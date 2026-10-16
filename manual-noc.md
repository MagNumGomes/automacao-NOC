# Manual — Orquestrador SRE NOC

## 1. Instalar e atualizar

Abra `OrquestradorNOC.exe`, mantendo `_internal` junto dele. Python e VS Code não são necessários no computador que recebe o pacote. Para gerar o pacote, execute **Build Windows.cmd**. O manual e os userscripts acompanham a distribuição.

No executável, configuração, rascunho/logs e extensão ficam em `%LOCALAPPDATA%\AutomacaoNOC`. Pelo Python, ficam no projeto. O login é mantido no perfil habitual do Edge.

1. No NOC, menu **⋯ > Instalar extensão do Edge**.
2. Abra `edge://extensions/`, ative **Modo do desenvolvedor** e carregue a pasta indicada pelo NOC.
3. Use o mesmo perfil que já está logado no Zabbix e Movidesk.
4. Ao atualizar, abra o aplicativo para atualizar os arquivos, clique em **Recarregar** na extensão e recarregue as páginas dos sites.

O fluxo local funciona sem configurar qualquer chave de IA. Para executar pelo código:

```powershell
pip install -r requirements.txt
copy .env.example .env
python app_noc.py
```

Preserve o `.env` existente ao atualizar. As opções ausentes são acrescentadas automaticamente. Alterações na configuração exigem reiniciar o NOC.

## 2. Importar diretamente do Zabbix

### Pela extensão

1. No aplicativo, menu **⋯ > Conectar Zabbix**.
2. Aguarde a confirmação na guia local. Você pode fechá-la.
3. Abra o evento no Zabbix e expanda **NOC — dados locais, sem IA**, no canto inferior esquerdo.
4. Clique em **Enviar ao NOC**.
5. O incidente aparece na fila, com origem DOM, URL e eventid. Revise campos ausentes ou inesperados.

A conexão de importação dura até 12 horas. Após reiniciar o aplicativo ou navegador, conecte novamente. Os dois Zabbix dos scripts originais já estão configurados.

### Pelo Tampermonkey ou clipboard

1. Instale `tampermonkey/NOC-Zabbix.user.js` e desative os três scripts Zabbix antigos para evitar duplicidade.
2. No painel NOC da página, clique em **Copiar dados para NOC**.
3. No aplicativo, clique em **Importar dados (Ctrl+I)**.

O mesmo botão de cópia também existe na extensão. Não é necessário instalar o userscript se você já utiliza os utilitários da extensão. A cópia é JSON estruturado; copiar apenas um link ou o template de e-mail não equivale a exportar os dados.

O userscript Movidesk (`NOC-Movidesk.user.js`) oferece cópia de número, link, assunto e template. A extensão do NOC é a responsável pelo preenchimento e pelo retorno automático do número.

### Vários alertas

Na lista `zabbix.php?action=problem.view`, selecione os eventos desejados. Use **Enviar selecionados ao NOC** ou **Copiar selecionados para NOC**. Também há **Selecionar primeiras N linhas** (1–100) e **Copiar links selecionados**.

Linhas já marcadas continuam marcadas. A importação utiliza os dados das colunas e busca somente os detalhes faltantes, com duas requisições simultâneas e timeout por página. Se um detalhe estiver indisponível, o evento é importado com os campos disponíveis para revisão. Nenhuma IA é chamada nesta etapa.

## 3. Trabalhar com a fila

- O seletor no topo alterna os atendimentos.
- Cada item mantém seus próprios campos e imagem. O ticket é mostrado no seletor quando disponível.
- **+ Novo (Ctrl+N)** acrescenta um item vazio, preservando os anteriores.
- Menu **⋯ > Desfazer** retorna ao anterior; um novo item ainda vazio é removido.
- Menu **⋯ > Remover** exclui o item local selecionado; não exclui tickets nem reconhece alertas nos sites.
- Importar novamente a mesma instância + eventid atualiza os dados do evento, preservando ticket, acionamento, time e print.
- Outro eventid ou outra instância cria outro incidente, mesmo com alerta e servidor iguais.

A fila, o item ativo, os campos, metadados e imagens são salvos automaticamente em `.noc_data/rascunho.json`. O rodapé informa o salvamento. Rascunhos antigos são recuperados como um único item. Ao fechar, aguarde a gravação; se ela falhar, o aplicativo oferece continuar aberto ou fechar sem salvar.

## 4. Captura de imagem e OCR local

Uma imagem serve como evidência e não é necessária para importar pelo DOM.

1. Se for outro evento, use **+ Novo** antes de capturá-lo.
2. Capture com **Win+Shift+S** e clique em **Ler print** (ou **Ctrl+Shift+V**).
3. Se só houver imagem disponível, o botão lê o print guardado.
4. O Windows lê a imagem e o parser local procura Host, Trigger/Event name, Severity, Operational data e Time, com rótulos PT/EN.
5. Confira os campos. Ausências, horários inválidos e valores conflitantes são informados para revisão; nenhuma API é chamada no modo padrão.

O OCR usa posições das palavras para reconstruir linhas e colunas. Nomes e números ainda podem ser reconhecidos incorretamente; revise especialmente hosts, percentuais e horário. Se faltar idioma de OCR, instale Português ou Inglês nas configurações de idioma do Windows.

A extração usa o print guardado na miniatura. Para trocar, capture novamente com **Win+Shift+S** e **Ler print**. Para eventos repetidos do mesmo host/alerta, a separação confiável depende do eventid importado; quando há apenas imagens, inicie um novo incidente explicitamente.

### Completar campos com IA, quando necessário

1. No menu **⋯ > Configurações**, preencha as chaves opcionais. Salve e reinicie.
2. No menu **⋯ > Completar com IA**, resolva o incidente incompleto.
3. O OCR é tentado primeiro. Com texto e Groq habilitada, ela recebe o trecho relevante e somente as chaves ainda não resolvidas são solicitadas. Se falhar, Gemini configurado pode receber o print. Sem texto legível, somente a visão é utilizada.
4. Os campos locais/revisados são preservados. Falhas deixam os dados disponíveis para correção manual.

Se não houver campos pendentes, nenhuma API é chamada. Resultados completos podem ser reutilizados em cache durante a sessão. Cada provedor tem no máximo uma chamada por extração; respostas inválidas/incompletas não são cacheadas como completas.

`IA_AUTOMATICA=false` é o padrão. Com `true` no `.env`, o botão passa a indicar **Ler print + IA** e pode completar automaticamente o OCR incompleto. As importações DOM/JSON continuam locais.

## 5. Preencher o Movidesk e receber o número

1. Revise pelo menos **Alerta** e **Servidor**, obrigatórios para o preenchimento.
2. Clique em **Abrir Movidesk** na barra inferior.
3. A extensão utiliza uma nova guia no perfil já logado. Se necessário, faça login; a espera padrão pelo formulário é de 120 segundos.
4. Confira assunto e descrição, complete os demais campos exigidos pelo site e cole o print com **Copiar → Ctrl+V**.
5. Salve o ticket manualmente.
6. Quando a URL expuser o número (`/Ticket/Edit/123`, `/Ticket/Create/123` ou `?id=123` nessas rotas), a extensão o devolve ao incidente original.

Você pode alternar a fila e trabalhar em outro item enquanto o ticket anterior aguarda salvamento. O retorno é associado ao pedido/guia, não ao incidente atualmente selecionado. Um número já digitado e diferente do retornado não é substituído silenciosamente; o aplicativo pede revisão.

A espera pelo retorno é de 8 horas, configurável por `MOVIDESK_RETORNO_TIMEOUT_SECONDS`. O NOC precisa permanecer aberto. Fechar/reiniciar o aplicativo invalida pedidos pendentes, sem fechar suas guias; após isso, informe números manualmente. Se remover o incidente da fila, o retorno não recria esse item.

Cada clique de preenchimento abre uma nova guia. Se uma tentativa falhar parcialmente, revise a guia existente antes de repetir.

## 6. Copiar comunicados e imagens

Informe o número no campo **Ticket** da barra inferior e escolha acionamento/time conforme o canal. Na aba **Comunicar**, selecione WhatsApp, Teams ou E-mail e copie. Os botões copiam; não enviam automaticamente.

No e-mail:

- **Assunto:** copia `ticket - alerta - servidor`.
- **Copiar mensagem / Copiar e-mail:** copia o corpo do canal selecionado.
- **Recortar print / Copiar recorte:** selecione Host, Trigger e Severity no print e cole no Outlook.

No Zabbix, **Copiar imagem Host / Trigger / Severity** gera uma imagem a partir das linhas identificadas pelos rótulos. A biblioteca carrega apenas quando a imagem é solicitada; falha no carregamento não bloqueia a cópia de dados. Na extensão ela está empacotada; no Tampermonkey depende do CDN. **Copiar e-mail + imagem** oferece HTML e texto ao clipboard, conforme suporte do destino. Para uma captura exata dos pixels da tela, use Win+Shift+S.

## 7. Acompanhar consumo e velocidade

Menu **⋯ > Consumo e detalhes** mostra consumo reportado, cotas Groq e resumo por incidente.

`GEMINI_MAX_OUTPUT_TOKENS` e `GROQ_MAX_COMPLETION_TOKENS` começam em 2048. Eles limitam a resposta, não a entrada nem a cota total. Na Groq, raciocínio também consome esse teto. Valores muito baixos podem truncar respostas. Modelos menores devem ser avaliados com exemplos reais revisados antes de serem adotados.

## 8. Solução de problemas

| Situação | Como continuar |
|---|---|
| Botões não aparecem no Zabbix | Recarregue a extensão e a página; confira domínio e rota de evento/lista. |
| Botões duplicados | Desative os scripts antigos ou o userscript equivalente quando usar os utilitários da extensão. |
| Envio pede conexão | No menu ⋯, use **Conectar Zabbix**. |
| JSON inválido | Use **Copiar dados para NOC**, não a cópia do link/template. |
| Campos vazios após importar | Confira o detalhe do evento; layouts não reconhecidos ou sessão expirada podem impedir a leitura. Complete manualmente ou capture o print. |
| Assunto do Movidesk não localizado | Copie do campo do formulário; layouts de edição podem usar outro seletor. O número continua sendo obtido pela URL. |
| OCR sem texto | Capture somente o alerta com campos visíveis; confirme idioma de OCR instalado. |
| IA falhou ou atingiu limite | Dados locais permanecem disponíveis; confira configuração/cota e complete manualmente. |
| Imagem não copia | Mantenha a guia em foco e confira permissão de clipboard; use Win+Shift+S como alternativa. |
| Guia permanece na conexão | Instale/ative/recarregue a extensão no perfil correto e repita a operação. |
| Formulário não preenche | Confira login, campos visíveis e tempo de espera; consulte **Detalhes do erro**. |
| Número não retorna | Confira se o NOC continua aberto, o prazo não terminou e a URL expõe o ID; digite o número manualmente. |
| Porta 18764 ocupada | Feche outra instância do NOC e conecte novamente. |
| Rascunho não salva | Verifique espaço e permissões de `.noc_data`; o rodapé informa a falha. |

Logs com rotação ficam em `.noc_data/noc.log`. A importação e automação foram testadas com fixtures locais; mudanças no HTML real dos sites podem exigir ajuste dos seletores. Veja o README do projeto para configurações completas, testes e permissões de outros domínios.
