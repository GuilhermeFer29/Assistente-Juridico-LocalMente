import json

# Função para carregar perguntas do JSON
def carregar_perguntas_json(path="perguntas_modelo_assistente.json"):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("perguntas_juridicas", [])
    except Exception as e:
        print(f"Erro ao carregar perguntas: {e}")
        return []

# Exemplo de uso
if __name__ == "__main__":
    perguntas = carregar_perguntas_json()
    for p in perguntas:
        print(f"Área: {p['area']} — Pergunta: {p['pergunta']}")
