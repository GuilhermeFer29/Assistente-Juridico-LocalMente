# 🧠⚖️ Assistente Jurídico LocalMente

Um sistema completo e 100% local de assistência jurídica com IA. Esse projeto oferece um **assistente digital jurídico** que opera sem necessidade de conexão com a internet, utilizando modelos LLM locais (.gguf via llama.cpp) e uma base vetorial FAISS para busca semântica.

---

## 🚀 Funcionalidades Principais

* ✅ Interface de login e cadastro de usuários com Flask + Gradio
* 🔐 Recuperação de senha via token e envio de e-mail
* 🧠 Processamento e indexação de documentos jurídicos (PDF, DOCX, EPUB)
* 🔍 Busca semântica com embeddings (SentenceTransformers + FAISS)
* 🤖 Geração de resposta jurídica com modelo LLM local ou OpenRouter
* 🗂️ Monitoramento automático de arquivos com Watchdog
* 📊 Registro e consulta de histórico de interações por usuário
* 💡 Interface Gradio com abas (Consulta / Upload de Documentos)

---

## 🧠 Como Funciona

1. Documentos jurídicos são carregados, limpos e segmentados
2. Cada segmento é transformado em embedding vetorial
3. O usuário faz uma pergunta
4. O sistema busca trechos mais relevantes
5. Um modelo de linguagem local responde baseado no contexto
6. A interação é salva e exibida

---

## 📁 Estrutura

```
.
├── main.py                      # App principal (Flask + Gradio)
├── db.py                        # Banco de dados e autenticação
├── llm_loader.py                # Carregamento do modelo LLM (.gguf ou via API)
├── embedding.py                # Indexação e busca semântica (FAISS + ST)
├── index_watcher.py            # Monitor de arquivos automático
├── register.py                 # Tela de cadastro (Gradio)
├── password_reset.py           # Recuperação de senha por token + e-mail
├── carregar_perguntas_json.py  # Adiciona perguntas modelo ao FAISS
├── limpar_faiss.py             # Reseta o índice FAISS
├── data/, cache/, arquivos/    # Pastas de documentos e embeddings
├── static/                     # Assets estáticos (favicon, css)
└── assistent.db                # Banco de dados SQLite
```

---

## 🛠️ Tecnologias

* Python 3.10+
* FAISS + SentenceTransformers
* Llama.cpp (modelos GGUF)
* Flask + Gradio (interface)
* SQLite + Werkzeug Security
* Watchdog (monitoramento de arquivos)
* SMTP (envio de token de redefinição)

---

## ▶️ Execução Rápida

1. **Clone o repositório:**

```bash
git clone https://github.com/GuilhermeFer29/Assistente-Juridico-LocalMente
cd Assistente-Juridico-LocalMente
```

2. **Instale as dependências:**

```bash
pip install -r requirements.txt
```

3. **Inicie a aplicação:**

```bash
python main.py
```

> O sistema abrirá em `http://localhost:7861` com autenticação, consulta e upload.

4. **Configure o modelo local:**

Coloque um modelo `.gguf` em `models/` com nome `tinyllama-cpu.gguf`, ou defina sua chave OpenRouter na variável `OPENROUTER_API_KEY`.

---

## 🔐 Admin Padrão

O sistema cria um usuário padrão no primeiro acesso:

```
E-mail: admin
Senha: admin123
```

---

## 📬 Recuperação de Senha

Configure as credenciais SMTP no `password_reset.py` para envio de token:

```python
SMTP_USER = 'seu_email@gmail.com'
SMTP_PASSWORD = 'sua_senha_app'
```

---

## ✅ Futuras Melhorias

* [ ] Chat com memória contextual
* [ ] Interface via dashboard (Streamlit ou React)
* [ ] Logs de consulta exportáveis
* [ ] Citações com links para artigos
* [ ] Dockerfile + docker-compose para deploy

---

## 👨‍💻 Autor

**Guilherme Fernandes**
🔗 [linkedin.com/in/guilhermefer29](https://linkedin.com/in/guilhermefer29)
📂 [github.com/GuilhermeFer29](https://github.com/GuilhermeFer29)

---

## 📄 Licença

Distribuído sob a licença MIT. Veja o arquivo `LICENSE` para mais detalhes.
