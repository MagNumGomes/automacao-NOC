# Contrato e implementação do fluxo local

## Entrada JSON, versão 1

Um evento avulso ou um lote:

```json
{
  "versao": 1,
  "origem": "zabbix",
  "eventos": [
    {
      "eventid": "123456",
      "alerta": "CPU usage high",
      "servidor": "host-01",
      "severidade": "High",
      "situacao": "CPU 95%",
      "horario": "2026-10-16 10:42:00",
      "link_zabbix": "https://monitoramento.noc.dataside.com.br/tr_events.php?triggerid=1&eventid=123456"
    }
  ]
}
```

No formato avulso, os campos ficam junto de `versao` e `origem`. Campos ausentes são strings vazias. A importação aceita dados parciais para revisão, mas exige URL HTTP/HTTPS com eventid numérico; um eventid explícito deve corresponder ao link. Credenciais na URL, campos não textuais e valores acima de 30.000 caracteres são rejeitados. Limites: 100 eventos por lote e 2 MB no clipboard/ponte. A validação do lote precede sua aplicação à fila.

Identidade: esquema + autoridade + diretório da instalação Zabbix + eventid. Trigger e host não são identidade, pois podem se repetir. A fila possui também UUID local para correlacionar tickets e incidentes manuais. Recapturas atualizam campos disponíveis do evento; valores vazios não apagam dados anteriores. Ticket e encaminhamento não são aceitos do exportador Zabbix.

## Extensão e ponte

- `coletor.js`: funções compartilhadas, extração por rótulos PT/EN, seleção por checkbox/link e enriquecimento com concorrência 2.
- `zabbix.js`: controles da página, clipboard, envio e renderização de evidência sob demanda.
- `background.js`: valida remetente/domínio, armazena tokens em `chrome.storage.session`, faz HTTP local e coordena as guias.
- `ticket.js`: observa alterações do formulário, com debounce de 250 ms e fallback de 5 s apenas enquanto aguarda preenchimento. Verifica prontidão local antes de consultar a ponte.
- `movidesk.js`: utilitários de cópia também distribuídos como userscript; não varre o texto de toda a página a cada segundo.

O aplicativo cria pedidos com tokens aleatórios. A guia `/request/{token}` inicia o vínculo; `/api/request/{token}` exige `X-NOC-Token`. O POST `/api/result/{token}` aceita os eventos compatíveis com o pedido:

- `progresso`, `ok`, `erro`: andamento.
- `importar` + `payload`: somente no canal de conexão Zabbix; validado antes de entrar na fila da interface.
- `ticket` + `ticket`/`url`: somente no pedido Movidesk; origem, rota e número precisam corresponder à instância solicitada.

O canal Zabbix dura até 12 horas. O pedido Movidesk começa com o timeout de formulário e, após preencher, passa para o timeout de retorno (8 horas por padrão). O worker pode acompanhar vários retornos simultaneamente. Após receber o número, remove o pedido. Expiração, fechamento do aplicativo e erros invalidam o token. Uma nova conexão Zabbix invalida a anterior.

Importações recebidas enquanto outra operação está ativa aguardam a liberação da interface. Retornos de ticket atualizam o item identificado pelo UUID original, sem trocar a seleção nem sobrescrever um ticket diferente já informado. Reinícios não restauram tokens pendentes: os dados da fila são persistidos, as autorizações de navegador são de sessão.

## OCR e IA opcional

`ocr_windows.py` agrupa palavras pelas coordenadas antes de formar texto. `extracao_local.py` mapeia rótulos, preserva dados operacionais multilinha, sinaliza valores conflitantes e rejeita horários sem um horário válido. A extração local não atribui um score probabilístico de confiança; revisão continua disponível.

`noc_services.extrair_dados()` executa OCR antes de qualquer provedor. Campos revisados são preservados quando a identidade textual reconhecida não mudou. Com IA permitida, solicita somente chaves faltantes. Groq recebe texto limitado; Gemini recebe imagem quando necessário. Respostas não substituem campos locais. Erros e dados parciais são apresentados sem descartar o resultado local. Nenhum retry automático é feito.

Cache SHA-256 dos pixels, modo/configuração e campos conhecidos, limitado a 20 resultados completos por sessão. Falhas e resultados parciais não entram no cache. A cache não serve para deduplicar eventos Zabbix: essa deduplicação utiliza instância/eventid.

Modelos permanecem configuráveis; trocar o modelo de texto requer compatibilidade com JSON Schema estrito e `reasoning_effort=low`. O projeto não escolhe automaticamente modelos com base em preços externos nem faz chamadas de benchmark pagas.

## Persistência e métricas

Rascunho v2: campos/imagem do incidente ativo, fila com UUIDs, metadados e imagens, e UUID ativo. v1 continua legível. O worker serializa gravações, reaproveita imagens codificadas enquanto forem o mesmo objeto e mantém apenas o snapshot mais recente quando há gravações pendentes. Escrita atômica e preservação de rascunho inválido continuam ativas.

Metadados armazenam origem, identidade, última duração/chamadas, tokens reportados acumulados e campos editados após captura. Esses campos editados não representam automaticamente erros do extrator: podem ser ajustes operacionais. A proporção sem IA é calculada sobre as últimas operações dos itens presentes, não sobre todo o histórico de uso. Tempos de DOM medem aplicação/importação local; OCR/IA incluem o processamento do worker. O painel de cotas por API continua limitado ao uso reportado na sessão.

## Evidências e manutenção

`html2canvas` 1.4.1 e sua licença MIT ficam em `edge_extension/vendor/`. A extensão carrega a biblioteca empacotada somente sob solicitação de imagem. O userscript usa a mesma versão no CDN sob demanda. A seleção das linhas é semântica, não ordinal. Cache de imagem considera URL, conteúdo, cores relevantes, largura e pixel ratio; Win+Shift+S continua disponível para capturar a tela original.

`gerar_userscripts.py` reúne fontes compartilhadas e cabeçalhos Tampermonkey. O build regenera e distribui os scripts; um teste detecta artefatos divergentes. Edite `edge_extension/` e regenere, em vez de editar as cópias geradas.

Fixtures locais cobrem rótulos, colunas reordenadas, dados parciais, fila/recapturas, migração, OCR, cache, ponte autenticada, sessão de navegador, envio Zabbix e retornos Movidesk fora de ordem. Para homologar nos sites reais, confira um evento de cada Zabbix, uma seleção em lote, uma imagem e um ticket salvo na instância Movidesk. Não há criação automática de tickets nem reconhecimento automático de eventos.
