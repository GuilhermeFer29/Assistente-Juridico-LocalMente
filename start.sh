#!/bin/bash
while true; do
    echo "=== $(date) ==="
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
    free -h
    sensors | grep "Core"
    sleep 5
done#!/bin/bash

# Script de inicialização do Assistente Jurídico Digital com Docker
# Uso: ./start.sh [--build] [--stop]

# Cores para mensagens
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Função para construir e iniciar os containers
start_application() {
    echo -e "${YELLOW}Iniciando o Assistente Jurídico Digital...${NC}"
    
    # Verifica se o docker-compose está instalado
    if ! command -v docker-compose &> /dev/null; then
        echo -e "${RED}Erro: docker-compose não está instalado.${NC}"
        exit 1
    fi
    
    # Verifica se deve construir as imagens
    if [ "$1" == "--build" ]; then
        echo -e "${GREEN}Construindo as imagens Docker...${NC}"
        docker-compose build
    fi
    
    # Inicia os serviços
    echo -e "${GREEN}Subindo os containers...${NC}"
    docker-compose up -d
    
    # Verifica se os containers estão rodando
    if [ $(docker-compose ps -q | wc -l) -ge 1 ]; then
        echo -e "\n${GREEN}✅ Assistente Jurídico Digital está rodando!${NC}"
        echo -e "\nAcesse a interface em: ${YELLOW}http://localhost:7861${NC}"
        echo -e "API Flask disponível em: ${YELLOW}http://localhost:5000${NC}"
    else
        echo -e "${RED}❌ Erro ao iniciar os containers.${NC}"
        docker-compose logs
        exit 1
    fi
}

# Função para parar os containers
stop_application() {
    echo -e "${YELLOW}Parando o Assistente Jurídico Digital...${NC}"
    docker-compose down
    echo -e "${GREEN}✅ Containers parados com sucesso.${NC}"
}

# Verifica os argumentos
case "$1" in
    "--build")
        start_application "--build"
        ;;
    "--stop")
        stop_application
        ;;
    "")
        start_application
        ;;
    *)
        echo -e "${RED}Uso: ./start.sh [--build] [--stop]${NC}"
        echo -e "  --build  Reconstroi as imagens Docker antes de iniciar"
        echo -e "  --stop   Para os containers"
        exit 1
        ;;
esac