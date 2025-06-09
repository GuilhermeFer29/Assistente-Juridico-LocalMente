import time
from embedding import load_index, alimentar_faiss_com_json

def reprocessar_json_periodicamente(intervalo_horas=1):
    index, textos = load_index()
    while True:
        print("🔁 Reindexando perguntas do JSON...")
        alimentar_faiss_com_json(index, textos, "perguntas_modelo_assistente.json")
        print(f"✅ Reindexação concluída. Aguardando {intervalo_horas} horas para a próxima rodada.")
        time.sleep(intervalo_horas * 1800)  # converte horas em segundos

if __name__ == "__main__":
    reprocessar_json_periodicamente(intervalo_horas=1)  # troca para o intervalo que quiser
