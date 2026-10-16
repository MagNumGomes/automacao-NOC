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
