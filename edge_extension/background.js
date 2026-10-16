import {preencherFormulario} from "./preencher.js";

const PONTE = "http://127.0.0.1:18764";
const ZABBIX = new Set(["https://monitoramento.noc.dataside.com.br", "https://crz.extras.tools.dataside.com.br"]);
const chave = tabId => `noc:${tabId}`;
const emAndamento = new Set();

async function consultar(token) {
  const resposta = await fetch(`${PONTE}/api/request/${token}`, {
    headers: {"X-NOC-Token": token}, cache: "no-store", signal: AbortSignal.timeout(5000)
  });
  if (!resposta.ok) throw new Error("Pedido encerrado ou expirado. Conecte ou abra o ticket novamente pelo NOC.");
  return resposta.json();
}

async function informar(token, tipo, mensagem = "", extra = {}) {
  const resposta = await fetch(`${PONTE}/api/result/${token}`, {
    method: "POST", headers: {"Content-Type": "application/json", "X-NOC-Token": token},
    body: JSON.stringify({tipo, mensagem, ...extra}), signal: AbortSignal.timeout(5000)
  });
  if (!resposta.ok) throw new Error("Pedido expirado ou dados inválidos. Confira o NOC e conecte novamente.");
}

async function abrir(mensagem, sender) {
  const origem = new URL(sender.url);
  if (sender.frameId !== 0 || origem.origin !== PONTE || origem.pathname !== `/request/${mensagem.token}` ||
      !/^[A-Za-z0-9_-]{43}$/.test(mensagem.token)) throw new Error("Solicitação NOC inválida.");
  const dados = await consultar(mensagem.token);
  if (dados.tipo === "conectar") {
    await chrome.storage.session.set({conexaoNoc: {token: mensagem.token, expira: Date.now() + 43200000}});
    await informar(mensagem.token, "ok");
    return {mensagem: "NOC conectado. Use Enviar ao NOC nas páginas do Zabbix. Você pode fechar esta guia."};
  }
  const destino = new URL(dados.url);
  if (!["http:", "https:"].includes(destino.protocol)) throw new Error("Endereço do Movidesk inválido.");
  await chrome.storage.session.set({[chave(sender.tab.id)]: {
    token: mensagem.token, url: destino.href, fase: "preencher", expira: Date.now() + (dados.timeout_login || 120) * 1000,
    retorno: dados.timeout_retorno || 28800
  }});
  await informar(mensagem.token, "progresso", "Extensão conectada. Abrindo Movidesk na sua sessão do Edge…");
  await chrome.tabs.update(sender.tab.id, {url: destino.href, active: true});
  return {ok: true};
}

function numeroTicket(href, pedido) {
  const atual = new URL(href), destino = new URL(pedido.url);
  if (atual.origin !== destino.origin) return "";
  const base = destino.pathname.replace(/\/Ticket\/Create\/?$/i, "");
  const caminho = atual.pathname.slice(base.length);
  if (!atual.pathname.startsWith(base)) return "";
  const match = caminho.match(/^\/Ticket\/(?:Edit|Create)\/(\d+)\/?$/i);
  if (match) return match[1];
  if (/^\/Ticket\/(?:Edit|Create)\/?$/i.test(caminho)) {
    const id = atual.searchParams.get("id") || "";
    if (/^\d+$/.test(id)) return id;
  }
  return "";
}

async function preencher(sender) {
  if (sender.frameId !== 0) return {};
  const id = sender.tab.id;
  const pedido = (await chrome.storage.session.get(chave(id)))[chave(id)];
  if (!pedido) return {};
  if (emAndamento.has(id)) return {aguardar: true};
  emAndamento.add(id);
  try {
    if (Date.now() >= pedido.expira) throw new Error("Prazo do pedido encerrado. Informe o ticket no NOC manualmente.");
    const tab = await chrome.tabs.get(id);
    if (pedido.fase === "salvar") {
      const ticket = numeroTicket(tab.url, pedido);
      if (!ticket) return {aguardando_ticket: true};
      await informar(pedido.token, "ticket", "", {ticket, url: tab.url});
      await chrome.storage.session.remove(chave(id));
      return {mensagem: `NOC: ticket ${ticket} devolvido ao incidente correspondente.`};
    }
    const atual = new URL(tab.url), destino = new URL(pedido.url);
    if (atual.origin !== destino.origin || atual.pathname.toLowerCase() !== destino.pathname.toLowerCase()) return {aguardar: true};
    // Verifica o DOM antes de consultar a ponte; não faz HTTP a cada mutação da página.
    const pronto = await chrome.scripting.executeScript({target: {tabId: id}, func: () => {
      const assunto = document.querySelector('input[name="Subject"], input[id*="Subject"]');
      const frame = document.querySelector('iframe.tox-edit-area__iframe, iframe.k-content');
      return Boolean(assunto?.getClientRects().length && frame?.getClientRects().length && frame.contentDocument?.body);
    }});
    if (!pronto[0]?.result) return {aguardar: true};
    const dados = await consultar(pedido.token);
    const respostas = await chrome.scripting.executeScript({target: {tabId: id}, world: "MAIN", func: preencherFormulario, args: [dados]});
    if (respostas[0]?.result?.aguardar) return {aguardar: true};
    if (!respostas[0]?.result?.ok) throw new Error("Não foi possível preencher o editor. Revise a guia aberta.");
    await informar(pedido.token, "ok");
    await chrome.storage.session.set({[chave(id)]: {...pedido, fase: "salvar", expira: Date.now() + pedido.retorno * 1000}});
    return {aguardando_ticket: true, mensagem: "NOC: formulário preenchido. Revise, cole o print e salve; o número será devolvido ao aplicativo."};
  } catch (erro) {
    const mensagem = erro.message || String(erro);
    await informar(pedido.token, "erro", mensagem).catch(() => {});
    await chrome.storage.session.remove(chave(id));
    return {erro: mensagem, mensagem: `NOC: ${mensagem}`};
  } finally { emAndamento.delete(id); }
}

async function zabbix(mensagem, sender) {
  if (sender.frameId !== 0 || !ZABBIX.has(new URL(sender.url).origin)) throw new Error("Origem Zabbix não configurada.");
  if (mensagem.tipo === "carregar_renderizador") {
    await chrome.scripting.executeScript({target: {tabId: sender.tab.id}, files: ["vendor/html2canvas.min.js"]});
    return {ok: true};
  }
  const conexao = (await chrome.storage.session.get("conexaoNoc")).conexaoNoc;
  if (!conexao || Date.now() >= conexao.expira) throw new Error("No aplicativo, clique em Conectar Zabbix ao NOC primeiro.");
  const payload = mensagem.payload;
  if (!Array.isArray(payload?.eventos) || !payload.eventos.length || payload.eventos.length > 100 ||
      payload.eventos.some(e => new URL(e.link_zabbix).origin !== new URL(sender.url).origin)) throw new Error("Lote de eventos inválido.");
  await informar(conexao.token, "importar", "", {payload});
  return {ok: true};
}

chrome.runtime.onMessage.addListener((mensagem, sender, responder) => {
  if (!sender.tab || sender.id !== chrome.runtime.id) return;
  const tarefa = mensagem.tipo === "abrir" ? abrir(mensagem, sender) :
    mensagem.tipo === "preencher" ? preencher(sender) :
    ["importar_zabbix", "carregar_renderizador"].includes(mensagem.tipo) ? zabbix(mensagem, sender) : Promise.resolve({});
  tarefa.then(responder).catch(erro => responder({erro: erro.message || String(erro)}));
  return true;
});

// onUpdated cobre mudanças de URL por History API e navegações após salvar.
chrome.tabs.onUpdated.addListener((id, mudancas, tab) => {
  if (mudancas.url) preencher({tab, frameId: 0}).catch(() => {});
});
chrome.tabs.onRemoved.addListener(async id => {
  const pedido = (await chrome.storage.session.get(chave(id)))[chave(id)];
  await chrome.storage.session.remove(chave(id));
  if (pedido) await informar(pedido.token, "erro", "Guia fechada. Se o ticket foi salvo, informe seu número manualmente no NOC.").catch(() => {});
});
