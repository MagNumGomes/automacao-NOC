// Esta função é serializada pelo Chrome e executada no contexto do Movidesk.
export function preencherFormulario(dados) {
  const assunto = document.querySelector('input[name="Subject"], input[id*="Subject"]');
  const frame = document.querySelector('iframe.tox-edit-area__iframe, iframe.k-content');
  const body = frame?.contentDocument?.body;
  if (!assunto || !assunto.getClientRects().length || !body || !frame.getClientRects().length) {
    return {aguardar: true};
  }
  if (assunto.value.trim() && assunto.value !== dados.assunto) {
    throw new Error("O assunto já foi editado nesta guia. Revise o ticket antes de tentar novamente.");
  }
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
  setter.call(assunto, dados.assunto);
  assunto.dispatchEvent(new Event("input", {bubbles: true}));
  assunto.dispatchEvent(new Event("change", {bubbles: true}));

  let preenchido = false;
  const editores = window.tinymce?.get?.() || window.tinymce?.editors || [];
  const tiny = Array.from(editores).find(editor => editor.iframeElement === frame);
  if (tiny) {
    tiny.setContent(dados.html);
    tiny.setDirty(true);
    tiny.save();
    tiny.fire("input");
    tiny.fire("change");
    preenchido = true;
  } else if (window.jQuery) {
    window.jQuery('[data-role="editor"]').each(function () {
      const editor = window.jQuery(this).data("kendoEditor");
      if (editor?.body === body) {
        editor.value(dados.html);
        editor.trigger("change");
        preenchido = true;
      }
    });
  }
  if (!preenchido) {
    body.focus();
    body.innerHTML = dados.html;
    body.dispatchEvent(new Event("input", {bubbles: true}));
    body.dispatchEvent(new Event("change", {bubbles: true}));
    body.blur();
  }
  if (!body.textContent.includes(dados.alerta) || assunto.value !== dados.assunto) {
    throw new Error("O formulário não confirmou o preenchimento. Revise a guia aberta.");
  }
  return {ok: true};
}
