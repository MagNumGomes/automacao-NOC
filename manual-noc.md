# Manual de Instruções: Orquestrador SRE NOC (IA + Playwright)

Este manual detalha a configuração e utilização da ferramenta de automação para o NOC. A aplicação utiliza Inteligência Artificial (Google Gemini) para leitura de imagens via Visão Computacional e o Playwright para automação web nativa no Movidesk, eliminando a dependência de extensões manuais no navegador (como o Tampermonkey).

---

## 1. Pré-requisitos e Instalação

A ferramenta foi desenvolvida em Python (compatível com Python 3.10+) e requer algumas dependências.

### 1.1. Instalar Dependências do Python
Abra o terminal na pasta do projeto e instale as bibliotecas necessárias usando o `requirements.txt`:

```bash
pip install -r requirements.txt
```

### 1.2. Instalar os Navegadores do Playwright
O Playwright precisa do binário do navegador Chromium instalado no sistema:

```bash
playwright install chromium
```

### 1.3. Configuração da Chave de API (Gemini)
1. Acesse o [Google AI Studio](https://aistudio.google.com/) e crie uma chave de API gratuita.
2. Crie um arquivo `.env` a partir do modelo de exemplo:
   ```bash
   copy .env.example .env
   ```
3. Abra o arquivo `.env` e insira a sua chave gerada:
   ```env
   GEMINI_API_KEY=sua_chave_api_aqui
   ```
   > **Nota de Segurança:** O arquivo `.env` está incluído no `.gitignore` para evitar o vazamento acidental de credenciais em repositórios Git públicos ou privados.

---

## 2. Executando a Aplicação

Para iniciar o orquestrador, execute o comando:

```bash
python app_noc.py
```

A interface gráfica (Tkinter) será exibida na tela.

---

## 3. Fluxo de Trabalho (Workflow)

A ferramenta cobre o ciclo de vida completo do incidente, desde a extração de dados no Zabbix até o disparo de comunicações multicanal.

### Fase 1: Extração Inteligente (Zabbix)
1. Quando um alerta surgir no Zabbix, utilize o atalho de captura de tela do Windows (`Win + Shift + S`) e selecione o bloco contendo os detalhes do evento (Trigger, Host, Severity, Operational Data, etc.).
2. A imagem capturada ficará automaticamente na sua área de transferência.
3. Na aplicação, clique no botão roxo **"🧠 Extrair Dados do Print (Área de Transferência)"**.
4. O modelo Gemini processará a imagem e preencherá automaticamente os campos:
   - **Alerta (Trigger)**
   - **Servidor (Host)**
   - **Severidade**
   - **Dados Operacionais**
   - **Horário da Falha**
5. *(Opcional)* Copie o link do evento no Zabbix e cole no campo **"Link do Zabbix:"**.

### Fase 2: Automação no Movidesk (Playwright)
1. Com os campos preenchidos, clique no botão azul **"🌐 Abrir e Preencher Movidesk"**.
2. O Playwright abrirá uma janela do navegador Chromium e navegará até a página de criação de tickets do Movidesk:
   - **Perfil persistente:** Os dados da sessão são armazenados na pasta local `movidesk_profile/`. No primeiro acesso, faça o login; nos acessos seguintes, a sessão permanecerá salva.
3. A automação preencherá automaticamente:
   - **Assunto:** Formato `[Alerta] - [Servidor]`
   - **Descrição:** Tabela/lista formatada em HTML com todos os dados do incidente e o link do Zabbix.
4. O navegador permanecerá aberto aguardando sua finalização manual:
   - Clique no corpo do ticket no Movidesk.
   - Pressione `CTRL + V` para colar o print do Zabbix diretamente no editor de texto.
   - Conclua os campos adicionais necessários e salve o ticket.

### Fase 3: Comunicação Multicanal (Disparo)
1. Copie o número do Ticket recém-criado no Movidesk e insira-o no campo **"N° do Ticket gerado no Movidesk:"**.
2. Preencha os campos de acionamento:
   - **Acionamento (WhatsApp):** Nome ou equipe de acionamento.
   - **Time Responsável (Teams):** Identificação do canal ou equipe responsável.
3. Utilize os botões de cópia rápida para obter os comunicados pré-formatados:
   - 🟢 **Copiar WhatsApp:** Gera o resumo com saudação dinâmica (Bom dia / Boa tarde / Boa noite) e dados operacionais.
   - 🟣 **Copiar Teams:** Gera o formato compacto com link direto para o ticket no Movidesk (`https://grupohda.movidesk.com/Ticket/Edit/{ticket}`).
   - 🔴 **Copiar E-mail:** Gera o modelo formal de comunicação de incidente.
4. Cole o conteúdo diretamente nas respectivas ferramentas de comunicação.