# Manual de Instruções: Orquestrador SRE NOC (IA + Playwright)

Este manual detalha a configuração e utilização da ferramenta de automação para o NOC. A aplicação utiliza Inteligência Artificial (Google Gemini) para leitura de ecrãs através de Visão Computacional e o Playwright para a automação web nativa, eliminando a dependência de extensões no navegador (como o Tampermonkey).

## 1. Pré-requisitos e Instalação

A ferramenta foi desenvolvida em Python e requer a instalação de algumas bibliotecas. Abra o terminal do seu sistema e execute os seguintes comandos:

**Instalar dependências do Python:**
```bash
pip install google-generativeai pillow pyperclip playwright
```

**Instalar os navegadores do Playwright:**
```bash
playwright install chromium
```

**Chave de API (Gemini):**
1. Aceda ao Google AI Studio.
2. Crie uma chave de API gratuita.
3. Insira a chave na variável `API_KEY` localizada no topo do código-fonte `app_noc.py`.

## 2. Fluxo de Trabalho (Workflow)

A ferramenta cobre o ciclo de vida completo do incidente, desde a extração de dados no Zabbix até ao disparo de comunicações multicanal.

### Fase 1: Extração Inteligente
1. Quando um alerta surgir no Zabbix, utilize o atalho de captura de ecrã do Windows (`Win + Shift + S`) e selecione o bloco que contém os detalhes do evento (Trigger, Host, Severity, etc.). A imagem ficará guardada na sua área de transferência.
2. Abra a aplicação `app_noc.py`.
3. Clique no botão roxo **"🧠 Extrair Dados do Print (Área de Transferência)"**.
4. A IA lerá a imagem de forma invisível e preencherá automaticamente os campos de Alerta, Servidor, Severidade, Dados Operacionais e Horário.
5. Copie o link da página do Zabbix no seu navegador e cole no campo "Link do Zabbix (Opcional)".

### Fase 2: Automação no Movidesk
1. Com os dados preenchidos, clique no botão azul **"🌐 Abrir e Preencher Movidesk"**.
2. O Playwright iniciará uma janela do navegador Chromium e navegará até à página de criação de tickets do Movidesk. *(Nota: O primeiro acesso exigirá que faça o login; os acessos seguintes utilizarão o perfil guardado localmente)*.
3. A automação preencherá automaticamente o campo de "Assunto" e formatará a "Descrição" em HTML no editor de texto do Movidesk.
4. O navegador permanecerá aberto. Clique no corpo do ticket no Movidesk, faça `CTRL + V` para colar o print do Zabbix (que ainda está na sua área de transferência) e guarde o ticket.

### Fase 3: Comunicação às Equipas
1. Recolha o número do Ticket recém-criado no Movidesk e insira-o no campo "N° do Ticket no Movidesk" da aplicação.
2. Preencha os dados de acionamento (WhatsApp e Teams).
3. Utilize os botões verdes, azuis e vermelhos para copiar os templates formatados e cole-os nas respetivas plataformas de comunicação.