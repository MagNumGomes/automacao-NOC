// ==UserScript==
// @name         NOC - Zabbix - Local
// @namespace    automacao-noc
// @version      2.0.0
// @description  Coleta local de eventos, seleção em lote e imagens sob demanda
// @match        https://monitoramento.noc.dataside.com.br/*
// @match        https://crz.extras.tools.dataside.com.br/*
// @grant        none
// @run-at       document-idle
// ==/UserScript==

// Gerado por gerar_userscripts.py; edite as fontes em edge_extension/.
/* Coletor compartilhado pela extensão, userscript e fixtures de navegador. */
(() => {
  const campos = ["alerta", "servidor", "severidade", "situacao", "horario"];
  const normalizar = texto => (texto || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ").trim().replace(/:$/, "").toLowerCase();
  const rotulos = {
    host: "servidor", servidor: "servidor", trigger: "alerta", "event name": "alerta", "nome do evento": "alerta",
    gatilho: "alerta", severity: "severidade", severidade: "severidade", "operational data": "situacao",
    "dados operacionais": "situacao", time: "horario", hora: "horario", horario: "horario"
  };
  function texto(el) {
    if (!el) return "";
    if (el.ownerDocument.defaultView && typeof el.innerText === "string") return el.innerText.replace(/\r/g, "").trim();
    const clone = el.cloneNode(true);
    for (const br of clone.querySelectorAll("br")) br.replaceWith("\n");
    for (const bloco of clone.querySelectorAll("p, div, li")) bloco.append("\n");
    for (const oculto of clone.querySelectorAll("script, style, [hidden]")) oculto.remove();
    return (clone.textContent || "").replace(/\r/g, "").trim();
  }
  function urlEvento(link, base) {
    try {
      const url = new URL(link, base);
      if (!/^https?:$/.test(url.protocol) || url.origin !== new URL(base).origin ||
          !/^\d+$/.test(url.searchParams.get("eventid") || "") || !url.pathname.endsWith("/tr_events.php")) return null;
      return url;
    } catch { return null; }
  }
  function linhasRotuladas(doc) {
    return Array.from(doc.querySelectorAll("tr")).flatMap(linha => {
      const celulas = Array.from(linha.cells);
      if (celulas.length !== 2) return [];
      const campo = rotulos[normalizar(texto(celulas[0]))];
      return campo ? [{campo, valor: texto(celulas[1]), linha}] : [];
    });
  }
  function extrair(doc, href) {
    const url = urlEvento(href, href);
    if (!url) throw new Error("Abra o detalhe de um evento Zabbix com eventid.");
    const dados = Object.fromEntries(campos.map(c => [c, ""]));
    const linhas = linhasRotuladas(doc);
    for (const campo of campos) {
      const valores = [...new Set(linhas.filter(l => l.campo === campo && l.valor).map(l => l.valor))];
      if (valores.length === 1) dados[campo] = valores[0];
    }
    // Alguns layouts mostram Time como cabeçalho na tabela de eventos.
    if (!dados.horario) {
      const candidatos = Array.from(doc.querySelectorAll("tr")).filter(l =>
        Array.from(l.querySelectorAll("a[href]")).some(a => urlEvento(a.getAttribute("href"), href)?.searchParams.get("eventid") === url.searchParams.get("eventid")));
      const horas = [...new Set(candidatos.flatMap(l => {
        const cabecalho = l.closest("table")?.querySelector("thead tr");
        const indice = Array.from(cabecalho?.cells || []).findIndex(c => rotulos[normalizar(texto(c))] === "horario");
        return indice >= 0 && l.cells[indice] ? [texto(l.cells[indice])] : [];
      }))];
      if (horas.length === 1) dados.horario = horas[0];
    }
    return {...dados, link_zabbix: url.href, eventid: url.searchParams.get("eventid")};
  }
  function selecionados(doc, href) {
    const eventos = new Map();
    for (const checkbox of doc.querySelectorAll('tbody input[type="checkbox"]:checked')) {
      const linha = checkbox.closest("tr");
      const url = Array.from(linha?.querySelectorAll("a[href]") || []).map(a => urlEvento(a.getAttribute("href"), href)).find(Boolean);
      if (!url) continue;
      const dados = Object.fromEntries(campos.map(c => [c, ""]));
      const cabecalhos = Array.from(linha.closest("table").querySelector("thead tr")?.cells || []);
      cabecalhos.forEach((c, indice) => {
        const nome = normalizar(texto(c));
        const campo = rotulos[nome] || ({problem: "alerta", problema: "alerta", problems: "alerta"})[nome];
        if (campo) dados[campo] = texto(linha.cells[indice]);
      });
      eventos.set(url.href, {...dados, link_zabbix: url.href, eventid: url.searchParams.get("eventid")});
    }
    if (!eventos.size) throw new Error("Selecione as linhas dos eventos na lista do Zabbix.");
    if (eventos.size > 100) throw new Error("Selecione no máximo 100 eventos por importação.");
    return [...eventos.values()];
  }
  async function completar(eventos, buscar = fetch) {
    const resultado = eventos.map(e => ({...e}));
    let indice = 0;
    async function trabalhar() {
      while (indice < resultado.length) {
        const evento = resultado[indice++];
        if (campos.every(c => evento[c])) continue;
        try {
          const resposta = await buscar(evento.link_zabbix, {credentials: "same-origin", signal: AbortSignal.timeout(8000)});
          if (!resposta.ok || new URL(resposta.url || evento.link_zabbix).origin !== new URL(evento.link_zabbix).origin) throw new Error("Detalhe indisponível");
          const doc = new DOMParser().parseFromString(await resposta.text(), "text/html");
          const detalhe = extrair(doc, evento.link_zabbix);
          for (const campo of campos) if (!evento[campo]) evento[campo] = detalhe[campo];
        } catch { evento.aviso = "Detalhe indisponível; revise os campos vazios no NOC."; }
      }
    }
    await Promise.all([trabalhar(), trabalhar()]);
    return resultado;
  }
  function selecionar(doc, href, quantidade) {
    if (!Number.isInteger(quantidade) || quantidade < 1 || quantidade > 100) throw new Error("Informe um número inteiro de 1 a 100.");
    const caixas = Array.from(doc.querySelectorAll('tbody input[type="checkbox"]')).filter(c =>
      !c.disabled && Array.from(c.closest("tr")?.querySelectorAll("a[href]") || []).some(a => urlEvento(a.getAttribute("href"), href)));
    for (const caixa of caixas.slice(0, quantidade)) if (!caixa.checked) caixa.click();
    return Math.min(quantidade, caixas.length);
  }
  function numeroChamado(doc) {
    // Procura somente no histórico de reconhecimentos, nunca em todos os números da página.
    const tabelas = Array.from(doc.querySelectorAll("table")).filter(t => {
      const cabecalho = normalizar(texto(t.querySelector("thead")));
      const contexto = texto(t.previousElementSibling) + " " + texto(t.closest("section, fieldset")?.querySelector("h2, h3, legend"));
      return /acknowledg|reconhec/i.test(cabecalho + " " + t.id + " " + contexto) ||
        (/message|mensagem|comment|comentario/.test(cabecalho) && /user|usuario/.test(cabecalho));
    });
    for (const tabela of tabelas) {
      const indice = Array.from(tabela.querySelector("thead tr")?.cells || []).findIndex(c => /^(?:message|mensagem|comment|comentario)$/.test(normalizar(texto(c))));
      const celulas = indice >= 0 ? Array.from(tabela.querySelectorAll("tbody tr")).map(l => l.cells[indice]) : Array.from(tabela.querySelectorAll(".message-cell, tbody tr td:nth-child(3)"));
      for (const celula of celulas) {
        const mensagem = texto(celula);
        const prefixado = mensagem.match(/\b(?:INC|CHG|TASK|REQ|SD|WO|TICKET)\d{5,}\b/i);
        const rotulado = mensagem.match(/\b(?:ticket|chamado|movidesk)\s*[:#-]?\s*(\d{5,})\b/i);
        if (prefixado) return prefixado[0];
        if (rotulado) return rotulado[1];
        if (/^\d{5,}$/.test(mensagem)) return mensagem;
      }
    }
    return "";
  }
  globalThis.NocZabbix = {campos, extrair, selecionados, completar, selecionar, linhasRotuladas, numeroChamado};
})();

(() => {
  if (document.getElementById("noc-zabbix")) return;
  const coletor = globalThis.NocZabbix;
  const extensao = typeof chrome !== "undefined" && Boolean(chrome.runtime?.id);
  const lista = new URL(location.href).searchParams.get("action") === "problem.view";
  if (!lista && !location.pathname.endsWith("/tr_events.php")) return;
  const painel = document.createElement("details");
  painel.id = "noc-zabbix";
  Object.assign(painel.style, {position: "fixed", bottom: "16px", left: "16px", zIndex: "2147483647", background: "#202630", color: "white", padding: "12px", borderRadius: "8px", font: "13px Segoe UI,sans-serif", maxWidth: "520px"});
  const titulo = document.createElement("summary");
  titulo.textContent = "NOC — dados locais, sem IA";
  titulo.style.cursor = "pointer";
  painel.append(titulo);
  const botoes = document.createElement("div");
  Object.assign(botoes.style, {display: "flex", flexWrap: "wrap", gap: "6px", marginTop: "10px"});
  const status = document.createElement("div");
  status.setAttribute("role", "status");
  status.style.marginTop = "8px";
  painel.append(botoes, status);
  document.body.append(painel);
  let ocupado = false, carregandoRenderizador, cacheImagem;
  function botao(nome, acao) {
    const el = document.createElement("button");
    el.type = "button";
    el.textContent = nome;
    Object.assign(el.style, {padding: "8px", cursor: "pointer", border: "1px solid #8793a3", borderRadius: "4px", background: "#303d50", color: "white"});
    el.onclick = async () => {
      if (ocupado) return;
      ocupado = true;
      for (const b of botoes.children) b.disabled = true;
      status.textContent = "Processando localmente…";
      try { status.textContent = await acao() || "Copiado."; }
      catch (erro) { status.textContent = erro.message || String(erro); }
      finally { ocupado = false; for (const b of botoes.children) b.disabled = false; }
    };
    botoes.append(el);
  }
  async function mensagem(dados) {
    const resposta = await chrome.runtime.sendMessage(dados);
    if (resposta?.erro) throw new Error(resposta.erro);
    return resposta;
  }
  async function payload() {
    const eventos = lista ? await coletor.completar(coletor.selecionados(document, location.href)) : [coletor.extrair(document, location.href)];
    return {versao: 1, origem: "zabbix", eventos};
  }
  botao(lista ? "Copiar selecionados para NOC" : "Copiar dados para NOC", async () => {
    await navigator.clipboard.writeText(JSON.stringify(await payload()));
    return "Dados copiados. Use Importar dados no aplicativo NOC.";
  });
  if (extensao) botao(lista ? "Enviar selecionados ao NOC" : "Enviar ao NOC", async () => {
    const dados = await payload();
    await mensagem({tipo: "importar_zabbix", payload: dados});
    return `${dados.eventos.length} evento(s) enviado(s) à fila do NOC.`;
  });
  if (lista) {
    botao("Selecionar primeiras N linhas", async () => {
      const valor = prompt("Quantas linhas selecionar? (1–100)", "4");
      if (valor === null) return "Cancelado.";
      return `${coletor.selecionar(document, location.href, Number(valor))} linha(s) selecionada(s).`;
    });
    botao("Copiar links selecionados", async () => navigator.clipboard.writeText(coletor.selecionados(document, location.href).map(e => e.link_zabbix).join("\n")));
    return;
  }
  botao("Copiar link", async () => navigator.clipboard.writeText(location.href));
  botao("Copiar Trigger - Host", async () => {
    const d = coletor.extrair(document, location.href);
    await navigator.clipboard.writeText(`${d.alerta} - ${d.servidor}`);
  });
  botao("Copiar chamado reconhecido", async () => {
    const numero = coletor.numeroChamado(document);
    if (!numero) throw new Error("Chamado não encontrado na tabela de reconhecimentos.");
    await navigator.clipboard.writeText(numero);
  });
  const template = d => `Prezados,\n\nRecebemos o seguinte alerta:\n\nN° do Ticket criado:\nAlerta: ${d.alerta}\nSeveridade: ${d.severidade}\nServidor: ${d.servidor}\nDados operacionais: ${d.situacao}\nHorário da Falha: ${d.horario}`;
  botao("Copiar template", async () => navigator.clipboard.writeText(template(coletor.extrair(document, location.href))));
  async function renderizador() {
    if (globalThis.html2canvas) return;
    if (!carregandoRenderizador) carregandoRenderizador = (async () => {
      if (extensao) await mensagem({tipo: "carregar_renderizador"});
      else await new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = "https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js";
        script.onload = resolve;
        script.onerror = () => reject(new Error("Não foi possível carregar o renderizador. A cópia de dados continua disponível."));
        document.head.append(script);
      });
    })().catch(erro => { carregandoRenderizador = null; throw erro; });
    await carregandoRenderizador;
  }
  async function imagem() {
    const linhas = coletor.linhasRotuladas(document);
    const selecionadas = ["servidor", "alerta", "severidade"].map(c => {
      const opcoes = linhas.filter(l => l.campo === c);
      if (new Set(opcoes.map(l => l.valor)).size > 1) throw new Error(`Mais de um valor de ${c} na página. Use Win+Shift+S para a evidência.`);
      return opcoes[0]?.linha;
    });
    if (selecionadas.some(l => !l)) throw new Error("Host, Trigger e Severity não foram localizados para a imagem.");
    const chave = location.href + selecionadas.map(l => l.outerHTML + [l, ...l.cells].map(el => {
      const s = getComputedStyle(el);
      return s.color + s.backgroundColor + s.font + el.getBoundingClientRect().width;
    }).join("")).join("") + devicePixelRatio;
    if (cacheImagem?.chave === chave) return cacheImagem.blob;
    await renderizador();
    const wrapper = document.createElement("div");
    const estilo = getComputedStyle(selecionadas[0].closest("table"));
    Object.assign(wrapper.style, {position: "fixed", left: "-20000px", top: "0", padding: "10px", background: getComputedStyle(document.body).backgroundColor, color: estilo.color, font: estilo.font});
    const tabela = selecionadas[0].closest("table").cloneNode(false);
    tabela.removeAttribute("id");
    tabela.style.width = `${Math.ceil(selecionadas[0].closest("table").getBoundingClientRect().width)}px`;
    const corpo = document.createElement("tbody");
    for (const linha of selecionadas) corpo.append(linha.cloneNode(true));
    tabela.append(corpo);
    wrapper.append(tabela);
    document.body.append(wrapper);
    try {
      const canvas = await globalThis.html2canvas(wrapper, {scale: devicePixelRatio || 1, backgroundColor: getComputedStyle(document.body).backgroundColor});
      const blob = await new Promise(resolve => canvas.toBlob(resolve, "image/png"));
      if (!blob) throw new Error("Não foi possível gerar a imagem.");
      cacheImagem = {chave, blob};
      return blob;
    } finally { wrapper.remove(); }
  }
  botao("Copiar imagem Host / Trigger / Severity", async () => navigator.clipboard.write([new ClipboardItem({"image/png": await imagem()})]));
  botao("Copiar e-mail + imagem", async () => {
    const blob = await imagem();
    const base64 = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = reject; reader.readAsDataURL(blob); });
    const texto = template(coletor.extrair(document, location.href));
    const div = document.createElement("div");
    const pre = document.createElement("div");
    pre.style.whiteSpace = "pre-wrap";
    pre.textContent = texto;
    const img = document.createElement("img");
    img.src = base64;
    div.append(pre, img);
    await navigator.clipboard.write([new ClipboardItem({"text/plain": new Blob([texto], {type: "text/plain"}), "text/html": new Blob([div.outerHTML], {type: "text/html"})})]);
  });
})();
