import tkinter as tk
from tkinter import messagebox
from PIL import ImageGrab
import google.generativeai as genai
import pyperclip
import json
import re
import os
from datetime import datetime
from playwright.sync_api import sync_playwright

# ==========================================
# CONFIGURAÇÃO DA API DO GEMINI
# ==========================================
# Insira a sua chave gerada no Google AI Studio
API_KEY = "SUA_CHAVE_API_AQUI" 
genai.configure(api_key=API_KEY)

def obter_saudacao():
    hora = datetime.now().hour
    if hora < 12:
        return "Bom dia"
    elif hora < 18:
        return "Boa tarde"
    else:
        return "Boa noite"

class GeradorIA_NOC:
    def __init__(self, root):
        self.root = root
        self.root.title("Orquestrador SRE NOC - IA & Playwright")
        self.root.geometry("650x850")
        self.root.configure(padx=20, pady=10)

        fonte_titulo = ("Arial", 11, "bold")
        fonte_label = ("Arial", 9, "bold")
        fonte_input = ("Arial", 10)

        # ==========================================
        # 1. EXTRAÇÃO INTELIGENTE (ZABBIX)
        # ==========================================
        tk.Label(root, text="--- 1. EXTRAÇÃO INTELIGENTE (ZABBIX) ---", font=fonte_titulo, fg="#1976D2").pack(pady=(5, 5))
        
        btn_ia = tk.Button(root, text="🧠 Extrair Dados do Print (Área de Transferência)", bg="#8E24AA", fg="white", font=("Arial", 10, "bold"), command=self.extrair_com_ia, height=2)
        btn_ia.pack(fill="x", pady=(0, 10))

        self.criar_campo("Alerta (Trigger):", "alerta", fonte_label, fonte_input)
        self.criar_campo("Servidor (Host):", "servidor", fonte_label, fonte_input)
        self.criar_campo("Severidade:", "severidade", fonte_label, fonte_input)
        self.criar_campo("Dados Operacionais:", "situacao", fonte_label, fonte_input)
        self.criar_campo("Horário da Falha:", "horario", fonte_label, fonte_input)
        self.criar_campo("Link do Zabbix:", "link_zabbix", fonte_label, fonte_input)

        # ==========================================
        # 2. MOVIDESK (PLAYWRIGHT AUTOMAÇÃO)
        # ==========================================
        tk.Label(root, text="--- 2. MOVIDESK ---", font=fonte_titulo, fg="#F57C00").pack(pady=(15, 5))

        btn_playwright = tk.Button(root, text="🌐 Abrir e Preencher Movidesk", bg="#0277BD", fg="white", font=("Arial", 10, "bold"), command=self.preencher_movidesk_playwright, height=2)
        btn_playwright.pack(fill="x", pady=(0, 15))

        self.criar_campo("N° do Ticket gerado no Movidesk:", "ticket", fonte_label, fonte_input)
        self.criar_campo("Acionamento (WhatsApp):", "acionamento", fonte_label, fonte_input)
        self.criar_campo("Time Responsável (Teams):", "time_resp", fonte_label, fonte_input)

        # ==========================================
        # 3. DISPARO (WPP / TEAMS / EMAIL)
        # ==========================================
        tk.Label(root, text="--- 3. COMUNICAÇÃO MULTICANAL ---", font=fonte_titulo, fg="#388E3C").pack(pady=(15, 5))
        
        frame_comunicacao = tk.Frame(root)
        frame_comunicacao.pack(fill="x", pady=(5, 5))

        btn_wpp = tk.Button(frame_comunicacao, text="Copiar WhatsApp", bg="#25D366", fg="white", font=fonte_label, command=self.copiar_wpp)
        btn_wpp.pack(side="left", expand=True, fill="x", padx=2)

        btn_teams = tk.Button(frame_comunicacao, text="Copiar Teams", bg="#6264A7", fg="white", font=fonte_label, command=self.copiar_teams)
        btn_teams.pack(side="left", expand=True, fill="x", padx=2)

        btn_email = tk.Button(frame_comunicacao, text="Copiar E-mail", bg="#D44638", fg="white", font=fonte_label, command=self.copiar_email)
        btn_email.pack(side="left", expand=True, fill="x", padx=2)

    def criar_campo(self, label_text, var_name, fonte_label, fonte_input):
        tk.Label(self.root, text=label_text, font=fonte_label).pack(anchor="w")
        entrada = tk.Entry(self.root, width=80, font=fonte_input)
        entrada.pack(pady=(0, 4))
        setattr(self, f"entrada_{var_name}", entrada)

    def obter_dados(self):
        return {
            "alerta": self.entrada_alerta.get().strip(),
            "servidor": self.entrada_servidor.get().strip(),
            "severidade": self.entrada_severidade.get().strip(),
            "situacao": self.entrada_situacao.get().strip(),
            "horario": self.entrada_horario.get().strip(),
            "link_zabbix": self.entrada_link_zabbix.get().strip(),
            "ticket": self.entrada_ticket.get().strip(),
            "acionamento": self.entrada_acionamento.get().strip(),
            "time_resp": self.entrada_time_resp.get().strip()
        }

    # ==========================
    # LÓGICA DE INTELIGÊNCIA ARTIFICIAL
    # ==========================
    def extrair_com_ia(self):
        img = ImageGrab.grabclipboard()
        if img is None:
            messagebox.showwarning("Aviso", "Nenhuma imagem encontrada na área de transferência. Tire um print (Win+Shift+S) do Zabbix primeiro.")
            return

        self.root.title("Processando imagem com IA... Aguarde")
        self.root.update()

        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            prompt = """
            Analise a imagem deste alerta de monitoramento.
            Extraia exatamente as informações solicitadas e retorne APENAS um JSON válido, sem formatação extra.
            Chaves obrigatórias do JSON:
            - "alerta" (corresponde a Trigger ou Event name)
            - "servidor" (corresponde a Host)
            - "severidade" (corresponde a Severity)
            - "situacao" (corresponde a Operational data ou descrição do erro)
            - "horario" (corresponde a Time ou Hora)
            """
            
            response = model.generate_content([prompt, img])
            texto_json = response.text
            match = re.search(r'```(?:json)?\s*(.*?)\s*```', texto_json, re.DOTALL)
            if match:
                texto_json = match.group(1)
                
            dados_ia = json.loads(texto_json)

            self.entrada_alerta.delete(0, tk.END)
            self.entrada_alerta.insert(0, dados_ia.get("alerta", ""))

            self.entrada_servidor.delete(0, tk.END)
            self.entrada_servidor.insert(0, dados_ia.get("servidor", ""))

            self.entrada_severidade.delete(0, tk.END)
            self.entrada_severidade.insert(0, dados_ia.get("severidade", ""))

            self.entrada_situacao.delete(0, tk.END)
            self.entrada_situacao.insert(0, dados_ia.get("situacao", ""))

            self.entrada_horario.delete(0, tk.END)
            self.entrada_horario.insert(0, dados_ia.get("horario", ""))

            self.root.title("Orquestrador SRE NOC - IA & Playwright")
            messagebox.showinfo("Sucesso", "Dados extraídos com sucesso pela IA!")

        except Exception as e:
            self.root.title("Orquestrador SRE NOC - IA & Playwright")
            messagebox.showerror("Erro na IA", f"Ocorreu um erro ao processar a imagem:\n{str(e)}")

    # ==========================
    # LÓGICA DO PLAYWRIGHT (AUTOMAÇÃO WEB)
    # ==========================
    def preencher_movidesk_playwright(self):
        d = self.obter_dados()
        
        if not d['alerta'] or not d['servidor']:
            messagebox.showwarning("Aviso", "Preencha os dados do alerta e servidor antes de abrir o Movidesk.")
            return

        assunto = f"{d['alerta']} - {d['servidor']}"
        user_data_dir = os.path.join(os.getcwd(), "movidesk_profile")

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch_persistent_context(
                    user_data_dir,
                    headless=False,
                    args=["--start-maximized"],
                    no_viewport=True
                )
                
                page = browser.new_page()
                page.goto("https://grupohda.movidesk.com/Ticket/Create")
                
                # Aguarda o carregamento do campo de assunto
                page.wait_for_selector('input[name="Subject"], input[id*="Subject"]', timeout=20000)
                
                # Preenche o Assunto
                page.fill('input[name="Subject"]', assunto)
                
                # Prepara o HTML da Descrição
                html_descricao = f"""
                    <p><strong>Abertura de Ticket via NOC (IA):</strong></p>
                    <ul>
                        <li><strong>Alerta:</strong> {d['alerta']}</li>
                        <li><strong>Servidor:</strong> {d['servidor']}</li>
                        <li><strong>Severidade:</strong> {d['severidade']}</li>
                        <li><strong>Dados Operacionais:</strong> {d['situacao']}</li>
                    </ul>
                    <p><strong>Link do Zabbix:</strong> <a href="{d['link_zabbix']}">{d['link_zabbix']}</a></p>
                    <br><p><em>Colar o print do alerta abaixo:</em></p><br>
                """
                
                # Injeta a descrição no iframe do editor rico
                frame = page.frame_locator("iframe.tox-edit-area__iframe, iframe.k-content")
                frame.locator("body").evaluate(f"(body) => body.innerHTML = `{html_descricao}`")
                
                print("Automação do Movidesk finalizada. Por favor, cole o print e guarde o ticket.")
                
                # O page.pause() suspende o script para que possa interagir manualmente com o ecrã
                page.pause()
                
        except Exception as e:
            messagebox.showerror("Erro de Automação", f"Falha ao executar o Playwright:\n{str(e)}")

    # ==========================
    # GERAÇÃO DE TEMPLATES
    # ==========================
    def copiar_para_clipboard(self, texto, nome):
        pyperclip.copy(texto)
        messagebox.showinfo("Copiado", f"O template de {nome} foi copiado para a área de transferência!")

    def copiar_wpp(self):
        d = self.obter_dados()
        saudacao = obter_saudacao()
        texto = f"""Equipe NOC
{saudacao},

• Ticket aberto no Movidesk: {d['ticket']}
• Servidor impactado: {d['servidor']}
• Severidade: {d['severidade']}
• Erro: {d['alerta']}
• Situação atual: {d['situacao']}
• Acionamento: {d['acionamento']}"""
        self.copiar_para_clipboard(texto, "WhatsApp")

    def copiar_teams(self):
        d = self.obter_dados()
        texto = f"""{d['ticket']}
{d['alerta']}
https://grupohda.movidesk.com/Ticket/Edit/{d['ticket']}
{d['time_resp']}"""
        self.copiar_para_clipboard(texto, "Teams")

    def copiar_email(self):
        d = self.obter_dados()
        texto = f"""Prezados,

Gostaria de informar sobre alertas detectados no sistema Zabbix. Abaixo estão os detalhes da falha:

N° do Ticket criado: {d['ticket']}
Alerta: {d['alerta']}
Severidade: {d['severidade']}
Servidor: {d['servidor']}
Dados operacionais: {d['situacao']}
Horário da Falha: {d['horario']}"""
        self.copiar_para_clipboard(texto, "E-mail")

if __name__ == "__main__":
    janela = tk.Tk()
    app = GeradorIA_NOC(janela)
    janela.mainloop()