/* Utilitários locais também distribuídos como userscript Tampermonkey. */
(() => {
  if (globalThis.nocUtilitariosMovidesk) return;
  globalThis.nocUtilitariosMovidesk = true;
  let timer;
  function numero() {
    const url = new URL(location.href);
    const match = url.pathname.match(/\/Ticket\/(?:Edit|Create)\/(\d+)\/?$/i);
    const id = match?.[1] || url.searchParams.get("id") || "";
    return /^\d+$/.test(id) ? id : "";
  }
  function assunto() {
    const input = document.querySelector('input[name="Subject"], input[id*="Subject"]');
    if (input?.getClientRects().length && input.value.trim()) return input.value.trim();
    const el = document.querySelector('[data-field="Subject"], .ticket-subject, #ticketSubject');
    return (el?.innerText || "").trim();
  }
  function atualizar() {
    const permitido = /\/Ticket\/(?:Edit|Create)(?:\/\d+)?\/?$/i.test(location.pathname);
    let painel = document.getElementById("noc-movidesk-utilitarios");
    if (!permitido) { painel?.remove(); return; }
    if (painel) return;
    painel = document.createElement("details");
    painel.id = "noc-movidesk-utilitarios";
    Object.assign(painel.style, {position: "fixed", bottom: "16px", left: "16px", zIndex: "2147483647", background: "#202630", color: "white", padding: "12px", borderRadius: "8px", font: "13px Segoe UI,sans-serif"});
    const resumo = document.createElement("summary");
    resumo.textContent = "NOC — copiar ticket";
    painel.append(resumo);
    const status = document.createElement("div");
    status.setAttribute("role", "status");
    for (const [rotulo, obter] of [
      ["Copiar número", () => { if (!numero()) throw new Error("Salve o ticket para obter o número pela URL."); return numero(); }],
      ["Copiar link", () => location.href],
      ["Copiar ticket + assunto", () => { if (!assunto()) throw new Error("Assunto não localizado neste layout."); return [numero(), assunto()].filter(Boolean).join(" - "); }],
      ["Copiar template", () => { if (!numero() || !assunto()) throw new Error("Número ou assunto não encontrado. Confira o ticket salvo."); return `${numero()}\n${assunto()}\n${location.href}`; }]
    ]) {
      const botao = document.createElement("button");
      botao.type = "button";
      botao.textContent = rotulo;
      Object.assign(botao.style, {margin: "8px 4px 4px 0", padding: "8px", cursor: "pointer"});
      botao.onclick = async () => { try { await navigator.clipboard.writeText(obter()); status.textContent = "Copiado."; } catch (erro) { status.textContent = erro.message; } };
      painel.append(botao);
    }
    painel.append(status);
    document.body.append(painel);
  }
  new MutationObserver(() => { clearTimeout(timer); timer = setTimeout(atualizar, 200); }).observe(document.body, {childList: true, subtree: true});
  window.addEventListener("popstate", atualizar);
  atualizar();
})();
