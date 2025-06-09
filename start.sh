#!/bin/bash

# Script de gerenciamento do Assistente Jurídico Digital
# Uso: ./manage.sh [start|stop|restart|update|monitor|logs]

# Configurações
CONTAINER_NAME="assistente-juridico"
PROJECT_DIR="/DATA/AppData/AssistenteJuridico"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.yml"

# Cores para mensagens
RED='\033[0;31m'
GREEN='\033[0;32m'
BLACK='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Funções principais
start_container() {
    echo -e "${GREEN}Iniciando o Assistente Jurídico...${NC}"
    cd "$PROJECT_DIR" || exit 1
    
    local build_flag=""
    if [ "$1" == "--build" ]; then
        build_flag="--build"
        echo -e "${YELLOW}Reconstruindo imagens...${NC}"
    fi
    
    if docker compose -f "$COMPOSE_FILE" up -d $build_flag; then
        echo -e "${GREEN}✅ Container iniciado com sucesso${NC}"
        echo -e "Acesse: ${BLUE}http://localhost:7861${NC}"
    else
        echo -e "${RED}❌ Falha ao iniciar container${NC}"
        docker compose -f "$COMPOSE_FILE" logs
        return 1
    fi
}

stop_container() {
    echo -e "${YELLOW}Parando o container...${NC}"
    cd "$PROJECT_DIR" || exit 1
    docker compose -f "$COMPOSE_FILE" down
    echo -e "${GREEN}✅ Container parado${NC}"
}

restart_container() {
    stop_container
    start_container
}

update_container() {
    echo -e "${BLUE}Atualizando o container...${NC}"
    cd "$PROJECT_DIR" || exit 1
    docker compose -f "$COMPOSE_FILE" build --no-cache
    start_container
}

monitor_resources() {
    echo -e "${YELLOW}Monitorando recursos... (Ctrl+C para sair)${NC}"
    echo -e "${BLUE}=== Sistema ===${NC}"
    while true; do
        echo -e "\n${YELLOW}=== $(date) ===${NC}"
        
        # Docker stats
        echo -e "\n${BLUE}Container Stats:${NC}"
        docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}\t{{.BlockIO}}"
        
        # System memory
        echo -e "\n${BLUE}Memória do Sistema:${NC}"
        free -h
        
        # CPU temperature
        if sensors &> /dev/null; then
            echo -e "\n${BLUE}Temperatura da CPU:${NC}"
            sensors | grep "Core"
        fi
        
        sleep 5
    done
}

show_logs() {
    echo -e "${YELLOW}Exibindo logs... (Ctrl+C para sair)${NC}"
    cd "$PROJECT_DIR" || exit 1
    docker compose -f "$COMPOSE_FILE" logs -f --tail=50
}

# Menu principal
case "$1" in
    "start")
        if [ "$2" == "--build" ]; then
            start_container "--build"
        else
            start_container
        fi
        ;;
    "stop")
        stop_container
        ;;
    "restart")
        restart_container
        ;;
    "update")
        update_container
        ;;
    "monitor")
        monitor_resources
        ;;
    "logs")
        show_logs
        ;;
    *)
        echo -e "${YELLOW}Uso: ./manage.sh [comando]${NC}"
        echo -e "Comandos disponíveis:"
        echo -e "  ${GREEN}start [--build]${NC} - Inicia o container (opcional: reconstruir imagens)"
        echo -e "  ${RED}stop${NC}          - Para o container"
        echo -e "  ${YELLOW}restart${NC}       - Reinicia o container"
        echo -e "  ${BLUE}update${NC}        - Atualiza o container (reconstruir com todas as mudanças)"
        echo -e "  ${YELLOW}monitor${NC}       - Monitora recursos do sistema e container"
        echo -e "  ${GREEN}logs${NC}          - Mostra os logs em tempo real"
        exit 1
        ;;
esac