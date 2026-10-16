(() => {
  if (globalThis.nocPreenchimentoAtivo) return;
  globalThis.nocPreenchimentoAtivo = true;
  let timer, fallback, ocupado = false, ativo = true;
  const observador = new MutationObserver(mudancas => {
    if (mudancas.some(m => !m.target.closest?.(".noc-aviso"))) agendar();
  });
  function parar() {
    ativo = false;
    observador.disconnect();
    clearTimeout(timer);
    clearTimeout(fallback);
    document.removeEventListener("load", agendar, true);
    globalThis.nocPreenchimentoAtivo = false;
  }
  function mostrar(texto, erro) {
    const aviso = document.createElement("div");
    aviso.className = "noc-aviso";
    aviso.textContent = texto;
    Object.assign(aviso.style, {position: "fixed", bottom: "20px", right: "20px", zIndex: "2147483647", maxWidth: "440px", padding: "16px", color: "white", borderRadius: "8px", background: erro ? "#b42318" : "#175cd3", font: "14px Segoe UI,sans-serif"});
    document.body.append(aviso);
    setTimeout(() => aviso.remove(), 12000);
  }
  function agendar() {
    if (!ativo || ocupado) return;
    clearTimeout(timer);
    timer = setTimeout(tentar, 250);
  }
  async function tentar() {
    if (!ativo || ocupado) return;
    ocupado = true;
    clearTimeout(fallback);
    try {
      const resposta = await chrome.runtime.sendMessage({tipo: "preencher"});
      if (resposta?.mensagem) mostrar(resposta.mensagem, Boolean(resposta.erro));
      if (!resposta?.aguardar && !resposta?.aguardando_ticket) parar();
      else if (resposta.aguardar) fallback = setTimeout(tentar, 5000);
    } catch { parar(); }
    finally { ocupado = false; }
  }
  observador.observe(document.body, {childList: true, subtree: true});
  document.addEventListener("load", agendar, true);
  tentar();
})();
