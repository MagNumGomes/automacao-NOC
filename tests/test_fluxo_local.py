import json
import os
from pathlib import Path
import queue
import tempfile
import unittest

from PIL import Image

from extracao_local import interpretar_ocr, texto_relevante
from incidentes import FilaIncidentes, importar_eventos
from noc_services import Config, RascunhoWorker
from ocr_windows import organizar_palavras


def evento(eventid="10", dominio="https://zabbix.test", **campos):
    return {"versao": 1, "origem": "zabbix", "eventid": eventid, "alerta": "CPU alta", "servidor": "host-01",
            "situacao": "95%", "link_zabbix": f"{dominio}/tr_events.php?triggerid=1&eventid={eventid}", **campos}


class ImportacaoTests(unittest.TestCase):
    def test_mesmo_host_trigger_com_novo_eventid_e_instancia_nao_reusa_ticket(self):
        fila = FilaIncidentes()
        primeiro = fila.importar(importar_eventos(evento()))[0]
        fila.obter(primeiro)["dados"]["ticket"] = "123"
        fila.obter(primeiro)["imagem"] = Image.new("RGB", (2, 2))
        fila.importar(importar_eventos(evento(situacao="99%")))
        self.assertEqual(len(fila.itens), 1)
        self.assertEqual(fila.obter(primeiro)["dados"]["situacao"], "99%")
        self.assertEqual(fila.obter(primeiro)["dados"]["ticket"], "123")
        self.assertIsNotNone(fila.obter(primeiro)["imagem"])
        segundo = fila.importar(importar_eventos(evento("11")))[0]
        terceiro = fila.importar(importar_eventos(evento(dominio="https://outro.test")))[0]
        self.assertEqual(len(fila.itens), 3)
        self.assertEqual(fila.obter(segundo)["dados"]["ticket"], "")
        self.assertEqual(fila.obter(terceiro)["dados"]["ticket"], "")

    def test_formato_valores_e_identidade_sao_validados_antes_de_importar(self):
        invalidos = [[], {"versao": 2, "origem": "zabbix"}, evento(eventid="99", link_zabbix="https://zabbix.test/tr_events.php?eventid=10"),
                     evento(alerta=[]), evento(link_zabbix="javascript:alert(1)"), evento(link_zabbix="https://user:senha@zabbix.test/tr_events.php?eventid=10"),
                     {"versao": 1, "origem": "zabbix", "eventos": [evento()] * 101}]
        for valor in invalidos:
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                importar_eventos(json.dumps(valor))

    def test_fila_imagens_e_ativo_sobrevivem_ao_reinicio(self):
        with tempfile.TemporaryDirectory() as pasta:
            fila = FilaIncidentes()
            ids = fila.importar(importar_eventos({"versao": 1, "origem": "zabbix", "eventos": [evento(), evento("11")]}))
            fila.ativo = ids[1]
            fila.obter(ids[0])["dados"]["ticket"] = "123"
            fila.obter(ids[0])["imagem"] = Image.new("RGB", (2, 2), "red")
            fila.obter()["imagem"] = Image.new("RGB", (3, 3), "blue")
            config = Config(Path(pasta))
            worker = RascunhoWorker(config, queue.Queue())
            worker.start()
            worker.comandos.put((1, fila.obter()["dados"], fila.obter()["imagem"], fila.snapshot()))
            worker.comandos.put(None)
            worker.join(timeout=5)
            restaurador = RascunhoWorker(config, queue.Queue())
            restaurador.carregar()
            recuperada = FilaIncidentes()
            recuperada.restaurar(restaurador.fila_carregada)
            self.assertEqual(recuperada.ativo, ids[1])
            self.assertEqual(recuperada.obter(ids[0])["dados"]["ticket"], "123")
            self.assertEqual(recuperada.obter(ids[0])["imagem"].getpixel((0, 0)), (255, 0, 0))
            self.assertEqual(recuperada.obter()["imagem"].size, (3, 3))

    def test_rascunho_v1_continua_legivel(self):
        with tempfile.TemporaryDirectory() as pasta:
            config = Config(Path(pasta))
            config.dados_dir.mkdir()
            (config.dados_dir / "rascunho.json").write_text(json.dumps({"versao": 1, "dados": {"alerta": "CPU", "ticket": "123"}}), encoding="utf-8")
            worker = RascunhoWorker(config, queue.Queue())
            self.assertEqual(worker.carregar()[0]["ticket"], "123")
            self.assertIsNone(worker.fila_carregada)


class ParserOCRTests(unittest.TestCase):
    def test_rotulos_portugues_multilinha_e_horario_invalido(self):
        dados, ambiguos = interpretar_ocr("Servidor: host-01\nGatilho: CPU alta\nSeveridade: Alta\nDados operacionais:\nCPU 95%\nRAM 80%\nHorário: 29:80\nStatus: PROBLEM")
        self.assertEqual(dados["situacao"], "CPU 95%\nRAM 80%")
        self.assertEqual(dados["horario"], "")
        self.assertIn("horario", ambiguos)

    def test_valores_conflitantes_nao_sao_escolhidos_arbitrariamente(self):
        dados, ambiguos = interpretar_ocr("Host: host-01\nTrigger: CPU alta\nHost: host-02\nTime: 10:42")
        self.assertEqual(dados["servidor"], "")
        self.assertIn("servidor", ambiguos)
        self.assertEqual(dados["alerta"], "CPU alta")

    def test_colunas_reconstruidas_pelas_coordenadas(self):
        texto = organizar_palavras([("host-01", 200, 10, 80, 20), ("Trigger", 0, 40, 60, 20), ("Host", 0, 10, 40, 20), ("CPU", 200, 40, 30, 20), ("alta", 236, 40, 35, 20)])
        dados, _ = interpretar_ocr(texto)
        self.assertEqual(dados["servidor"], "host-01")
        self.assertEqual(dados["alerta"], "CPU alta")

    def test_contexto_da_ia_remove_navegacao_e_rejeita_excesso(self):
        self.assertEqual(texto_relevante("Menu\nPainel\nHost: host-01"), "Host: host-01")
        with self.assertRaises(ValueError):
            texto_relevante("Host: " + "a" * 9000)


@unittest.skipUnless(os.getenv("NOC_TEST_BROWSER") == "1", "Defina NOC_TEST_BROWSER=1 para fixtures DOM")
class ColetorDOMTests(unittest.TestCase):
    def test_imagem_carrega_sob_demanda_e_reutiliza_renderizacao(self):
        from playwright.sync_api import sync_playwright
        raiz = Path(__file__).resolve().parents[1]
        html = """<html><body style='background:white;color:black'><table><tbody>
        <tr><td>Host</td><td>host-01</td></tr><tr><td>Trigger</td><td>CPU alta</td></tr>
        <tr><td>Severity</td><td>High</td></tr><tr><td>Operational data</td><td>95%</td></tr></tbody></table></body></html>"""
        carregamentos = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chromium", headless=True)
            try:
                page = browser.new_page()
                page.route("https://zabbix.test/**", lambda route: route.fulfill(body=html, content_type="text/html"))
                def renderizador(route):
                    carregamentos.append(True)
                    route.fulfill(body=(raiz / "edge_extension/vendor/html2canvas.min.js").read_text(encoding="utf-8"), content_type="application/javascript")
                page.route("https://cdnjs.cloudflare.com/**", renderizador)
                page.goto("https://zabbix.test/tr_events.php?eventid=10")
                page.evaluate("""() => {
                  window.copias = [];
                  Object.defineProperty(navigator, 'clipboard', {value: {write: async items => {window.copias.push(await items[0].getType('image/png'));}, writeText: async texto => {window.textoCopiado = texto;}}});
                }""")
                for nome in ("coletor.js", "zabbix.js"):
                    page.add_script_tag(content=(raiz / "edge_extension" / nome).read_text(encoding="utf-8"))
                page.locator("#noc-zabbix summary").click()
                page.get_by_role("button", name="Copiar dados para NOC", exact=True).click()
                page.wait_for_function("Boolean(window.textoCopiado)")
                self.assertFalse(carregamentos)
                botao = page.get_by_role("button", name="Copiar imagem Host / Trigger / Severity", exact=True)
                botao.click()
                page.wait_for_function("window.copias.length === 1")
                self.assertEqual(len(carregamentos), 1)
                page.evaluate("""() => {const original = window.html2canvas; window.renderizacoes = 0; window.html2canvas = (...args) => {window.renderizacoes++; return original(...args);};}""")
                botao.click()
                page.wait_for_function("window.copias.length === 2")
                self.assertEqual(page.evaluate("window.renderizacoes"), 0)
                page.locator("td").nth(1).evaluate("el => el.textContent = 'host-02'")
                botao.click()
                page.wait_for_function("window.copias.length === 3")
                self.assertEqual(page.evaluate("window.renderizacoes"), 1)
                self.assertGreater(page.evaluate("window.copias[0].size"), 100)
            finally:
                browser.close()

    def test_layouts_rotulos_selecao_e_busca_so_detalhes_ausentes(self):
        from playwright.sync_api import sync_playwright
        fonte = (Path(__file__).resolve().parents[1] / "edge_extension/coletor.js").read_text(encoding="utf-8")
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chromium", headless=True)
            try:
                page = browser.new_page()
                page.set_content("""<table><tbody><tr><td>irrelevante</td><td>12345</td></tr></tbody></table>
                <table><tbody><tr><th>Host:</th><td>host-01</td></tr><tr><th>Trigger:</th><td>CPU &lt; 5 &amp; alta</td></tr>
                <tr><th>Severity:</th><td>High</td></tr><tr><th>Operational data:</th><td>CPU 95%<br>RAM 80%</td></tr>
                <tr><th>Time:</th><td>2026-10-16 10:42:00</td></tr></tbody></table>""")
                page.add_script_tag(content=fonte)
                dados = page.evaluate("NocZabbix.extrair(document, 'https://zabbix.test/tr_events.php?eventid=10')")
                self.assertEqual(dados["servidor"], "host-01")
                self.assertEqual(dados["alerta"], "CPU < 5 & alta")
                self.assertIn("RAM 80%", dados["situacao"])
                self.assertEqual(page.evaluate("NocZabbix.numeroChamado(document)"), "")
                page.set_content("""<table><thead><tr><th>Select</th><th>Time</th><th>Host</th><th>Problem</th><th>Severity</th><th>Operational data</th></tr></thead>
                <tbody><tr><td><input type='checkbox' checked></td><td><a href='/tr_events.php?eventid=10'>10:42</a></td><td>host-01</td><td>CPU</td><td>High</td><td>95%</td></tr>
                <tr><td><input type='checkbox'></td><td><a href='/tr_events.php?eventid=11'>10:43</a></td><td>host-02</td><td>RAM</td><td>High</td><td></td></tr></tbody></table>""")
                page.evaluate("NocZabbix.selecionar(document, 'https://zabbix.test/zabbix.php?action=problem.view', 2)")
                self.assertEqual(page.locator("input:checked").count(), 2)
                resultado = page.evaluate("""async () => {
                  let chamadas = 0;
                  const eventos = NocZabbix.selecionados(document, 'https://zabbix.test/zabbix.php?action=problem.view');
                  const dados = await NocZabbix.completar(eventos, async url => { chamadas++; return {ok:true, url, text: async () => '<table><tr><td>Operational data</td><td>RAM 99%<br>CPU 90%</td></tr></table>'}; });
                  return {chamadas, dados};
                }""")
                self.assertEqual(resultado["chamadas"], 1)
                self.assertEqual(resultado["dados"][1]["situacao"], "RAM 99%\nCPU 90%")
            finally:
                browser.close()


class UserscriptsTests(unittest.TestCase):
    def test_artefatos_distribuidos_correspondem_as_fontes(self):
        from gerar_userscripts import artefatos, RAIZ
        for nome, esperado in artefatos():
            self.assertEqual((RAIZ / "tampermonkey" / nome).read_text(encoding="utf-8"), esperado)
