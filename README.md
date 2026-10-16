# Orquestrador SRE NOC — local primeiro

Aplicativo Windows para importar alertas do Zabbix, preencher o Movidesk no Edge já logado e gerar comunicados. **O fluxo principal não usa IA nem consome tokens.**

```text
Zabbix → leitura do HTML → extensão / JSON no clipboard → fila NOC
                                                          ↓
                          comunicados ← número do ticket ← Movidesk

Somente print disponível → OCR Windows + regras locais → revisão
                                     ↓ campos ausentes, IA habilitada
                              Groq (texto) → Gemini (visão, se necessário)
```

## Recursos

- **Coleta direta do Zabbix:** Host, Trigger/Event name, Severity, Operational data, Time, URL e eventid.
- **Extensão Edge:** botão **Enviar ao NOC**, sem chaves da API Zabbix e usando a sessão do navegador.
- **Tampermonkey/clipboard:** scripts distribuídos em [`tampermonkey/`](tampermonkey/); botão **Copiar dados para NOC** e importação JSON no aplicativo.
- **Lotes:** até 100 eventos selecionados por importação. Dados disponíveis na lista são reutilizados; detalhes faltantes são buscados com até duas requisições simultâneas, de 8 segundos cada.
- **Fila persistente:** cada incidente tem campos, metadados e print próprios. Recapturas da mesma instância + eventid atualizam o evento, preservando ticket e encaminhamento.
- **OCR sem API:** leitura espacial de linhas/colunas e regras para rótulos PT/EN. Campos ausentes ou conflitantes ficam disponíveis para revisão.
- **IA opcional:** desligada por padrão no fluxo local; completa somente campos não resolvidos. Resultados completos da mesma captura/configuração são reutilizados em cache de sessão.
- **Movidesk:** preenche assunto e descrição; após o salvamento manual, devolve número e link ao incidente original, mesmo que outro incidente esteja selecionado.
- **Comunicados locais:** WhatsApp, Teams e e-mail, com assunto e recortes de imagem.
- **Métricas:** origem, tempo da última extração/importação, chamadas de IA, tokens reportados e campos editados após captura.

## Começar pelo código-fonte

Requisitos: Python 3.10+, Windows 10/11 e Microsoft Edge. OCR requer Português ou Inglês instalado no Windows.

```powershell
pip install -r requirements.txt
copy .env.example .env
python app_noc.py
```

Não sobrescreva seu `.env` existente ao atualizar. **Nenhuma chave é obrigatória** para importar dados, extrair localmente, preencher o Movidesk ou gerar comunicados. A configuração existente recebe apenas opções ausentes; alterações no `.env` exigem reiniciar.

## Instalar ou atualizar a extensão

1. No aplicativo, menu **⋯ > Instalar extensão do Edge**.
2. Abra `edge://extensions/`, ative **Modo do desenvolvedor** e escolha **Carregar sem compactação**.
3. Selecione a pasta indicada, no perfil em que você utiliza Zabbix e Movidesk.
4. Ao atualizar: abra o NOC, clique em **Recarregar** no cartão da extensão e recarregue as páginas do Zabbix/Movidesk.
5. No aplicativo, menu **⋯ > Conectar Zabbix**. A guia local confirma a conexão e pode ser fechada.
6. No Zabbix, expanda **NOC — dados locais, sem IA** e clique em **Enviar ao NOC**.

A conexão de importação dura até 12 horas na sessão atual. Após reiniciar o NOC ou o navegador, conecte novamente. O preenchimento e retorno do Movidesk são associados automaticamente ao pedido; não dependem dessa conexão de importação.

Domínios incluídos:

- `https://monitoramento.noc.dataside.com.br`
- `https://crz.extras.tools.dataside.com.br`
- `https://*.movidesk.com`

Para outros Zabbix, ajuste `host_permissions` e o coletor em `content_scripts` do [`manifest.json`](edge_extension/manifest.json), e a lista `ZABBIX` em [`background.js`](edge_extension/background.js). Para Movidesk personalizado, ajuste as permissões, a entrada de `ticket.js`/`movidesk.js` e `MOVIDESK_URL`. Recarregue a extensão.

## Usar Tampermonkey

Instale os arquivos gerados:

- [`NOC-Zabbix.user.js`](tampermonkey/NOC-Zabbix.user.js): substitui os três exemplos Zabbix, nos dois domínios, incluindo seleção em lote.
- [`NOC-Movidesk.user.js`](tampermonkey/NOC-Movidesk.user.js): copia número, assunto, link e template, usando observação do DOM em vez de `setInterval`.

Desative os scripts antigos nas páginas atendidas para evitar botões duplicados. Se utilizar os utilitários da extensão, não é necessário instalar os userscripts nessas mesmas páginas.

No Zabbix, use **Copiar dados para NOC**; no aplicativo, **Importar dados (Ctrl+I)**. O userscript não envia diretamente à ponte local. A extensão continua sendo utilizada para preencher e acompanhar o Movidesk.

As fontes são compartilhadas com a extensão. Para regenerar os userscripts após editar os coletores:

```powershell
python gerar_userscripts.py
```

## Fluxo de atendimento

1. Importe o evento pelo navegador ou JSON. Se necessário, use **+ Novo** e preencha manualmente.
2. Revise os dados na aba **Incidente**. Use o seletor no topo para alternar incidentes.
3. Guarde um print com **Win+Shift+S** e **Ler print**, se necessário como evidência. A imagem não é necessária para importar os dados.
4. Clique em **Abrir Movidesk**. Revise, complete os campos exigidos pelo site, cole a evidência e salve manualmente.
5. O número retorna ao incidente original. Se o prazo/sessão tiver terminado ou o site não expuser o ID em uma URL suportada, digite-o no campo **Ticket** da barra inferior.
6. Na aba **Comunicar**, escolha o canal e copie a mensagem.

**+ Novo** acrescenta um item à fila e preserva os anteriores. Menu **⋯ > Desfazer** volta ao anterior; **⋯ > Remover** exclui apenas o item local. A remoção não altera Zabbix nem Movidesk.

## Quando só houver um print

- **Ler print:** OCR Windows + regras, sem API por padrão.
- **⋯ > Completar com IA:** resolve campos ausentes. Se os campos já estiverem preenchidos ou o OCR resolver tudo, não há chamada.
- Com texto de OCR e Groq habilitada, tenta Groq primeiro. Se a tentativa falhar e Gemini estiver configurado, usa visão. Sem texto legível, usa somente Gemini quando permitido/configurado.
- Cada provedor é chamado no máximo uma vez por extração, sem retries automáticos. Falhas preservam os dados locais e mostram orientações.
- Campos locais/revisados são preservados ao completar. Resultados completos entram em cache limitado a 20 capturas/configurações, somente durante a sessão.

Para um evento diferente disponível apenas como imagem, use **Novo incidente** antes da captura: uma imagem não fornece identidade confiável por eventid. Se a extração detectar outro alerta/servidor, um novo item será criado; eventos repetidos do mesmo host/trigger exigem essa separação manual ou a importação estruturada.

### Configurações

| Variável | Padrão | Finalidade |
|---|---|---|
| `IA_AUTOMATICA` | `false` | Permite IA após OCR incompleto no botão de extração; quando ativa, o botão indica OCR + IA |
| `OCR_TIMEOUT_SECONDS` | `15` | Tempo da leitura local |
| `GROQ_API_KEY` | vazio | Chave opcional para texto |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Modelo de texto; pode ser alterado para outro compatível com schema estrito e `reasoning_effort=low` |
| `GROQ_FALLBACK_ENABLED` | `true` | Habilita o provedor Groq quando houver chave (nome mantido por compatibilidade) |
| `GROQ_TIMEOUT_SECONDS` | `30` | Tempo da chamada Groq |
| `GROQ_MAX_COMPLETION_TOKENS` | `2048` | Teto de resposta, incluindo raciocínio |
| `GEMINI_API_KEY` | vazio | Chave opcional para visão |
| `GEMINI_MODEL` | valor histórico no `.env.example` | Informe um modelo de visão disponível na sua conta |
| `GEMINI_TIMEOUT_SECONDS` | `60` | Tempo da chamada Gemini |
| `GEMINI_MAX_OUTPUT_TOKENS` | `2048` | Teto de resposta Gemini |
| `MOVIDESK_URL` | `https://grupohda.movidesk.com` | Endereço da instância |
| `MOVIDESK_LOGIN_TIMEOUT_SECONDS` | `120` | Espera pelo formulário/login |
| `MOVIDESK_RETORNO_TIMEOUT_SECONDS` | `28800` | Espera pelo salvamento e retorno do ticket (8 horas) |

Timeouts de OCR/APIs/formulário aceitam 5–300 segundos. Retorno do ticket aceita 60–86400 segundos. Tetos de tokens aceitam 128–32768; o modelo pode impor outras restrições. Os timeouts das etapas opcionais podem se somar.

O menu **⋯ > Consumo e detalhes** mantém os dados reportados por Gemini/Groq e o resumo por incidente. Cotas Groq refletem os cabeçalhos da última resposta; Gemini não informa cota restante nessa integração. Tetos limitam saída, não entrada nem gasto total. Consumo não reportado não é estimado. O painel por API é reiniciado ao fechar; tokens reportados por incidente são persistidos na fila.

O texto enviado à Groq exclui a navegação anterior ao primeiro rótulo e é limitado a 8.000 caracteres; texto maior pede um recorte. Modelos menores podem ser avaliados com amostras revisadas e as métricas locais. Não há benchmark de custo/precisão em produção incluído neste projeto.

## Imagens e e-mail

No Zabbix, **Copiar imagem Host / Trigger / Severity** seleciona as linhas pelos rótulos, sem assumir que são as três primeiras da primeira tabela. `html2canvas` só carrega ao solicitar imagem; na extensão está empacotado, e no Tampermonkey é carregado do CDN. A imagem é reutilizada enquanto conteúdo/apresentação relevante não mudar. Ela é uma renderização do HTML; para evidência dos pixels da tela, use Win+Shift+S.

**Copiar e-mail + imagem** fornece HTML e texto ao clipboard, conforme o suporte do destino. No aplicativo, a aba Comunicar com canal E-mail oferece assunto, corpo e recorte do print. Os recortes são locais e não usam IA. Suas seleções são descartadas ao trocar a imagem/incidente ou reiniciar.

## Executável Windows

Execute **Build Windows.cmd** ou:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
```

O build usa `.venv-build`, gera os userscripts, empacota a extensão e verifica interface, OCR, importação local, dependências e Edge. O relatório fica em `build/verificacao.json`. Para outra saída sem substituir o atalho:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1 -SemAtalho -PastaSaida dist\local-first
```

Distribua a pasta `OrquestradorNOC` inteira, incluindo `_internal`. O destino não precisa de Python ou VS Code. O pacote inclui manual e userscripts. O executável usa `%LOCALAPPDATA%\AutomacaoNOC` para `.env`, `.noc_data` e extensão, preservados entre builds. Na execução pelo Python, esses dados ficam no projeto. **Abrir configuracoes.cmd** abre a configuração do executável.

O rascunho versão 2 persiste fila, incidente ativo e imagens. Rascunhos antigos de um incidente são lidos e migrados no próximo salvamento. Arquivos inválidos são preservados antes de novas gravações. O login permanece no Edge. A ponte escuta somente `127.0.0.1:18764`, com tokens temporários e validação dos pedidos; fechá-la não fecha suas guias.

## Desenvolvimento e verificação

```powershell
python -m unittest discover -s tests -v
```

Para incluir testes reais da extensão e dos coletores com fixtures locais:

```powershell
playwright install chromium --no-shell
$env:NOC_TEST_BROWSER = "1"
python -m unittest discover -s tests -v
```

Os testes cobrem importação, deduplicação, fila/rascunho, OCR nativo e parser, IA simulada, cache, autenticação da ponte, preenchimento e retorno de tickets fora de ordem. Não chamam APIs pagas nem os sites da empresa. Os testes Tkinter precisam de sessão gráfica. Os seletores devem ser conferidos com os layouts reais após a atualização.

Principais arquivos:

- `app_noc.py`: interface e fila de eventos.
- `incidentes.py`: contrato de importação, identidade e fila.
- `extracao_local.py` / `ocr_windows.py`: interpretação local, cache e OCR espacial.
- `noc_services.py`: extração opcional, rascunhos, templates e coordenação Movidesk.
- `edge_bridge.py` / `edge_extension/`: comunicação autenticada e automação DOM.
- `gerar_userscripts.py` / `tampermonkey/`: distribuição Tampermonkey.
- `tokens_ia.py` / `recortes_email.py`: consumo e evidências.

Consulte o [manual operacional](manual-noc.md) e o [contrato técnico do fluxo local](docs/fluxo-local.md). Erros ficam em **Detalhes do erro** e `.noc_data/noc.log`. `.env`, rascunhos e perfis locais não devem ser versionados.
