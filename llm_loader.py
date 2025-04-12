from llama_cpp import Llama
from typing import Optional
import time

MODEL_PATH = "models/tinyllama-cpu.gguf"  # Atualize para seu modelo

class LLM_Loader:
    def __init__(self):
        self.llm = None
        self.last_loaded = 0
        self.load_model()

    def load_model(self):
        print("Carregando modelo para CPU Intel i5...")
        self.llm = Llama(
        model_path=MODEL_PATH,
        n_ctx=1024,          # Reduzir contexto para economizar RAM
        n_threads=2,          # 2 threads físicos
        n_threads_batch=2,    # Evitar sobrecarga
        n_gpu_layers=0,       # Modo CPU puro
        use_mlock=True,       # Evitar swapping
        low_vram=True,        # Modo baixo consumo
        verbose=False
        )
        
        self.last_loaded = time.time()

    def generate_response(self, prompt, context: Optional[str] = None, alternative_version: bool = False):
        """Gera resposta com base no prompt e contexto opcional
        Args:
            prompt: Pergunta do usuário
            context: Contexto adicional (opcional)
            alternative_version: Se True, usa a versão alternativa do prompt
        """
        try:
            system_prompt = """Você é um assistente jurídico especializado em Direito Brasileiro. 
            Forneça respostas claras, precisas e baseadas na legislação vigente. 
            Sempre que possível, cite artigos de lei, súmulas ou jurisprudência relevante."""
            
            if alternative_version:
                # Versão alternativa do prompt (mais simples)
                full_prompt = f"""### INSTRUÇÕES:
1. Você é um especialista em Direito Brasileiro
2. Responda de forma técnica e precisa
3. Cite legislação quando possível

### CONTEXTO:
{context if context else 'Nenhum contexto adicional fornecido'}

### PERGUNTA:
{prompt}

### RESPOSTA:"""
            else:
                # Versão original do prompt (com tags especiais)
                full_prompt = f"""[INST] <<SYS>>
{system_prompt}
<</SYS>>

{f'Contexto: {context}\n\n' if context else ''}
Pergunta: {prompt} [/INST]"""
            
            output = self.llm(
                prompt=full_prompt,
                max_tokens=1024,  # Aumentado para respostas mais completas
                temperature=0.3,  # Mais determinístico para respostas jurídicas
                top_p=0.9,
                echo=False,
                stop=["</s>", "[INST]", "###"] if not alternative_version else ["###", "Pergunta:"]
            )
            
            # Processamento da resposta para remover artefatos
            response = output['choices'][0]['text'].strip()
            if alternative_version:
                response = response.split("### RESPOSTA:")[-1].strip()
            
            return response
        
        except Exception as e:
            print(f"Erro ao gerar resposta: {e}")
            return "Desculpe, ocorreu um erro ao processar sua pergunta."

def get_llm_instance():
    """Retorna uma instância única do carregador LLM"""
    global _llm_loader
    if '_llm_loader' not in globals():
        _llm_loader = LLM_Loader()
    return _llm_loader