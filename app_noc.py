import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import Image, ImageGrab, ImageTk
import pyperclip

from edge_bridge import abrir_no_edge, preparar_extensao
from tokens_ia import ConsumoIA
from recortes_email import CAMPOS_RECORTE, EditorRecortes, montar_recortes
from incidentes import FilaIncidentes, importar_eventos, CAMPOS_EVENTO
from extracao_local import CacheExtracao

from noc_services import (
    CAMPOS, MovideskWorker, RascunhoWorker, carregar_config, diretorio_aplicacao,
    preparar_config_apis,
    copiar_imagem, extrair_dados, gerar_assunto_email, gerar_template, validar_dados,
)


class GeradorIA_NOC:
    def __init__(self, root, config=None):
        self.root = root
        self.config = config or carregar_config(diretorio_aplicacao())
        self.eventos = queue.Queue()
        self.imagem = None
        self.recortes_email = {}
        self.miniatura = None
        self.operacao = None
        self.sequencia = 0
        self.revisao = 0
        self.carregando = True
        self.fechando = False
        self.atualizando = False
        self.save_after = None
        self.poll_after = None
        self.ultimo_erro = ""
        self.anterior = None
        self.fila = FilaIncidentes()
        self.cache_extracao = CacheExtracao()
        self.importacoes_pendentes = []
        self.avisos_extracao = []
        self.metricas_extracao = {}
        self.tokens_extracao = 0
        self.inicio_operacao = 0
        self.vars = {campo: tk.StringVar(root) for campo in CAMPOS}
        self.erros = {campo: tk.StringVar(root) for campo in CAMPOS}
        self.entradas = {}
        self.status = tk.StringVar(root, "Recuperando rascunho…")
        self.status_rascunho = tk.StringVar(root, "")
        self.tempo = tk.StringVar(root, "")
        self.assunto_email = tk.StringVar(root, "")
        self.canal = tk.StringVar(root, "WhatsApp")
        self.consumo_ia = ConsumoIA()
        self.resumo_tokens = tk.StringVar(root, self.consumo_ia.resumo(self.config))

        self.root.title("NOC")
        altura = min(720, self.root.winfo_screenheight() - 90)
        self.root.geometry(f"720x{max(520, altura)}")
        self.root.minsize(600, 520)
        self.root.protocol("WM_DELETE_WINDOW", self.fechar)
        self.montar_interface()
        for variavel in self.vars.values():
            variavel.trace_add("write", self.alterado)
        self.root.bind("<Control-n>", lambda _: self.novo_incidente())
        self.root.bind("<Control-Shift-V>", lambda _: self.ler_print())
        self.root.bind("<Control-i>", lambda _: self.importar_clipboard())
        self.root.bind("<MouseWheel>", self.rolar)

        self.movidesk = MovideskWorker(self.config, self.eventos)
        self.rascunho = RascunhoWorker(self.config, self.eventos)
        self.movidesk.start()
        self.rascunho.start()
        self.atualizar_controles()
        self.atualizar_menu()
        self.poll_after = self.root.after(100, self.processar_eventos)

    # ---------- interface ----------

    def montar_interface(self):
        estilo = ttk.Style(self.root)
        try:
            estilo.theme_use("clam")
        except tk.TclError:
            pass
        self.root.configure(background="#f6f7f9")
        estilo.configure(".", font=("Segoe UI", 10), background="#f6f7f9", foreground="#182230")
        estilo.configure("TButton", padding=(10, 6))
        estilo.configure("TEntry", padding=4, fieldbackground="white")
        estilo.configure("TCombobox", padding=4, fieldbackground="white")
        estilo.configure("TNotebook.Tab", padding=(16, 7))
        estilo.configure("Titulo.TLabel", font=("Segoe UI", 16, "bold"))
        estilo.configure("Discreto.TLabel", foreground="#667085", font=("Segoe UI", 9))
        estilo.configure("Erro.TLabel", foreground="#b42318", font=("Segoe UI", 9))
        estilo.configure("Principal.TButton", background="#215dcc", foreground="white", borderwidth=0)
        estilo.map("Principal.TButton", background=[("disabled", "#dfe5ed"), ("active", "#194ba8")],
                   foreground=[("disabled", "#667085")])

        topo = ttk.Frame(self.root, padding=(16, 10))
        topo.pack(fill="x")
        ttk.Label(topo, text="NOC", style="Titulo.TLabel").pack(side="left")
        self.seletor_fila = ttk.Combobox(topo, state="readonly", width=34)
        self.seletor_fila.pack(side="left", fill="x", expand=True, padx=(16, 8))
        self.seletor_fila.bind("<<ComboboxSelected>>", self.selecionar_incidente)
        self.btn_novo = ttk.Button(topo, text="+ Novo", width=8, command=self.novo_incidente)
        self.btn_novo.pack(side="left", padx=(0, 6))
        self.btn_mais = ttk.Menubutton(topo, text="⋯", width=4)
        self.btn_mais.pack(side="left")
        self.menu_mais = tk.Menu(self.btn_mais, tearoff=False)
        self.btn_mais.configure(menu=self.menu_mais)
        self.acoes_menu = {}
        itens = (
            ("conectar", "Conectar Zabbix", self.conectar_zabbix),
            None,
            ("capturar", "Guardar print sem extrair", self.capturar_print),
            ("reler", "Reler print guardado", lambda: self.extrair_com_ia(False)),
            ("ia", "Completar com IA", self.extrair_com_ia),
            ("copiar_print", "Copiar print", self.copiar_print),
            None,
            ("extensao", "Instalar extensão do Edge", self.configurar_extensao),
            ("config", "Configurações", self.configurar_apis),
            ("consumo", "Consumo e detalhes", self.mostrar_tokens),
            None,
            ("desfazer", "Desfazer novo incidente", self.desfazer_novo),
            ("remover", "Remover incidente da fila", self.remover_incidente),
        )
        for item in itens:
            if item is None:
                self.menu_mais.add_separator()
            else:
                chave, rotulo, comando = item
                self.menu_mais.add_command(label=rotulo, command=comando)
                self.acoes_menu[chave] = self.menu_mais.index("end")

        rodape = ttk.Frame(self.root, padding=(16, 6))
        rodape.pack(side="bottom", fill="x")
        self.status_label = ttk.Label(rodape, textvariable=self.status, wraplength=640, style="Discreto.TLabel")
        self.status_label.pack(fill="x", anchor="w")
        self.progresso = ttk.Progressbar(rodape, mode="indeterminate")
        linha_status = ttk.Frame(rodape)
        linha_status.pack(fill="x")
        ttk.Label(linha_status, textvariable=self.status_rascunho, style="Discreto.TLabel").pack(side="left")
        ttk.Label(linha_status, textvariable=self.tempo, style="Discreto.TLabel").pack(side="right")
        self.btn_detalhes = ttk.Button(rodape, text="Detalhes", command=self.detalhes_erro)
        rodape.bind("<Configure>", lambda e: self.status_label.configure(wraplength=max(200, e.width - 32)))

        acoes = ttk.Frame(self.root, padding=(16, 8))
        acoes.pack(side="bottom", fill="x")
        ticket_area = ttk.Frame(acoes)
        ticket_area.pack(side="left", fill="x", expand=True)
        ttk.Label(ticket_area, text="Ticket", style="Discreto.TLabel").pack(anchor="w")
        ticket_linha = ttk.Frame(ticket_area)
        ticket_linha.pack(fill="x")
        self.entradas["ticket"] = ttk.Entry(ticket_linha, textvariable=self.vars["ticket"], width=18)
        self.entradas["ticket"].pack(side="left")
        self.entradas["ticket"].bind("<FocusIn>", lambda _: self.mostrar_campo(self.entradas["ticket"]))
        self.erro_ticket = ttk.Label(ticket_linha, textvariable=self.erros["ticket"], style="Erro.TLabel")
        self.erro_ticket.pack(side="left", padx=(8, 0))
        self.btn_movidesk = ttk.Button(acoes, text="Abrir Movidesk", style="Principal.TButton",
                                       command=self.preencher_movidesk)
        self.btn_comunicado = ttk.Button(acoes, text="Copiar mensagem", style="Principal.TButton",
                                         command=lambda: self.copiar_comunicado(self.canal.get()))

        self.paginas = ttk.Notebook(self.root)
        self.paginas.pack(fill="both", expand=True, padx=16)
        self.pagina_incidente = ttk.Frame(self.paginas)
        self.pagina_comunicar = ttk.Frame(self.paginas, padding=(12, 12))
        self.paginas.add(self.pagina_incidente, text="Incidente")
        self.paginas.add(self.pagina_comunicar, text="Comunicar")
        self.paginas.bind("<<NotebookTabChanged>>", self.mudar_pagina)

        area = ttk.Frame(self.pagina_incidente)
        area.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(area, highlightthickness=0, background="#f6f7f9")
        barra = ttk.Scrollbar(area, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=barra.set)
        barra.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.conteudo = ttk.Frame(self.canvas, padding=(12, 12))
        janela = self.canvas.create_window((0, 0), window=self.conteudo, anchor="nw")
        self.conteudo.bind("<Configure>", lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(janela, width=e.width))

        entrada = ttk.Frame(self.conteudo)
        entrada.pack(fill="x", pady=(0, 12))
        self.btn_importar = ttk.Button(entrada, text="Importar dados", command=self.importar_clipboard)
        self.btn_importar.pack(side="left", padx=(0, 8))
        self.btn_ler_print = ttk.Button(entrada, text="Ler print", command=self.ler_print)
        self.btn_ler_print.pack(side="left")
        # Compatibilidade com testes e atalhos antigos.
        self.btn_ia = self.btn_ler_print
        if self.config.ia_automatica:
            self.btn_ler_print.configure(text="Ler print + IA")
        ttk.Label(entrada, text="Do Zabbix (Ctrl+I) ou print (Win+Shift+S).",
                  style="Discreto.TLabel").pack(side="left", padx=(12, 0))

        campos = ttk.Frame(self.conteudo)
        campos.pack(fill="x")
        campos.columnconfigure((0, 1), weight=1, uniform="campos")
        for rotulo, campo, linha, coluna, largura in (
            ("Alerta *", "alerta", 0, 0, 2),
            ("Servidor *", "servidor", 1, 0, 1),
            ("Severidade", "severidade", 1, 1, 1),
            ("Dados operacionais", "situacao", 2, 0, 2),
            ("Horário", "horario", 3, 0, 1),
            ("Link Zabbix", "link_zabbix", 3, 1, 1),
        ):
            self.criar_campo(campos, rotulo, campo, linha=linha, coluna=coluna, colunas=largura)

        self.area_print = ttk.Frame(self.conteudo, padding=(0, 6))
        self.area_print.pack(fill="x")
        self.preview_imagem = ttk.Label(self.area_print, style="Discreto.TLabel")
        self.preview_imagem.pack(side="left", fill="x", expand=True)
        self.btn_print = ttk.Button(self.area_print, text="Copiar", command=self.copiar_print)
        self.btn_print.pack(side="right")

        ttk.Label(self.pagina_comunicar, text="Canal", style="Discreto.TLabel").pack(anchor="w")
        self.seletor_canal = ttk.Combobox(self.pagina_comunicar, textvariable=self.canal,
                                          values=("WhatsApp", "Teams", "E-mail"), state="readonly")
        self.seletor_canal.pack(fill="x", pady=(4, 10))
        self.seletor_canal.bind("<<ComboboxSelected>>", self.mudar_canal)
        self.opcoes_canal = ttk.Frame(self.pagina_comunicar)
        self.opcoes_canal.pack(fill="x")
        self.campos_canal = {}
        for canal, campo, rotulo in (("WhatsApp", "acionamento", "Acionamento"),
                                     ("Teams", "time_resp", "Time responsável")):
            frame = ttk.Frame(self.opcoes_canal)
            self.criar_campo(frame, rotulo, campo)
            self.campos_canal[canal] = frame
        email = ttk.Frame(self.opcoes_canal)
        self.campos_canal["E-mail"] = email
        email_linha = ttk.Frame(email)
        email_linha.pack(fill="x", pady=(0, 8))
        ttk.Entry(email_linha, textvariable=self.assunto_email, state="readonly").pack(
            side="left", fill="x", expand=True)
        self.btn_assunto = ttk.Button(email_linha, text="Assunto", command=self.copiar_assunto_email)
        self.btn_assunto.pack(side="right", padx=(8, 0))
        self.previa = tk.Text(self.pagina_comunicar, height=9, width=1, wrap="word",
                              font=("Segoe UI", 10), relief="flat", padx=12, pady=12,
                              background="white", foreground="#182230", state="disabled")
        self.previa.pack(fill="both", expand=True, pady=(0, 8))
        self.area_recortes = ttk.Frame(self.pagina_comunicar)
        self.btn_recortar_email = ttk.Button(self.area_recortes, text="Recortar print",
                                             command=self.recortar_imagem_email)
        self.btn_recortar_email.pack(side="left", padx=(0, 8))
        self.btn_imagem_email = ttk.Button(self.area_recortes, text="Copiar recorte",
                                           command=self.copiar_imagem_email)
        self.btn_imagem_email.pack(side="left")
        self.btns_copiar = (self.btn_comunicado, self.btn_assunto)
        self.mudar_canal()
        self.mudar_pagina()
        self.atualizar_previews()
        self.atualizar_fila()

    def criar_campo(self, pai, rotulo, campo, linha=None, coluna=None, colunas=1):
        frame = ttk.Frame(pai)
        if linha is None:
            frame.pack(fill="x", pady=(0, 8))
        else:
            frame.grid(row=linha, column=coluna, columnspan=colunas, sticky="ew", padx=4, pady=(0, 8))
        ttk.Label(frame, text=rotulo, style="Discreto.TLabel").pack(anchor="w")
        if campo == "situacao":
            entrada = tk.Text(frame, height=3, wrap="word", font=("Segoe UI", 10), width=1, undo=True,
                              relief="flat", padx=8, pady=8, background="white")
            entrada.bind("<<Modified>>", self.situacao_alterada)
        elif campo == "severidade":
            entrada = ttk.Combobox(frame, textvariable=self.vars[campo], values=(
                "Não classificado", "Informação", "Aviso", "Média", "Alta", "Desastre"))
        else:
            entrada = ttk.Entry(frame, textvariable=self.vars[campo])
        entrada.pack(fill="x", pady=(2, 0))
        entrada.bind("<FocusIn>", lambda _: self.mostrar_campo(entrada))
        self.entradas[campo] = entrada
        aviso = ttk.Label(frame, textvariable=self.erros[campo], style="Erro.TLabel")

        def mostrar_erro(*_):
            if self.erros[campo].get():
                aviso.pack(anchor="w")
            else:
                aviso.pack_forget()

        self.erros[campo].trace_add("write", mostrar_erro)

    def mudar_pagina(self, _=None):
        try:
            comunicar = self.paginas.select() == str(self.pagina_comunicar)
        except tk.TclError:
            comunicar = False
        self.btn_movidesk.pack_forget()
        self.btn_comunicado.pack_forget()
        (self.btn_comunicado if comunicar else self.btn_movidesk).pack(side="right", padx=(12, 0))

    def mudar_canal(self, _=None):
        for frame in self.campos_canal.values():
            frame.pack_forget()
        self.campos_canal[self.canal.get()].pack(fill="x")
        self.area_recortes.pack_forget()
        if self.canal.get() == "E-mail":
            self.area_recortes.pack(fill="x", pady=(8, 0))
        self.btn_comunicado.configure(
            text="Copiar e-mail" if self.canal.get() == "E-mail" else "Copiar mensagem")
        self.atualizar_previews()

    # ---------- fila ----------

    def guardar_incidente(self):
        item = self.fila.obter()
        if item is None:
            return
        item["dados"] = self.obter_dados()
        item["imagem"] = self.imagem

    def atualizar_fila(self):
        valores = []
        for n, item in enumerate(self.fila.itens, 1):
            d = item["dados"]
            base = f"{n}. {d.get('servidor') or 'Novo'} — {d.get('alerta') or 'sem alerta'}"[:120]
            if d.get("ticket"):
                base += f" · {d['ticket']}"
            valores.append(base)
        self.seletor_fila.configure(values=valores)
        try:
            indice = next(i for i, item in enumerate(self.fila.itens) if item["id"] == self.fila.ativo)
        except StopIteration:
            indice = 0
        if valores:
            self.seletor_fila.current(indice)

    def ativar_incidente(self, identificador):
        self.fila.ativo = identificador
        item = self.fila.obter()
        self.definir_dados(item["dados"])
        self.definir_imagem(item["imagem"])
        self.atualizar_fila()
        self.atualizar_menu()
        self.revisao += 1
        self.agendar_salvamento()

    def selecionar_incidente(self, _=None):
        if self.operacao or self.carregando or self.fechando:
            return
        indice = self.seletor_fila.current()
        if 0 <= indice < len(self.fila.itens):
            self.guardar_incidente()
            self.ativar_incidente(self.fila.itens[indice]["id"])

    def navegar_fila(self, passo):
        if self.operacao or self.carregando or self.fechando or not self.fila.itens:
            return
        atual = next((i for i, item in enumerate(self.fila.itens) if item["id"] == self.fila.ativo), 0)
        self.guardar_incidente()
        self.ativar_incidente(self.fila.itens[(atual + passo) % len(self.fila.itens)]["id"])

    def remover_incidente(self):
        if self.operacao or self.carregando or self.fechando:
            return
        atual = self.fila.obter()
        if atual in self.fila.itens:
            self.fila.itens.remove(atual)
        if not self.fila.itens:
            self.fila.novo()
        self.anterior = None
        self.ativar_incidente(self.fila.itens[0]["id"])
        self.informar("Incidente removido.")

    def atualizar_menu(self):
        try:
            self.menu_mais.entryconfig(self.acoes_menu["desfazer"],
                                       state="normal" if self.anterior else "disabled")
        except (tk.TclError, KeyError, AttributeError):
            pass

    # ---------- entrada ----------

    def importar_clipboard(self):
        if self.operacao or self.carregando or self.fechando:
            return
        try:
            self.aplicar_importacao(importar_eventos(pyperclip.paste()))
        except Exception as exc:
            self.exibir_erro(str(exc))

    def aplicar_importacao(self, eventos):
        inicio = time.monotonic()
        self.guardar_incidente()
        ids = self.fila.importar(eventos)
        for identificador in ids:
            item = self.fila.obter(identificador)
            item["meta"]["metricas"] = {"origem": "DOM", "segundos": time.monotonic() - inicio, "chamadas": 0}
        self.ativar_incidente(ids[0])
        self.salvar_rascunho()
        msg = "Evento importado. Revise e abra o Movidesk." if len(ids) == 1 else \
            f"{len(ids)} eventos importados. Revise o primeiro."
        self.informar(msg)

    def conectar_zabbix(self):
        identificador = self.iniciar_operacao("conexao", "Conectando ao Zabbix…")
        if identificador is not None:
            self.movidesk.comandos.put((identificador, {"_conectar": True}))

    def ler_print(self):
        self.extrair_com_ia(self.config.ia_automatica)

    def situacao_alterada(self, _=None):
        entrada = self.entradas["situacao"]
        if entrada.edit_modified():
            entrada.edit_modified(False)
            self.vars["situacao"].set(entrada.get("1.0", "end-1c"))

    def definir_dados(self, dados):
        self.atualizando = True
        try:
            for campo in CAMPOS:
                self.vars[campo].set(dados.get(campo, ""))
                self.erros[campo].set("")
            texto = self.entradas["situacao"]
            estado = texto.cget("state")
            texto.configure(state="normal")
            texto.delete("1.0", "end")
            texto.insert("1.0", self.vars["situacao"].get())
            texto.edit_modified(False)
            texto.edit_reset()
            texto.configure(state=estado)
        finally:
            self.atualizando = False
        self.atualizar_previews()

    def obter_dados(self):
        return {campo: variavel.get().strip() for campo, variavel in self.vars.items()}

    def alterado(self, *_):
        if self.atualizando or self.carregando or self.fechando:
            return
        for erro in self.erros.values():
            erro.set("")
        self.revisao += 1
        item = self.fila.obter()
        if item is not None and item["meta"].get("origem"):
            revisados = set(item["meta"].get("campos_revisados", []))
            for campo in CAMPOS_EVENTO:
                if self.vars[campo].get().strip() != item["dados"].get(campo, ""):
                    revisados.add(campo)
            item["meta"]["campos_revisados"] = sorted(revisados)
        self.atualizar_previews()
        self.agendar_salvamento()

    def atualizar_previews(self):
        if not hasattr(self, "previa"):
            return
        dados = self.obter_dados()
        self.assunto_email.set(gerar_assunto_email(dados))
        self.previa.configure(state="normal")
        self.previa.delete("1.0", "end")
        self.previa.insert("1.0", gerar_template(dados, self.canal.get(), self.config.movidesk_url))
        self.previa.configure(state="disabled")

    def rolar(self, evento):
        try:
            if evento.widget.winfo_toplevel() != self.root or isinstance(evento.widget, (tk.Text, ttk.Combobox)):
                return
            self.canvas.yview_scroll(-int(evento.delta / 120), "units")
        except (tk.TclError, AttributeError):
            pass

    def mostrar_campo(self, entrada):
        try:
            self.root.update_idletasks()
            y = entrada.winfo_rooty() - self.conteudo.winfo_rooty()
            topo = self.canvas.canvasy(0)
            if y < topo or y + entrada.winfo_height() > topo + self.canvas.winfo_height():
                self.canvas.yview_moveto(max(0, y - 24) / max(1, self.conteudo.winfo_height()))
        except (tk.TclError, AttributeError):
            pass

    def atualizar_controles(self):
        bloqueado = self.carregando or self.fechando
        ocupado = bloqueado or self.operacao is not None
        for botao in (self.btn_novo, self.btn_importar, self.btn_ler_print, self.btn_movidesk,
                      self.btn_comunicado):
            try:
                botao.configure(state="disabled" if ocupado else "normal")
            except tk.TclError:
                pass
        for combo in (self.seletor_fila, self.seletor_canal):
            try:
                combo.configure(state="disabled" if ocupado else "readonly")
            except tk.TclError:
                pass
        try:
            self.btn_mais.configure(state="disabled" if ocupado else "normal")
        except tk.TclError:
            pass
        self.btn_print.configure(state="disabled" if ocupado or self.imagem is None else "normal")
        self.btn_recortar_email.configure(state="disabled" if ocupado or self.imagem is None else "normal")
        self.btn_imagem_email.configure(
            state="normal" if not ocupado and self.imagem is not None
            and all(c in self.recortes_email for c in CAMPOS_RECORTE) else "disabled")
        edicao_bloqueada = bloqueado or (self.operacao and self.operacao[1] == "ia")
        for entrada in self.entradas.values():
            try:
                entrada.configure(state="disabled" if edicao_bloqueada else "normal")
            except tk.TclError:
                pass
        for botao in self.btns_copiar:
            try:
                botao.configure(state="disabled" if edicao_bloqueada else "normal")
            except tk.TclError:
                pass

    def iniciar_operacao(self, tipo, mensagem):
        if self.operacao or self.carregando or self.fechando:
            return None
        self.sequencia += 1
        self.operacao = (self.sequencia, tipo)
        self.inicio_operacao = time.monotonic()
        self.informar(mensagem)
        self.progresso.pack(after=self.status_label, fill="x", pady=4)
        self.progresso.start(12)
        self.atualizar_controles()
        return self.sequencia

    def executar(self, tipo, mensagem, funcao):
        identificador = self.iniciar_operacao(tipo, mensagem)
        if identificador is None:
            return
        eventos = self.eventos

        def tarefa():
            try:
                resultado = funcao()
                eventos.put((f"{tipo}_ok", identificador, resultado))
            except Exception as exc:
                logging.getLogger("noc").exception("Falha na operação %s", tipo)
                eventos.put(("erro", identificador, str(exc)))

        threading.Thread(target=tarefa, name=f"noc-{tipo}", daemon=True).start()

    @staticmethod
    def ler_clipboard():
        imagem = ImageGrab.grabclipboard()
        if not isinstance(imagem, Image.Image):
            raise ValueError("Sem imagem no clipboard. Use Win+Shift+S e tente de novo.")
        return imagem.convert("RGB")

    def capturar_print(self):
        self.executar("captura", "Guardando print…", self.ler_clipboard)

    def definir_imagem(self, imagem):
        if imagem is not self.imagem:
            self.recortes_email = {}
        self.imagem = imagem
        if imagem is None:
            self.miniatura = None
            self.preview_imagem.configure(image="", text="Sem print (opcional)")
        else:
            miniatura = imagem.copy()
            miniatura.thumbnail((320, 110))
            self.miniatura = ImageTk.PhotoImage(miniatura, master=self.root)
            self.preview_imagem.configure(image=self.miniatura, compound="top",
                                          text=f"{imagem.width} × {imagem.height}px")
        self.atualizar_controles()

    def mostrar_tokens(self):
        self.guardar_incidente()
        janela = tk.Toplevel(self.root)
        janela.title("Consumo e detalhes")
        janela.transient(self.root)
        conteudo = ttk.Frame(janela, padding=20)
        conteudo.pack(fill="both", expand=True)
        ttk.Label(conteudo, textvariable=self.resumo_tokens, wraplength=560,
                  justify="left").pack(fill="x")
        medidas = [i["meta"].get("metricas", {}) for i in self.fila.itens if i["meta"].get("metricas")]
        locais = sum(1 for m in medidas if m.get("chamadas", 0) == 0)
        linhas = [f"Incidentes com operação local: {locais}/{len(medidas)}." if medidas
                   else "Nenhuma importação/extração registrada."]
        for n, item in enumerate(self.fila.itens, 1):
            meta = item["meta"]
            m = meta.get("metricas", {})
            linhas.append(
                f"{n}. {item['dados'].get('servidor') or 'Novo'} · {meta.get('origem', 'manual')} · "
                f"{m.get('segundos', 0):.1f}s · {m.get('chamadas', 0)} IA · "
                f"{meta.get('tokens_reportados', 0)} tokens")
        ttk.Label(conteudo, text="\n".join(linhas), wraplength=560, justify="left",
                  style="Discreto.TLabel").pack(fill="x", pady=(12, 0))
        ttk.Button(conteudo, text="Configurações", command=self.configurar_apis).pack(anchor="w", pady=(12, 0))

    def configurar_apis(self):
        try:
            arquivo = preparar_config_apis(self.config.diretorio)
            subprocess.Popen(["notepad.exe", str(arquivo)])
            self.informar("Ajuste o .env, salve e reinicie o NOC.")
        except Exception as exc:
            self.exibir_erro(f"Não foi possível abrir as configurações.\n\n{exc}")

    def extrair_com_ia(self, permitir_ia=True):
        if self.operacao or self.carregando or self.fechando:
            return
        imagem = self.imagem
        eventos = self.eventos
        config = self.config
        conhecidos = {c: self.vars[c].get().strip() for c in CAMPOS_EVENTO} if permitir_ia else {}

        def tarefa():
            capturada = imagem if imagem is not None else GeradorIA_NOC.ler_clipboard()
            eventos.put(("imagem", identificador, capturada))
            return extrair_dados(config, capturada, lambda tipo, texto: eventos.put((tipo, identificador, texto)),
                                permitir_ia=permitir_ia, cache=self.cache_extracao, conhecidos=conhecidos)

        self.provedor_ia = "IA"
        self.avisos_extracao = []
        self.metricas_extracao = {}
        self.tokens_extracao = 0
        identificador = self.iniciar_operacao("ia", "Lendo print…")
        if identificador is None:
            return

        def executar_ia():
            try:
                eventos.put(("ia_ok", identificador, tarefa()))
            except Exception as exc:
                logging.getLogger("noc").exception("Falha na extração com IA")
                eventos.put(("erro", identificador, str(exc)))

        threading.Thread(target=executar_ia, name="noc-ia", daemon=True).start()

    def copiar_assunto_email(self):
        if self.fechando or self.carregando or not self.validar("E-mail"):
            return
        try:
            pyperclip.copy(gerar_assunto_email(self.obter_dados()))
            self.informar("Assunto copiado.")
        except Exception as exc:
            self.exibir_erro(f"Não foi possível copiar.\n\n{exc}")

    def recortar_imagem_email(self):
        if self.imagem is None or self.operacao or self.carregando or self.fechando:
            return
        imagem = self.imagem

        def confirmar(caixas):
            if self.imagem is not imagem or self.fechando:
                return
            self.recortes_email = caixas
            self.atualizar_controles()
            self.copiar_imagem_email()

        EditorRecortes(self.root, imagem, self.recortes_email, confirmar)

    def copiar_imagem_email(self):
        if self.imagem is None or not all(c in self.recortes_email for c in CAMPOS_RECORTE):
            return
        imagem, caixas = self.imagem, dict(self.recortes_email)
        hwnd = self.root.winfo_id()
        self.executar("imagem_email", "Copiando recorte…",
                      lambda: copiar_imagem(montar_recortes(imagem, caixas), hwnd))

    def copiar_print(self):
        if self.imagem is not None:
            imagem = self.imagem
            hwnd = self.root.winfo_id()
            self.executar("print", "Copiando print…", lambda: copiar_imagem(imagem, hwnd))

    def validar(self, finalidade):
        erros = validar_dados(self.obter_dados(), finalidade)
        for campo, variavel in self.erros.items():
            variavel.set(erros.get(campo, ""))
        if erros:
            campo = next(iter(erros))
            try:
                self.paginas.select(str(self.pagina_comunicar if campo in ("ticket", "acionamento", "time_resp")
                                        else self.pagina_incidente))
            except tk.TclError:
                pass
            try:
                self.entradas[campo].focus_set()
            except (tk.TclError, KeyError):
                pass
            self.informar("Revise os campos destacados.")
        return not erros

    def preencher_movidesk(self):
        if self.operacao or self.carregando or self.fechando or not self.validar("Movidesk"):
            return
        identificador = self.iniciar_operacao("movidesk", "Abrindo Movidesk…")
        self.movidesk.comandos.put((identificador, {**self.obter_dados(), "_incidente_id": self.fila.ativo}))

    # Mantido para compatibilidade.
    preencher_movidesk_playwright = preencher_movidesk

    def configurar_extensao(self):
        try:
            pasta = preparar_extensao(self.config.diretorio)
        except Exception as exc:
            self.exibir_erro(f"Não foi possível preparar a extensão.\n\n{exc}")
            return
        janela = tk.Toplevel(self.root)
        janela.title("Extensão do Edge")
        janela.transient(self.root)
        conteudo = ttk.Frame(janela, padding=20)
        conteudo.pack(fill="both", expand=True)
        ttk.Label(conteudo, text="Instale uma vez no perfil do Edge com Zabbix e Movidesk.",
                  wraplength=480).pack(anchor="w")
        ttk.Label(conteudo, text="1. Abra edge://extensions/ e ative o modo desenvolvedor.\n"
                  "2. Carregar sem compactação na pasta abaixo.\n3. Recarregue após atualizar.",
                  wraplength=480).pack(anchor="w", pady=12)
        caminho = ttk.Entry(conteudo, width=70)
        caminho.insert(0, str(pasta))
        caminho.configure(state="readonly")
        caminho.pack(fill="x", pady=(0, 10))

        def abrir_extensoes():
            try:
                abrir_no_edge("edge://extensions/")
            except Exception as exc:
                self.exibir_erro(str(exc))

        def copiar_caminho():
            try:
                pyperclip.copy(str(pasta))
                self.informar("Caminho copiado.")
            except Exception as exc:
                self.exibir_erro(str(exc))

        ttk.Button(conteudo, text="Abrir extensões", command=abrir_extensoes).pack(fill="x", pady=3)
        ttk.Button(conteudo, text="Copiar caminho", command=copiar_caminho).pack(fill="x", pady=3)

    def copiar_comunicado(self, canal):
        if self.fechando or self.carregando or not self.validar(canal):
            return
        try:
            pyperclip.copy(gerar_template(self.obter_dados(), canal, self.config.movidesk_url))
            self.informar(f"{canal} copiado.")
        except Exception as exc:
            self.exibir_erro(f"Não foi possível copiar.\n\n{exc}")

    def novo_incidente(self):
        if self.operacao or self.carregando or self.fechando:
            return
        self.guardar_incidente()
        self.anterior = self.fila.ativo
        self.fila.novo()
        self.definir_dados({})
        self.definir_imagem(None)
        self.atualizar_fila()
        self.atualizar_menu()
        self.revisao += 1
        self.salvar_rascunho()
        try:
            self.paginas.select(str(self.pagina_incidente))
            self.canvas.yview_moveto(0)
        except tk.TclError:
            pass
        self.entradas["alerta"].focus_set()
        self.informar("Novo incidente. Importe os dados ou preencha.")

    def desfazer_novo(self):
        if self.anterior is None or self.operacao or self.carregando or self.fechando:
            return
        self.guardar_incidente()
        if self.fila.obter(self.anterior) is None:
            return
        atual = self.fila.obter()
        if atual is not None and not any(atual["dados"].values()) and atual["imagem"] is None:
            self.fila.itens.remove(atual)
        self.ativar_incidente(self.anterior)
        self.anterior = None
        self.atualizar_menu()
        self.revisao += 1
        self.salvar_rascunho()
        self.informar("Incidente anterior restaurado.")

    def agendar_salvamento(self):
        self.status_rascunho.set("Alterações pendentes…")
        if self.save_after:
            self.root.after_cancel(self.save_after)
        self.save_after = self.root.after(750, self.salvar_rascunho)

    def salvar_rascunho(self):
        if self.save_after:
            self.root.after_cancel(self.save_after)
            self.save_after = None
        if not self.carregando:
            self.guardar_incidente()
            self.atualizar_fila()
            self.status_rascunho.set("Salvando…")
            self.rascunho.comandos.put((self.revisao, self.obter_dados(), self.imagem, self.fila.snapshot()))

    def informar(self, mensagem):
        self.status.set(mensagem)
        self.ultimo_erro = ""
        self.btn_detalhes.pack_forget()

    def exibir_erro(self, mensagem):
        self.ultimo_erro = mensagem
        self.status.set(mensagem.split("\n")[0][:350])
        self.btn_detalhes.pack(anchor="w", pady=(4, 0))

    def detalhes_erro(self):
        messagebox.showerror("Detalhes", self.ultimo_erro, parent=self.root)

    def processar_eventos(self):
        self.poll_after = None
        try:
            while True:
                tipo, identificador, resultado = self.eventos.get_nowait()
                if tipo == "rascunho_carregado":
                    if not self.fechando:
                        dados, imagem = resultado
                        self.definir_dados(dados)
                        self.definir_imagem(imagem)
                        if self.rascunho.fila_carregada:
                            self.fila.restaurar(self.rascunho.fila_carregada)
                            item = self.fila.obter()
                            self.definir_dados(item["dados"])
                            self.definir_imagem(item["imagem"])
                        else:
                            self.guardar_incidente()
                        self.atualizar_fila()
                        self.atualizar_menu()
                        self.carregando = False
                        self.atualizar_controles()
                        self.informar("Pronto. Importe os dados do Zabbix." if not any(dados.values()) and not imagem
                                      else "Rascunho recuperado.")
                elif tipo == "rascunho_erro_carga":
                    self.carregando = False
                    self.atualizar_controles()
                    self.exibir_erro(f"Rascunho inválido. Veja .noc_data/rascunho.json.\n\n{resultado}")
                elif tipo == "rascunho_salvo":
                    if identificador == self.revisao:
                        self.status_rascunho.set("✓ Salvo")
                        if self.fechando:
                            self.encerrar_workers()
                elif tipo == "rascunho_erro":
                    if identificador == self.revisao:
                        self.status_rascunho.set("Não salvo — verifique espaço/permissão")
                        self.exibir_erro(f"Não foi possível salvar.\n\n{resultado}")
                        if self.fechando:
                            if messagebox.askyesno("Rascunho não salvo",
                                                  "Fechar sem salvar?", parent=self.root):
                                self.encerrar_workers()
                            else:
                                self.fechando = False
                                self.atualizar_controles()
                elif tipo == "zabbix_importado" and not self.fechando:
                    self.importacoes_pendentes.append(resultado)
                elif tipo == "ticket_recebido" and not self.fechando:
                    item = self.fila.obter(identificador)
                    if item:
                        if identificador == self.fila.ativo:
                            self.guardar_incidente()
                        existente = item["dados"].get("ticket")
                        if existente and existente != resultado["ticket"]:
                            self.exibir_erro(f"Ticket {resultado['ticket']} retornado, mas há {existente}. Revise.")
                        else:
                            item["dados"]["ticket"] = resultado["ticket"]
                            item["meta"]["link_movidesk"] = resultado["url"]
                            if identificador == self.fila.ativo:
                                self.definir_dados(item["dados"])
                            self.revisao += 1
                            self.salvar_rascunho()
                            self.informar(f"Ticket {resultado['ticket']} recebido.")
                elif tipo == "integracao_aviso" and not self.fechando:
                    self.informar(resultado)
                elif not self.fechando and self.operacao and identificador == self.operacao[0]:
                    if tipo == "ia_consumo":
                        self.consumo_ia.registrar(resultado)
                        self.resumo_tokens.set(self.consumo_ia.resumo(self.config))
                        self.tokens_extracao += resultado.get("total") or 0
                        continue
                    if tipo == "extracao_aviso":
                        self.avisos_extracao.append(resultado)
                        continue
                    if tipo == "extracao_metricas":
                        self.metricas_extracao = resultado
                        continue
                    if tipo == "ia_provedor":
                        self.provedor_ia = resultado
                        continue
                    if tipo == "progresso":
                        self.informar(resultado)
                        continue
                    if tipo == "imagem":
                        self.definir_imagem(resultado)
                        self.revisao += 1
                        self.salvar_rascunho()
                        continue
                    self.operacao = None
                    self.progresso.stop()
                    self.progresso.pack_forget()
                    self.tempo.set("")
                    self.atualizar_controles()
                    if tipo == "erro":
                        self.exibir_erro(resultado)
                        if self.tokens_extracao:
                            meta = self.fila.obter()["meta"]
                            meta["tokens_reportados"] = meta.get("tokens_reportados", 0) + self.tokens_extracao
                            self.tokens_extracao = 0
                            self.revisao += 1
                            self.salvar_rascunho()
                    elif tipo == "captura_ok":
                        self.definir_imagem(resultado)
                        self.revisao += 1
                        self.salvar_rascunho()
                        self.informar("Print guardado.")
                    elif tipo == "ia_ok":
                        dados = self.obter_dados()
                        mudou = any(dados[c] and resultado.get(c) and dados[c] != resultado[c]
                                    for c in ("alerta", "servidor"))
                        if mudou:
                            self.guardar_incidente()
                            self.fila.novo()
                            for campo in ("ticket", "link_zabbix", "acionamento", "time_resp"):
                                dados[campo] = ""
                        dados.update({c: v for c, v in resultado.items() if v or not dados.get(c)})
                        self.definir_dados(dados)
                        meta = self.fila.obter()["meta"]
                        meta["origem"] = self.provedor_ia
                        meta["metricas"] = self.metricas_extracao
                        meta["tokens_reportados"] = meta.get("tokens_reportados", 0) + self.tokens_extracao
                        self.tokens_extracao = 0
                        self.revisao += 1
                        self.salvar_rascunho()
                        extra = " Novo incidente criado." if mudou else ""
                        avisos = f" {' | '.join(self.avisos_extracao)}" if self.avisos_extracao else ""
                        self.informar(f"Dados prontos via {self.provedor_ia}.{extra}{avisos}")
                    elif tipo == "conexao_ok":
                        self.informar("Zabbix conectado. Use Enviar ao NOC no navegador.")
                    elif tipo == "movidesk_ok":
                        self.informar("Preenchido. Revise, salve e o número volta sozinho.")
                    elif tipo == "print_ok":
                        self.informar("✓ Print copiado (Ctrl+V no ticket).")
                    elif tipo == "imagem_email_ok":
                        self.informar("Recorte copiado. Cole no e-mail (Ctrl+V).")
        except queue.Empty:
            pass
        if self.importacoes_pendentes and not self.operacao and not self.carregando and not self.fechando:
            while self.importacoes_pendentes:
                self.aplicar_importacao(self.importacoes_pendentes.pop(0))
        if self.operacao:
            self.tempo.set(f"{int(time.monotonic() - self.inicio_operacao)}s")
        if self.fechando and not self.movidesk.is_alive() and not self.rascunho.is_alive():
            self.progresso.stop()
            self.root.destroy()
            return
        self.poll_after = self.root.after(100, self.processar_eventos)

    def fechar(self):
        if self.fechando:
            return
        self.fechando = True
        self.salvar_rascunho()
        if self.carregando:
            self.encerrar_workers()
        self.atualizar_controles()
        self.informar("Salvando e encerrando…")

    def encerrar_workers(self):
        self.rascunho.comandos.put(None)
        self.movidesk.encerrar.set()


def main():
    root = tk.Tk()
    try:
        config = carregar_config(diretorio_aplicacao())
        preparar_extensao(config.diretorio)
        config.dados_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(config.dados_dir / "noc.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(threadName)s] %(message)s"))
        logging.getLogger("noc").addHandler(handler)
        logging.getLogger("noc").setLevel(logging.INFO)
        GeradorIA_NOC(root, config)
    except Exception as exc:
        messagebox.showerror("Não foi possível iniciar", str(exc), parent=root)
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--verificar-build":
        from verificar_build import verificar

        raise SystemExit(verificar(Path(sys.argv[2])))
    else:
        main()
