import json
import os
from pathlib import Path
from dataclasses import replace
import queue
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from PIL import Image

from app_noc import GeradorIA_NOC
from noc_services import (
    CAMPOS, Config, RascunhoWorker, diretorio_aplicacao, gerar_html,
    interpretar_resposta, validar_dados,
)


def dados_incidente(**valores):
    dados = dict.fromkeys(CAMPOS, "")
    dados.update(alerta="CPU alta", servidor="host-01", ticket="123")
    dados.update(valores)
    return dados


class ExecutavelTests(unittest.TestCase):
    def test_configuracao_fica_fora_do_pacote_e_sobrevive_a_atualizacao(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            pacote = raiz / "_internal"
            pacote.mkdir()
            (pacote / ".env.example").write_text("GEMINI_API_KEY=exemplo\n", encoding="utf-8")
            with patch.dict(os.environ, {"LOCALAPPDATA": str(raiz / "usuario")}), patch("sys.frozen", True, create=True), patch("sys._MEIPASS", str(pacote), create=True):
                destino = diretorio_aplicacao()
                self.assertEqual(destino, raiz / "usuario" / "AutomacaoNOC")
                arquivo = destino / ".env"
                self.assertEqual(arquivo.read_text(encoding="utf-8"), "GEMINI_API_KEY=exemplo\n")
                arquivo.write_text("GEMINI_API_KEY=configuracao_do_usuario\n", encoding="utf-8")
                (pacote / ".env.example").write_text("OUTRO_PADRAO=1\n", encoding="utf-8")
                self.assertEqual(diretorio_aplicacao(), destino)
                self.assertEqual(arquivo.read_text(encoding="utf-8"), "GEMINI_API_KEY=configuracao_do_usuario\n")


class DadosTests(unittest.TestCase):
    def test_resposta_ia_incompleta_nao_vira_incidente_valido(self):
        for texto in ('[]', '{"alerta": "CPU alta"}', '{"alerta": [], "servidor": "host"}'):
            with self.subTest(texto=texto), self.assertRaises(ValueError):
                interpretar_resposta(texto)
        resultado = interpretar_resposta('```json\n{"alerta":"CPU alta", "servidor":"host", "situacao":null}\n```')
        self.assertEqual(resultado["situacao"], "")

    def test_validacao_depende_da_etapa(self):
        dados = dados_incidente(ticket="")
        self.assertEqual(validar_dados(dados, "Movidesk"), {})
        self.assertIn("ticket", validar_dados(dados, "Teams"))
        self.assertIn("ticket", validar_dados(dados_incidente(ticket="123/456"), "Teams"))
        self.assertIn("link_zabbix", validar_dados(dados_incidente(link_zabbix="javascript:alert(1)"), "Movidesk"))

    def test_html_preserva_texto_sem_injetar_marcacao(self):
        html = gerar_html(dados_incidente(alerta='<script>alert("x")</script>', horario="10:42", situacao="valor < 5 & > 1"))
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("10:42", html)
        self.assertIn("&amp;", html)


class RascunhoTests(unittest.TestCase):
    def test_ultimo_snapshot_recupera_campos_e_imagem(self):
        with tempfile.TemporaryDirectory() as pasta:
            config = Config(Path(pasta))
            eventos = queue.Queue()
            worker = RascunhoWorker(config, eventos)
            worker.start()
            self.assertEqual(eventos.get(timeout=3)[0], "rascunho_carregado")
            imagem = Image.new("RGB", (16, 12), "red")
            worker.comandos.put((1, dados_incidente(ticket="123"), imagem))
            worker.comandos.put((2, dados_incidente(ticket="456"), imagem))
            worker.comandos.put(None)
            worker.join(timeout=5)
            self.assertFalse(worker.is_alive())
            dados, recuperada = RascunhoWorker(config, eventos).carregar()
            self.assertEqual(dados["ticket"], "456")
            self.assertEqual(recuperada.getpixel((0, 0)), (255, 0, 0))
            self.assertFalse((config.dados_dir / "rascunho.tmp").exists())

    def test_novo_incidente_remove_tambem_imagem_do_rascunho(self):
        with tempfile.TemporaryDirectory() as pasta:
            config = Config(Path(pasta))
            worker = RascunhoWorker(config, queue.Queue())
            worker.start()
            worker.comandos.put((1, dados_incidente(), Image.new("RGB", (2, 2))))
            worker.comandos.put((2, dict.fromkeys(CAMPOS, ""), None))
            worker.comandos.put(None)
            worker.join(timeout=5)
            dados, imagem = worker.carregar()
            self.assertFalse(any(dados.values()))
            self.assertIsNone(imagem)

    def test_rascunho_corrompido_e_preservado_antes_de_nova_gravacao(self):
        with tempfile.TemporaryDirectory() as pasta:
            config = Config(Path(pasta))
            config.dados_dir.mkdir()
            arquivo = config.dados_dir / "rascunho.json"
            arquivo.write_text("JSON interrompido", encoding="utf-8")
            eventos = queue.Queue()
            worker = RascunhoWorker(config, eventos)
            with self.assertLogs("noc", level="ERROR"):
                worker.start()
                self.assertEqual(eventos.get(timeout=3)[0], "rascunho_erro_carga")
            worker.comandos.put((1, dados_incidente(), None))
            worker.comandos.put(None)
            worker.join(timeout=5)
            backups = list(config.dados_dir.glob("rascunho-invalido-*.json"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), "JSON interrompido")
            self.assertEqual(json.loads(arquivo.read_text(encoding="utf-8"))["dados"]["ticket"], "123")


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = GeradorIA_NOC(self.root, Config(Path(self.pasta.name), api_key="teste"))
        self.aguardar(lambda: not self.app.carregando)

    def aguardar(self, predicado, timeout=5):
        limite = time.monotonic() + timeout
        while not predicado() and time.monotonic() < limite:
            self.root.update()
            time.sleep(0.005)
        self.assertTrue(predicado(), "A interface não concluiu a operação no prazo do teste")

    def tearDown(self):
        self.app.fechar()
        self.aguardar(lambda: not self.app.movidesk.is_alive() and not self.app.rascunho.is_alive())
        if self.app.poll_after:
            self.root.after_cancel(self.app.poll_after)
        if self.root.tk.call("info", "commands", "."):
            self.root.destroy()
        self.pasta.cleanup()

    def test_ia_lenta_mantem_event_loop_e_impede_disparo_duplicado(self):
        liberar = threading.Event()
        iniciou = threading.Event()
        threads = []

        def ia_lenta(*_, **kwargs):
            threads.append(threading.get_ident())
            iniciou.set()
            if not liberar.wait(5):
                raise TimeoutError("Teste excedeu o prazo")
            return {"alerta": "Disco cheio", "servidor": "host-02", "severidade": "Alta", "situacao": "95%", "horario": "12:30"}

        self.app.definir_dados(dados_incidente(link_zabbix="https://zabbix.test/event/1", acionamento="Equipe antiga"))
        self.app.definir_imagem(Image.new("RGB", (10, 10)))
        heartbeat = []
        try:
            with patch("app_noc.extrair_dados", side_effect=ia_lenta) as mock_ia:
                self.app.extrair_com_ia()
                self.app.extrair_com_ia()
                self.root.after(10, lambda: heartbeat.append(True))
                self.aguardar(lambda: iniciou.is_set() and bool(heartbeat))
                self.assertIsNotNone(self.app.operacao)
                self.assertEqual(mock_ia.call_count, 1)
                self.assertNotEqual(threads[0], threading.get_ident())
                self.assertEqual(str(self.app.btn_ia["state"]), "disabled")
                liberar.set()
                self.aguardar(lambda: self.app.operacao is None)
        finally:
            liberar.set()
        dados = self.app.obter_dados()
        self.assertEqual(dados["alerta"], "Disco cheio")
        self.assertEqual(dados["situacao"], "95%")
        self.assertEqual(dados["ticket"], "")
        self.assertEqual(dados["link_zabbix"], "")
        self.assertEqual(dados["acionamento"], "")

    def test_falha_ia_libera_controles_e_preserva_print(self):
        imagem = Image.new("RGB", (10, 10), "blue")
        with patch("app_noc.ImageGrab.grabclipboard", return_value=imagem), patch("app_noc.extrair_dados", side_effect=TimeoutError("Tempo excedido")), self.assertLogs("noc", level="ERROR"):
            self.app.extrair_com_ia()
            self.aguardar(lambda: self.app.operacao is None)
        self.assertIn("Tempo excedido", self.app.status.get())
        self.assertIsNotNone(self.app.imagem)
        self.assertEqual(str(self.app.btn_ia["state"]), "normal")

    def test_interface_mostra_groq_apos_ocr_incompleto(self):
        from google.api_core.exceptions import ServiceUnavailable

        self.app.config = replace(self.app.config, groq_api_key="groq-teste")
        self.app.definir_imagem(Image.new("RGB", (10, 10)))
        resposta = json.dumps({"alerta": "CPU alta", "servidor": "host-01", "severidade": "Alta", "situacao": "95%", "horario": "10:42"})
        with patch("noc_services.consultar_gemini", side_effect=ServiceUnavailable("alta demanda")), patch("ocr_windows.extrair_texto", return_value="CPU alta host-01"), patch("noc_services.consultar_groq", return_value=resposta):
            self.app.extrair_com_ia()
            self.aguardar(lambda: self.app.operacao is None)
        self.assertIn("Groq", self.app.status.get())
        self.assertIn("OCR local", self.app.status.get())
        self.assertEqual(self.app.obter_dados()["servidor"], "host-01")
        self.assertEqual(str(self.app.btn_ia["state"]), "normal")

    def test_novo_incidente_e_desfazer_restauram_print_e_dados(self):
        dados = dados_incidente()
        imagem = Image.new("RGB", (10, 10))
        self.app.definir_dados(dados)
        self.app.definir_imagem(imagem)
        self.app.novo_incidente()
        self.assertFalse(any(self.app.obter_dados().values()))
        self.assertIsNone(self.app.imagem)
        self.app.desfazer_novo()
        self.assertEqual(self.app.obter_dados(), dados)
        self.assertIs(self.app.imagem, imagem)

    def test_retorno_ticket_atualiza_incidente_original_apos_trocar_fila(self):
        from incidentes import importar_eventos
        eventos = [{"eventid": str(i), "alerta": "CPU alta", "servidor": "host-01", "link_zabbix": f"https://zabbix.test/tr_events.php?eventid={i}"} for i in (10, 11)]
        self.app.aplicar_importacao(importar_eventos({"versao": 1, "origem": "zabbix", "eventos": eventos}))
        primeiro = self.app.fila.ativo
        self.app.navegar_fila(1)
        segundo = self.app.fila.ativo
        self.app.vars["situacao"].set("99%")
        self.app.eventos.put(("ticket_recebido", primeiro, {"ticket": "456", "url": "https://grupohda.movidesk.com/Ticket/Edit/456"}))
        self.aguardar(lambda: self.app.fila.obter(primeiro)["dados"]["ticket"] == "456")
        self.assertEqual(self.app.fila.ativo, segundo)
        self.assertEqual(self.app.obter_dados()["ticket"], "")
        self.assertEqual(self.app.obter_dados()["situacao"], "99%")
        self.app.navegar_fila(-1)
        self.assertEqual(self.app.obter_dados()["ticket"], "456")

    def test_importacao_externa_aguarda_operacao_sem_sobrescrever_campos(self):
        from incidentes import importar_eventos
        id_op = self.app.iniciar_operacao("ia", "Teste")
        evento = importar_eventos({"versao": 1, "origem": "zabbix", "link_zabbix": "https://zabbix.test/tr_events.php?eventid=10", "alerta": "CPU alta", "servidor": "host-01"})
        self.app.eventos.put(("zabbix_importado", None, evento))
        self.aguardar(lambda: bool(self.app.importacoes_pendentes))
        self.assertEqual(self.app.obter_dados()["servidor"], "")
        self.app.eventos.put(("erro", id_op, "Teste concluído"))
        self.aguardar(lambda: self.app.obter_dados()["servidor"] == "host-01")
        self.assertEqual(self.app.fila.obter()["meta"]["eventid"], "10")

    def test_ocr_local_sem_chaves_funciona_pela_interface(self):
        self.app.config = replace(self.app.config, api_key="", groq_api_key="")
        self.app.definir_imagem(Image.new("RGB", (10, 10)))
        with patch("ocr_windows.extrair_texto", return_value="Host: local-01\nTrigger: CPU alta"), patch("noc_services.consultar_gemini") as gemini, patch("noc_services.consultar_groq") as groq:
            self.app.extrair_com_ia(False)
            self.aguardar(lambda: self.app.operacao is None)
            self.assertEqual(self.app.obter_dados()["servidor"], "local-01")
            gemini.assert_not_called()
            groq.assert_not_called()

    def test_evento_consumo_nao_encerra_operacao_e_atualiza_painel(self):
        identificador = self.app.iniciar_operacao("ia", "Analisando")
        dados = {"provedor": "Groq", "horario": "10:42:00", "entrada": 100, "saida": 50, "total": 150, "cotas": {}}
        self.app.mostrar_tokens()
        self.app.eventos.put(("ia_consumo", identificador, dados))
        self.aguardar(lambda: "Total: 150" in self.app.resumo_tokens.get())
        self.assertIsNotNone(self.app.operacao)
        self.app.eventos.put(("erro", identificador, "Resposta truncada"))
        self.aguardar(lambda: self.app.operacao is None)
        self.assertIn("Total: 150", self.app.resumo_tokens.get())

    def test_assunto_email_atualiza_e_valida_ticket_antes_de_copiar(self):
        self.app.definir_dados(dados_incidente())
        self.assertEqual(self.app.assunto_email.get(), "123 - CPU alta - host-01")
        self.app.vars["ticket"].set("456")
        with patch("app_noc.pyperclip.copy") as copiar:
            self.app.copiar_assunto_email()
            copiar.assert_called_once_with("456 - CPU alta - host-01")
        self.app.vars["ticket"].set("")
        with patch("app_noc.pyperclip.copy") as copiar:
            self.app.copiar_assunto_email()
            copiar.assert_not_called()
        self.assertIn("Preencha", self.app.erros["ticket"].get())

    def test_copia_recortes_em_worker_e_novo_print_limpa_selecoes(self):
        imagem = Image.new("RGB", (100, 100), "blue")
        self.app.definir_imagem(imagem)
        self.app.recortes_email = {"Host": (0, 0, 50, 10), "Trigger": (0, 20, 80, 30), "Severity": (0, 40, 30, 50)}
        self.app.atualizar_controles()
        recebidas = []
        def copiar(recorte, hwnd):
            recebidas.append((recorte.size, threading.get_ident()))
        with patch("app_noc.copiar_imagem", side_effect=copiar):
            self.app.copiar_imagem_email()
            self.aguardar(lambda: self.app.operacao is None)
        self.assertEqual(recebidas[0][0], (80, 42))
        self.assertNotEqual(recebidas[0][1], threading.get_ident())
        self.assertIs(self.app.imagem, imagem)
        self.assertIn("Recorte copiado", self.app.status.get())
        self.app.definir_imagem(Image.new("RGB", (50, 50)))
        self.assertEqual(self.app.recortes_email, {})
        self.assertEqual(str(self.app.btn_imagem_email["state"]), "disabled")

    def test_arquivo_copiado_nao_e_tratado_como_imagem(self):
        with patch("app_noc.ImageGrab.grabclipboard", return_value=["arquivo.png"]):
            with self.assertRaisesRegex(ValueError, "Win\\+Shift\\+S"):
                self.app.ler_clipboard()

    def test_fechar_durante_ia_nao_espera_rede_nem_aplica_resultado_tardio(self):
        liberar = threading.Event()
        iniciou = threading.Event()
        threads = []

        def ia_lenta(*_, **kwargs):
            threads.append(threading.current_thread())
            iniciou.set()
            liberar.wait(5)
            return {"alerta": "Resultado tardio", "servidor": "outro-host"}

        self.app.definir_dados(dados_incidente())
        self.app.definir_imagem(Image.new("RGB", (10, 10)))
        try:
            with patch("app_noc.extrair_dados", side_effect=ia_lenta):
                self.app.extrair_com_ia()
                self.aguardar(iniciou.is_set)
                self.app.fechar()
                self.aguardar(lambda: not self.root.tk.call("info", "commands", "."), timeout=3)
                self.assertTrue(threads[0].is_alive())
        finally:
            liberar.set()
            for thread in threads:
                thread.join(timeout=3)
        salvo = json.loads((Path(self.pasta.name) / ".noc_data/rascunho.json").read_text(encoding="utf-8"))
        self.assertEqual(salvo["dados"]["alerta"], "CPU alta")

    def test_falha_ao_salvar_no_fechamento_permite_manter_janela_e_dados(self):
        self.app.definir_dados(dados_incidente())
        self.app.rascunho.permitir_salvamento = False
        try:
            with patch("app_noc.messagebox.askyesno", return_value=False) as confirmar, self.assertLogs("noc", level="ERROR"):
                self.app.fechar()
                self.aguardar(lambda: not self.app.fechando)
            confirmar.assert_called_once()
            self.assertEqual(self.app.obter_dados()["ticket"], "123")
            self.assertTrue(self.app.rascunho.is_alive())
            self.assertTrue(self.app.movidesk.is_alive())
        finally:
            self.app.rascunho.permitir_salvamento = True


if __name__ == "__main__":
    unittest.main()
