FROM python:3.10-slim-bullseye

# Define variáveis de ambiente essenciais
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8 \
    GRADIO_SERVER_NAME=0.0.0.0 \
    GRADIO_SERVER_PORT=7861 \
    FLASK_APP=main.py \
    FLASK_ENV=production \
    LLAMA_CPP_USE_CUBLAS=0 \
    LLAMA_CPP_N_THREADS=4 \
    LLAMA_CPP_LOW_VRAM=1 \
    LLAMA_CPP_N_GPU_LAYERS=0

# Instala dependências do sistema necessárias para compilação e processamento
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1-mesa-glx \
    libglib2.0-0 \
    git \
    && rm -rf /var/lib/apt/lists/*

# Prepara diretório de trabalho
WORKDIR /app

# Cria estrutura de diretórios necessários
RUN mkdir -p /app/static /app/arquivos /app/data /app/cache/ocr /app/models /app/logs

# Copia o arquivo de requisitos e instala dependências
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefer-binary -r requirements.txt && \
    pip install --no-cache-dir gunicorn psutil

# Copia todo o código da aplicação
COPY . .

# Expõe a porta do Gradio
EXPOSE 7861

# Comando para iniciar a aplicação diretamente
CMD ["python", "-m", "flask", "run", "--host=0.0.0.0", "--port=7861"]
