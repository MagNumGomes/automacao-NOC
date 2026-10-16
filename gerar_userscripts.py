"""Gera os userscripts a partir dos mesmos coletores usados na extensão."""

from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def artefatos():
    for nome, descricao, matches, arquivos in (
        ("Zabbix", "Coleta local de eventos, seleção em lote e imagens sob demanda", ["https://monitoramento.noc.dataside.com.br/*", "https://crz.extras.tools.dataside.com.br/*"], ["coletor.js", "zabbix.js"]),
        ("Movidesk", "Copia número, assunto, link e template sem polling periódico", ["https://*.movidesk.com/*"], ["movidesk.js"]),
    ):
        cabecalho = "\n".join([
            "// ==UserScript==", f"// @name         NOC - {nome} - Local", "// @namespace    automacao-noc",
            "// @version      2.0.0", f"// @description  {descricao}",
            *(f"// @match        {match}" for match in matches),
            "// @grant        none", "// @run-at       document-idle", "// ==/UserScript==", "",
            "// Gerado por gerar_userscripts.py; edite as fontes em edge_extension/.", "",
        ])
        yield f"NOC-{nome}.user.js", cabecalho + "\n".join((RAIZ / "edge_extension" / a).read_text(encoding="utf-8") for a in arquivos)


if __name__ == "__main__":
    destino = RAIZ / "tampermonkey"
    destino.mkdir(exist_ok=True)
    for nome, conteudo in artefatos():
        (destino / nome).write_text(conteudo, encoding="utf-8", newline="\n")
        print(nome)
