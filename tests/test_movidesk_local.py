"""Integração real da extensão com cookies preexistentes e servidor local."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import shutil
import tempfile
import threading
import time
import unittest

from playwright.sync_api import sync_playwright

from edge_bridge import EdgeBridge
from noc_services import CAMPOS, Config, MovideskWorker


FORMULARIO = b"""<html><body><input id="TicketSubject">
<iframe class="tox-edit-area__iframe" srcdoc="<html><body contenteditable='true'></body></html>"></iframe>
<script>window.addEventListener('load', () => {
  const frame = document.querySelector('iframe');
  frame.contentDocument.body.addEventListener('change', () => {
    fetch('/resultado', {method: 'POST', body: JSON.stringify({
      assunto: document.querySelector('input').value,
      texto: frame.contentDocument.body.innerText,
      scripts: frame.contentDocument.querySelectorAll('script').length,
      injetado: Boolean(frame.contentWindow.injetado)
    })});
  });
});</script></body></html>"""

EVENTO = b"""<html><body><table><tr><td>Host</td><td>host-zabbix</td></tr>
<tr><td>Trigger</td><td>CPU alta</td></tr><tr><td>Severity</td><td>High</td></tr>
<tr><td>Operational data</td><td>95%</td></tr><tr><td>Time</td><td>10:42</td></tr></table></body></html>"""


@unittest.skipUnless(os.getenv("NOC_TEST_BROWSER") == "1", "Defina NOC_TEST_BROWSER=1 para testar a extensão no Chromium")
class MovideskLocalTests(unittest.TestCase):
    def test_extensao_reutiliza_login_e_mantem_guias_apos_fechar_aplicativo(self):
        resultados = queue.Queue()
        cookies = queue.Queue()
        login = threading.Event()
        login.set()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                cookie = self.headers.get("Cookie", "")
                if self.path == "/Ticket/Create":
                    cookies.put(cookie)
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                corpo = EVENTO if self.path.startswith("/tr_events.php") else FORMULARIO
                self.wfile.write(corpo if login.is_set() and "sessao=ja-logado" in cookie else b"<html><body>Login pendente</body></html>")

            def do_POST(self):
                resultados.put(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                self.send_response(200)
                self.end_headers()

        servidor = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        servidor_thread = threading.Thread(target=servidor.serve_forever, daemon=True)
        servidor_thread.start()
        ponte = EdgeBridge(porta=0)
        ponte.iniciar()
        eventos = queue.Queue()
        aberturas = queue.Queue()

        def aguardar_evento(tipo, timeout=20):
            limite = time.monotonic() + timeout
            while time.monotonic() < limite:
                evento = eventos.get(timeout=max(0.01, limite - time.monotonic()))
                if evento[0] == "erro":
                    self.fail(evento[2])
                if evento[0] == tipo:
                    return evento
            self.fail(f"Evento {tipo} não recebido")

        try:
            with tempfile.TemporaryDirectory() as pasta, sync_playwright() as playwright:
                raiz = Path(pasta)
                extensao = raiz / "extensao"
                shutil.copytree(Path(__file__).resolve().parents[1] / "edge_extension", extensao)
                # Só a fixture local recebe permissão extra; a extensão distribuída usa Movidesk.
                manifest = json.loads((extensao / "manifest.json").read_text(encoding="utf-8"))
                manifest["content_scripts"][1]["matches"].append("http://127.0.0.1/*")
                manifest["content_scripts"][2]["matches"].append("http://127.0.0.1/*")
                (extensao / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
                for nome in ("background.js", "bridge.js"):
                    arquivo = extensao / nome
                    arquivo.write_text(arquivo.read_text(encoding="utf-8").replace("http://127.0.0.1:18764", ponte.url).replace("https://monitoramento.noc.dataside.com.br", f"http://127.0.0.1:{servidor.server_port}"), encoding="utf-8")
                # Edge restringe --load-extension; o Chromium testa a mesma extensão MV3.
                navegador = playwright.chromium.launch_persistent_context(
                    str(raiz / "perfil"), channel="chromium", headless=True,
                    args=[f"--disable-extensions-except={extensao}", f"--load-extension={extensao}"],
                )
                worker = MovideskWorker(Config(raiz, movidesk_url=f"http://127.0.0.1:{servidor.server_port}", timeout_login=25), eventos, abrir=aberturas.put, ponte=ponte)
                try:
                    if not navegador.service_workers:
                        navegador.wait_for_event("serviceworker", timeout=10000)
                    navegador.add_cookies([{"name": "sessao", "value": "ja-logado", "url": f"http://127.0.0.1:{servidor.server_port}"}])
                    existente = navegador.new_page()
                    existente.goto(f"http://127.0.0.1:{servidor.server_port}/")
                    worker.start()
                    dados = dict.fromkeys(CAMPOS, "")
                    dados.update(alerta='CPU ` ${window.injetado=true} <script>erro</script>', servidor="host-01", horario="10:42")
                    worker.comandos.put((1, dados))
                    pagina = navegador.new_page()
                    pagina.goto(aberturas.get(timeout=5))
                    aguardar_evento("movidesk_ok")
                    recebido = resultados.get(timeout=5)
                    self.assertIn("sessao=ja-logado", cookies.get(timeout=5))
                    self.assertEqual(recebido["assunto"], f"{dados['alerta']} - host-01")
                    self.assertIn(dados["alerta"], recebido["texto"])
                    self.assertIn("10:42", recebido["texto"])
                    self.assertEqual(recebido["scripts"], 0)
                    self.assertFalse(recebido["injetado"])
                    worker.comandos.put((2, {**dados, "alerta": "Segundo incidente"}))
                    segunda = navegador.new_page()
                    segunda.goto(aberturas.get(timeout=5))
                    aguardar_evento("movidesk_ok")
                    self.assertEqual(resultados.get(timeout=5)["assunto"], "Segundo incidente - host-01")
                    self.assertFalse(pagina.is_closed())
                    # Salva fora de ordem: cada token retorna para o incidente de origem.
                    segunda.evaluate("history.pushState({}, '', '/Ticket/Edit/456')")
                    retorno = aguardar_evento("ticket_recebido")
                    self.assertEqual(retorno[1], "2")
                    self.assertEqual(retorno[2]["ticket"], "456")
                    pagina.goto(f"http://127.0.0.1:{servidor.server_port}/Ticket/Edit/123")
                    retorno = aguardar_evento("ticket_recebido")
                    self.assertEqual(retorno[1], "1")
                    self.assertEqual(retorno[2]["ticket"], "123")
                    # Conecta e importa um evento pela extensão real, sem clipboard/API de IA.
                    worker.comandos.put((4, {"_conectar": True}))
                    conexao = navegador.new_page()
                    conexao.goto(aberturas.get(timeout=5))
                    aguardar_evento("conexao_ok")
                    zabbix = navegador.new_page()
                    zabbix.goto(f"http://127.0.0.1:{servidor.server_port}/tr_events.php?triggerid=1&eventid=99")
                    zabbix.locator("#noc-zabbix summary").click()
                    zabbix.get_by_role("button", name="Enviar ao NOC", exact=True).click()
                    recebido = aguardar_evento("zabbix_importado")
                    self.assertEqual(recebido[2][0]["meta"]["eventid"], "99")
                    self.assertEqual(recebido[2][0]["dados"]["servidor"], "host-zabbix")
                    # Encerramento durante espera cancela o pedido sem fechar o browser.
                    login.clear()
                    worker.comandos.put((3, dados))
                    terceira = navegador.new_page()
                    terceira.goto(aberturas.get(timeout=5))
                    worker.encerrar.set()
                    worker.join(timeout=5)
                    self.assertFalse(worker.is_alive())
                    self.assertFalse(existente.is_closed())
                    self.assertFalse(segunda.is_closed())
                    self.assertIn("Segundo incidente", segunda.locator("input").input_value())
                finally:
                    worker.encerrar.set()
                    if worker.ident:
                        worker.join(timeout=5)
                    navegador.close()
        finally:
            ponte.fechar()
            servidor.shutdown()
            servidor.server_close()
            servidor_thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
