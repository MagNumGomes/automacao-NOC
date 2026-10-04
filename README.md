# 🚀 Automação SRE NOC (IA & Playwright)

Sistema desktop em Python desenvolvido para acelerar o ciclo operacional do NOC (Network Operations Center) e equipes de SRE. A ferramenta combina **Visão Computacional via Google Gemini**, automação de navegador nativa com **Playwright** e gerador de templates para comunicação multicanal.

---

## 📌 Principais Recursos

- **🧠 Leitura Inteligente do Zabbix (IA):** Extrai automaticamente dados de alertas (Trigger, Servidor, Severidade, Dados Operacionais e Horário) a partir de prints na área de transferência (`Win + Shift + S`) usando IA multimodal do Google Gemini.
- **🌐 Automação no Movidesk:** Criação e preenchimento de tickets com formato rico em HTML diretamente no navegador via Playwright, mantendo a sessão salva em perfil local.
- **📢 Comunicação Multicanal Instantânea:** Gera templates padronizados com um clique para WhatsApp, Microsoft Teams e E-mail.

---

## 🛠️ Tecnologias Utilizadas

- **Python 3.10+**
- **Tkinter** (Interface Gráfica)
- **Google Generative AI** (`gemini-1.5-flash`)
- **Playwright** (Automação Chromium)
- **Pillow** (Processamento de imagem / Clipboard)
- **Pyperclip** (Gestão da área de transferência)
- **Python-dotenv** (Gestão segura de variáveis de ambiente)

---

## ⚡ Início Rápido

### 1. Clonar o repositório
```bash
git clone https://github.com/MagNumGomes/automacao-NOC.git
cd automacao-NOC
```

### 2. Instalar dependências
```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Configurar a Chave de API
Copie o arquivo de exemplo para `.env`:
```bash
copy .env.example .env
```
No arquivo `.env`, adicione sua chave obtida gratuitamente no [Google AI Studio](https://aistudio.google.com/):
```env
GEMINI_API_KEY=sua_chave_aqui
```

### 4. Executar
```bash
python app_noc.py
```

---

## 📖 Documentação Detalhada

Para instruções detalhadas passo a passo de como operar cada etapa do fluxo de incidentes, consulte o [Manual de Instruções (manual-noc.md)](manual-noc.md).

---

## 📂 Estrutura do Projeto

```
automacao-NOC/
├── app_noc.py          # Código-fonte principal da aplicação Tkinter
├── manual-noc.md       # Manual operacional e fluxo de incidentes
├── README.md           # Visão geral e guia de início rápido
├── requirements.txt    # Dependências do projeto
├── .env.example        # Modelo de variáveis de ambiente
├── .gitignore          # Arquivos e pastas ignorados pelo Git
└── movidesk_profile/   # (Gerado localmente) Sessão persistente do Chromium
```

---

## 🔒 Segurança

- **Chaves de API e Credenciais:** Nunca versione o arquivo `.env`. Ele já está listado no `.gitignore`.
- **Sessões do Navegador:** A pasta `movidesk_profile/` armazena cookies e sessões do Movidesk no seu disco local e também está excluída pelo `.gitignore`.

