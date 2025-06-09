#!/bin/bash

# Script: clean_docker.sh
# Objetivo: Gerenciar o sistema Assistente Jurídico - limpeza, inicialização, monitoramento, etc.

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m'

# Função para exibir mensagem de ajuda
show_help() {
    echo -e "${CYAN}${BOLD}🚀 SISTEMA ASSISTENTE JURÍDICO - GERENCIAMENTO${NC}"
    echo -e "${YELLOW}Uso: $0 [comando]${NC}"
    echo -e "\nComandos disponíveis:"
    echo -e "  ${GREEN}start${NC} [--build]  - Inicia os containers (opcional: reconstruir imagens)"
    echo -e "  ${GREEN}stop${NC}           - Para os containers"
    echo -e "  ${GREEN}restart${NC}        - Reinicia os containers"
    echo -e "  ${GREEN}update${NC}         - Atualiza o sistema (reconstruindo com todas as mudanças)"
    echo -e "  ${GREEN}monitor${NC}        - Monitora recursos do sistema e containers"
    echo -e "  ${GREEN}logs${NC} [serviço]  - Mostra logs em tempo real (opcional: de um serviço específico)"
    echo -e "  ${GREEN}clean${NC}          - Executa limpeza profunda do Docker"
    echo -e "  ${GREEN}diagnose${NC}       - Executa diagnóstico do sistema"
    echo -e "  ${GREEN}help${NC}           - Mostra esta ajuda"
    echo
    echo -e "${YELLOW}Exemplo: $0 start --build${NC}"
}

# Se nenhum argumento for fornecido, mostrar ajuda
if [ $# -eq 0 ]; then
    show_help
    exit 1
fi

# Processamento de comandos
case "$1" in
    clean)
        echo -e "${CYAN}${BOLD}🚻 LIMPEZA PROFUNDA DO DOCKER${NC}"
        echo -e "${YELLOW}Essa operação removerá todos os containers, imagens não utilizadas e caches.${NC}"
        echo -e "${YELLOW}Use com cuidado em ambiente de produção.${NC}"
        ;;    
    help)
        show_help
        exit 0
        ;;
    start|stop|restart|update|monitor|logs|diagnose)
        # Iremos processar esses comandos abaixo
        ;;
    *)
        echo -e "${RED}Comando desconhecido: $1${NC}"
        show_help
        exit 1
        ;;
esac

# Status antes da limpeza
echo -e "\n${BLUE}${BOLD}📊 STATUS ANTES DA LIMPEZA:${NC}"
docker system df

# Parar e remover todos os containers
echo -e "\n${MAGENTA}⛔ Parando e removendo todos os containers...${NC}"
docker-compose down 2>/dev/null || true
docker stop $(docker ps -a -q) 2>/dev/null || true
docker rm -f $(docker ps -a -q) 2>/dev/null || true
echo -e "${GREEN}✔ Containers removidos${NC}"

# Verificar e limpar o build cache
echo -e "\n${MAGENTA}🔨 Limpando cache de build...${NC}"
docker builder prune -f
echo -e "${GREEN}✔ Cache de build removido${NC}"

# Remover todas as imagens
echo -e "\n${MAGENTA}🗑️ Removendo todas as imagens...${NC}"
docker rmi -f $(docker images -a -q) 2>/dev/null || true
docker image prune -a -f
echo -e "${GREEN}✔ Imagens removidas${NC}"

# Remover volumes não utilizados
echo -e "\n${MAGENTA}📦 Removendo todos os volumes...${NC}"
docker volume prune -f
echo -e "${GREEN}✔ Volumes removidos${NC}"

# Remover todas as redes não utilizadas
echo -e "\n${MAGENTA}🔌 Removendo redes não utilizadas...${NC}"
docker network prune -f
echo -e "${GREEN}✔ Redes removidas${NC}"

# Limpeza total do sistema Docker
echo -e "\n${MAGENTA}🔥 Limpeza profunda do sistema Docker...${NC}"
docker system prune -a -f --volumes
echo -e "${GREEN}✔ Sistema Docker limpo${NC}"

# Status após a limpeza
echo -e "\n${BLUE}${BOLD}📊 STATUS APÓS A LIMPEZA:${NC}"
docker system df

echo -e "\n${GREEN}${BOLD}✅ LIMPEZA COMPLETA CONCLUÍDA COM SUCESSO!${NC}"
echo -e "${CYAN}${BOLD}Para reconstruir o projeto:${NC}"
echo -e "${CYAN}cd $(pwd) && docker-compose build --no-cache && docker-compose up -d${NC}"

# Iniciar o projeto automaticamente, sem perguntar
echo -e "\n${YELLOW}${BOLD}🔧 Reconstruindo projeto...${NC}"
docker-compose build --no-cache
echo -e "${GREEN}✔ Build concluído${NC}"
echo -e "${YELLOW}${BOLD}🚀 Iniciando containers...${NC}"
docker-compose up -d
echo -e "${GREEN}✔ Containers iniciados${NC}"
echo -e "${BLUE}Para ver os logs em tempo real:${NC} docker-compose logs -f"

# Verificar se os containers estão rodando
echo -e "\n${BLUE}${BOLD}🔍 Verificando status dos containers...${NC}"
sleep 5 # Aguardar inicialização
docker-compose ps

# Mostrar informações de acesso
echo -e "\n${GREEN}${BOLD}✅ SISTEMA INICIADO!${NC}"
echo -e "${CYAN}Acesse a interface web em:${NC} http://localhost:7861"
echo -e "${YELLOW}Para parar o sistema:${NC} docker-compose down"