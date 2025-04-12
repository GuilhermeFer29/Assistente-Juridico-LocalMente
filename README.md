# Assistente Jurídico LocalMente

O **Assistente Jurídico LocalMente** é uma aplicação de inteligência artificial desenvolvida para auxiliar profissionais do Direito. Ele realiza análise e consulta de documentos jurídicos utilizando modelos locais de linguagem natural, garantindo segurança e privacidade.

## 🧠 Funcionalidades

- Análise de documentos jurídicos com embeddings locais.
- Geração de respostas contextuais via modelo TinyLLaMA.
- Interface para registro e autenticação de usuários.
- Memória vetorial de consultas.
- Armazenamento local de perguntas e respostas.
- Integração futura com sites jurídicos oficiais.

## 🛠️ Tecnologias Utilizadas

- **Python**
- **FastAPI**
- **Docker**
- **FAISS**
- **SentenceTransformers**
- **SQLite**
- **TinyLLaMA (formato GGUF)**

## 🚀 Como Executar o Projeto

### 1. Clone o repositório

```bash
git clone https://github.com/GuilhermeFer29/Assistente-Juridico-LocalMente.git
cd Assistente-Juridico-LocalMente
```

### 2. Crie a pasta `arquivos` na raiz do projeto

Essa pasta será usada para armazenar arquivos de entrada (PDF, DOCX, EPUB) e o modelo de IA local.

```bash
mkdir arquivos
```

### 3. Baixe o modelo `tinyllama-cpu.gguf`

Você deve fazer o download manual do modelo TinyLLaMA no formato `.gguf` e salvá-lo dentro da pasta `arquivos`.

> 💡 Dica: você pode encontrar modelos TinyLLaMA `.gguf` otimizados para CPU no [Hugging Face](https://huggingface.co/TheBloke/TinyLlama-1.1B-Chat-GGUF) ou [GPT4All](https://gpt4all.io/index.html).

Coloque o arquivo `tinyllama-cpu.gguf` dentro da pasta:

```
Assistente-Juridico-LocalMente/
├── arquivos/
│   └── tinyllama-cpu.gguf
```

### 4. Inicie a aplicação com Docker

```bash
docker-compose up --build
```

Acesse a aplicação em: `http://localhost:7861`

## 📁 Estrutura do Projeto

- `main.py`: Roteamento principal da API.
- `embedding.py`: Conversão de texto em vetores semânticos.
- `llm_loader.py`: Carregamento do modelo TinyLLaMA.
- `db.py`: Banco de dados SQLite local.
- `utils/`: Funções auxiliares.
- `Dockerfile` e `docker-compose.yml`: Configurações de container.

## 📄 Licença

Este projeto está sob a licença MIT. Sinta-se à vontade para usar, modificar e compartilhar.

## 🤝 Contribuições

Contribuições são bem-vindas! Sinta-se à vontade para abrir issues ou pull requests.