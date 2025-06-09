#!/bin/bash

# Script de inicialização para o serviço assistente-juridico (entrypoint.sh)
# Este script trata de problemas comuns e garante o funcionamento correto do serviço

# Configurando log detalhado
exec > >(tee -a /app/startup.log) 2>&1
echo "===== INICIANDO ASSISTENTE JURÍDICO $(date) ====="

# Configuração de ambiente
export PYTHONUNBUFFERED=1
export GRADIO_SERVER_NAME=0.0.0.0
export GRADIO_SERVER_PORT=7861
export GRADIO_NUM_WORKERS=1
export GRADIO_ALLOW_FLAGGING=never

# Cria diretórios essenciais
echo "Criando diretórios necessários..."
mkdir -p /app/models /app/data /app/cache /app/logs /app/arquivos /app/static

# Verificações iniciais
if [ ! -f "/app/models/tinyllama-cpu.gguf" ]; then
    echo "AVISO: Modelo tinyllama-cpu.gguf não encontrado"
    echo "O sistema usará a API online se disponível"
fi

if [ ! -f "/app/assistent.db" ]; then
    echo "Banco de dados não encontrado, será criado automaticamente"
fi

# Instala dependências se necessário
echo "Verificando dependências..."
pip install --no-cache-dir psutil gunicorn

# Inicia o servidor
echo "Iniciando servidor Python..."
cd /app && python -c "from main import main; main()"
