import os

EMBEDDING_PATH = 'data/faiss_index'

if os.path.exists(f"{EMBEDDING_PATH}.index"):
    os.remove(f"{EMBEDDING_PATH}.index")
    print("🧹 Arquivo FAISS index apagado.")

if os.path.exists(f"{EMBEDDING_PATH}.pkl"):
    os.remove(f"{EMBEDDING_PATH}.pkl")
    print("🧹 Arquivo textos.pkl apagado.")

print("✅ Índice limpo! Pronto para reprocessar com o modelo jurídico iusto-bert.")
