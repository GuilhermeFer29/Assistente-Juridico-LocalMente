#!/bin/bash

# Nome do arquivo de log
LOGFILE="llm_benchmark_$(date +%Y%m%d_%H%M%S).log"

echo "Iniciando monitoramento de memória e swap..." | tee -a "$LOGFILE"
echo "Log será salvo em: $LOGFILE"

# Monitoramento paralelo: grava RAM e SWAP a cada segundo
(
  while true; do
    echo "$(date '+%H:%M:%S') | RAM: $(free -h | grep Mem | awk '{print $3 "/" $2}') | SWAP: $(free -h | grep Swap | awk '{print $3 "/" $2}')" >> "$LOGFILE"
    sleep 1
  done
) &
MONITOR_PID=$!

# Rodar seu script Python de LLM (ajuste o nome se for diferente!)
python3 llm_loader.py | tee -a "$LOGFILE"

# Parar o monitoramento
kill $MONITOR_PID
echo "✅ Benchmark finalizado! Log salvo em: $LOGFILE"
