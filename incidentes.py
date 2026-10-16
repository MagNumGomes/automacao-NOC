"""Importação versionada e fila de eventos, sem rede e sem IA."""

import json
import uuid
from urllib.parse import parse_qs, urlsplit, urlunsplit

CAMPOS_EVENTO = ("alerta", "servidor", "severidade", "situacao", "horario")
CAMPOS_FORMULARIO = CAMPOS_EVENTO + ("link_zabbix", "ticket", "acionamento", "time_resp")
MAX_EVENTOS = 100
MAX_IMPORTACAO = 2_000_000


def identidade_evento(link):
    url = urlsplit(link)
    if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or any(c.isspace() for c in link):
        raise ValueError("O evento precisa de um link HTTP/HTTPS válido do Zabbix.")
    evento = parse_qs(url.query).get("eventid", [""])[0]
    if not evento.isascii() or not evento.isdigit():
        raise ValueError("O link do Zabbix precisa conter eventid numérico.")
    instancia = urlunsplit((url.scheme.lower(), url.netloc.lower(), url.path.rsplit("/", 1)[0], "", ""))
    return instancia, evento


def importar_eventos(conteudo):
    if isinstance(conteudo, str):
        if len(conteudo.encode("utf-8")) > MAX_IMPORTACAO:
            raise ValueError("Importação muito grande; limite de 2 MB.")
        try:
            conteudo = json.loads(conteudo)
        except ValueError:
            raise ValueError("Copie os dados JSON pelo botão do Zabbix antes de importar.") from None
    if not isinstance(conteudo, dict) or conteudo.get("versao") != 1 or conteudo.get("origem") != "zabbix":
        raise ValueError("Formato desconhecido. Use a exportação NOC versão 1 do Zabbix.")
    eventos = conteudo.get("eventos", [conteudo])
    if not isinstance(eventos, list) or not 1 <= len(eventos) <= MAX_EVENTOS:
        raise ValueError(f"Importe entre 1 e {MAX_EVENTOS} eventos por vez.")
    resultado = []
    for evento in eventos:
        if not isinstance(evento, dict):
            raise ValueError("Evento inválido na importação.")
        dados = {}
        for campo in CAMPOS_EVENTO + ("link_zabbix",):
            valor = evento.get(campo, "")
            if not isinstance(valor, str) or len(valor) > 30000:
                raise ValueError(f"Campo inválido ou muito extenso: {campo}.")
            dados[campo] = valor.strip()
        instancia, eventid = identidade_evento(dados["link_zabbix"])
        if evento.get("eventid", eventid) != eventid:
            raise ValueError("O eventid não corresponde ao link importado.")
        resultado.append({"dados": dados, "meta": {"origem": "DOM", "instancia": instancia, "eventid": eventid}})
    return resultado


class FilaIncidentes:
    def __init__(self):
        self.itens = []
        self.ativo = ""
        self.novo()

    def novo(self):
        item = {"id": uuid.uuid4().hex, "dados": dict.fromkeys(CAMPOS_FORMULARIO, ""), "meta": {}, "imagem": None}
        self.itens.append(item)
        self.ativo = item["id"]
        return item

    def obter(self, identificador=None):
        return next((i for i in self.itens if i["id"] == (identificador or self.ativo)), None)

    def importar(self, eventos):
        ids = []
        for evento in eventos:
            meta = evento["meta"]
            item = next((i for i in self.itens if (i["meta"].get("instancia"), i["meta"].get("eventid")) == (meta["instancia"], meta["eventid"])), None)
            if item is None:
                item = next((i for i in self.itens if not any(i["dados"].values()) and i["imagem"] is None and not i["meta"]), None)
                if item is None:
                    ativo = self.ativo
                    item = self.novo()
                    self.ativo = ativo
            # Uma recaptura atualiza os dados do evento, preservando ticket e encaminhamento.
            for campo, valor in evento["dados"].items():
                if valor or not item["dados"].get(campo):
                    item["dados"][campo] = valor
            item["meta"].update(meta)
            ids.append(item["id"])
        return list(dict.fromkeys(ids))

    def snapshot(self):
        return {"ativo": self.ativo, "itens": [{**i, "dados": dict(i["dados"]), "meta": dict(i["meta"])} for i in self.itens]}

    def restaurar(self, estado):
        if not isinstance(estado, dict) or not isinstance(estado.get("itens"), list) or not estado["itens"]:
            raise ValueError("Fila de incidentes inválida.")
        ids = set()
        for item in estado["itens"]:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"] or item["id"] in ids:
                raise ValueError("Identificador inválido na fila.")
            ids.add(item["id"])
            if not isinstance(item.get("dados"), dict) or any(not isinstance(item["dados"].get(c, ""), str) for c in CAMPOS_FORMULARIO):
                raise ValueError("Dados inválidos na fila.")
            if not isinstance(item.get("meta"), dict):
                raise ValueError("Metadados inválidos na fila.")
        if estado.get("ativo") not in ids:
            raise ValueError("Incidente ativo não encontrado na fila.")
        self.itens, self.ativo = estado["itens"], estado["ativo"]
