# Usa uma imagem base do Python
FROM python:3.11-slim

# Define o diretório de trabalho
WORKDIR /app

# Instala dependências do sistema
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copia os arquivos de requisitos
COPY requirements.txt .

# Instala as dependências do Python
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante do projeto
COPY . .

# Cria as pastas necessárias
RUN mkdir -p /app/arquivos /app/static

# Expõe as portas necessárias
EXPOSE 7861 5000

# Comando para rodar o aplicativo
CMD ["sh", "-c", "python main.py"]