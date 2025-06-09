# llm_loader.py — pronto para uso com main.py unificado

import os
import re
import requests
from typing import Optional, Dict, Any, List
import logging
import logging.handlers  # Added import for handlers module
import threading
from pathlib import Path
import time
import traceback
import sys

# Configuração de logging otimizada
# Cria o diretório de logs se não existir
os.makedirs('logs', exist_ok=True)

# Configuração para reduzir volume de logs e aumentar performance
log_file = os.path.join('logs', 'llm.log')

# Handler para arquivo com rotação (evita arquivos enormes)
file_handler = logging.handlers.RotatingFileHandler(
    log_file,
    maxBytes=5*1024*1024,  # 5MB por arquivo
    backupCount=3,         # Mantém até 3 arquivos antigos
    encoding='utf-8'
)

# Handler para console com nível mais alto (reduz volume de saída)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.WARNING)  # Só warnings e erros vão para o console

# Formato otimizado para facilitar a leitura
log_format = '%(asctime)s [%(levelname).1s] %(name)s: %(message).500s'
formatter = logging.Formatter(log_format)
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Configura o logger root (para todos os módulos)
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

# Remove handlers existentes (evita duplicação)
for handler in root_logger.handlers[:]: 
    root_logger.removeHandler(handler)
    
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

# Reduz logs verbose de bibliotecas
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('requests').setLevel(logging.WARNING)
logging.getLogger('sentence_transformers').setLevel(logging.WARNING)
logging.getLogger('transformers').setLevel(logging.ERROR)  # Transformers é muito verbose

# Logger específico para este módulo
logger = logging.getLogger(__name__)

# Importa Llama com tratamento de erro, para evitar falha total se não existir
try:
    from llama_cpp import Llama
    LLAMA_AVAILABLE = True
except ImportError:
    logger.warning("llama_cpp não encontrado. Usando apenas API online.")
    LLAMA_AVAILABLE = False
except Exception as e:
    logger.error(f"Erro ao importar llama_cpp: {e}")
    LLAMA_AVAILABLE = False

# Configuração do modelo principal - modelo único conforme especificado
PRIMARY_MODEL_PATH = "models/tinyllama-cpu.gguf"
FALLBACK_MODEL_PATHS = []  # Sem fallbacks, usar apenas o modelo principal
CONTEXT_WINDOW = 2048  # Um pouco maior para permitir mais contexto
DEFAULT_TEMPERATURE = 0.7
MAX_TOKENS = 1024

class LLM_Loader:
    def __init__(self, max_retries: int = 3):
        self.llm = None
        self.last_loaded = 0
        self.max_retries = max_retries
        self.api_key = os.getenv("OPENROUTER_API_KEY", None)
        self.model_available = False

        if self.api_key:
            logger.info("🔗 OpenRouter API Key detectada. Usando modelo online.")
            self.model_available = True
        elif LLAMA_AVAILABLE:
            try:
                self._initialize_model()
                if self.llm:
                    self.model_available = True
            except Exception as e:
                logger.error(f"Erro ao inicializar modelo local: {str(e)}")
                logger.warning("Continuando sem modelo LLM. Respostas serão limitadas.")
                traceback.print_exc()
        else:
            logger.warning("Biblioteca llama_cpp não disponível e sem API key. Funcionalidade será limitada.")

    def _initialize_model(self):
        """Inicializa o modelo local de forma otimizada com menos logs"""
        try:
            # Evita logs detalhados durante carregamento
            original_levels = {}
            for module in ['llama_cpp', 'sentence_transformers', 'transformers']:
                logger_obj = logging.getLogger(module)
                original_levels[module] = logger_obj.level
                logger_obj.setLevel(logging.ERROR)  # Silencia logs durante carregamento
                
            # Cria diretório models/ se não existir
            os.makedirs(os.path.dirname(PRIMARY_MODEL_PATH), exist_ok=True)
            
            # Verifica se o modelo existe
            if not Path(PRIMARY_MODEL_PATH).exists():
                logger.warning(f"Modelo {PRIMARY_MODEL_PATH} não encontrado. Configure o modelo correto.")
                return False
            
            # Configuração conservadora de memória baseada no ambiente
            try:
                # Tenta detectar memória disponível para evitar OOM
                import psutil
                available_memory_gb = psutil.virtual_memory().available / (1024**3)
                n_threads = max(1, min(4, int(available_memory_gb / 2)))
                
                # Configuração de batch conservadora para ambientes com pouca memória
                if available_memory_gb < 2:  # Menos de 2GB disponível
                    batch_size = 1
                    logger.warning(f"Pouca memória disponível ({available_memory_gb:.1f}GB). Usando configuração mínima.")
                else:
                    batch_size = 1  # Ainda conservador, mas pode ser ajustado
            except Exception:
                # Fallback seguro se não conseguir detectar memória
                n_threads = int(os.getenv("LLAMA_CPP_N_THREADS", "2"))
                batch_size = 1
            
            # Apenas uma tentativa de carregamento com configuração otimizada
            try:
                # Carrega com configurações conservadoras
                self.llm = Llama(
                    model_path=PRIMARY_MODEL_PATH,
                    n_ctx=CONTEXT_WINDOW,
                    n_batch=batch_size,
                    n_threads=n_threads,
                    n_threads_batch=1,
                    n_gpu_layers=int(os.getenv("LLAMA_CPP_N_GPU_LAYERS", "0")),
                    use_mlock=False,
                    low_vram=True,
                    verbose=False,
                    seed=42
                )
                self.last_loaded = time.time()
                self.model_path = PRIMARY_MODEL_PATH
                logger.info(f"Modelo {os.path.basename(PRIMARY_MODEL_PATH)} carregado")
                return True
            except Exception as e:
                logger.error(f"Erro ao carregar o modelo: {str(e)[:200]}")
                if self.api_key:
                    logger.info("Continuando com API online")
                return False
        except Exception as e:
            logger.error(f"Erro na inicialização do modelo: {str(e)}")
            return False
        finally:
            # Restaura níveis de log originais
            for module, level in original_levels.items():
                logging.getLogger(module).setLevel(level)

    def clean_context(self, text: str) -> str:
        return re.sub(r'[^\w\s.,;:!?()\[\]{}<>-]', '', text).strip()

    def _build_prompt(self, prompt: str, context: Optional[str], alternative: bool) -> str:
        instrucao = (
            "Você é um especialista jurídico do sistema legal brasileiro. Forneça respostas completas e precisas "
            "com base na legislação vigente, jurisprudência do STF/STJ e doutrina reconhecida. Inclua sempre:\n"
            "1. Fundamentação legal (ex: Artigo X da Lei Y)\n"
            "2. Posicionamento doutrinário\n"
            "3. Jurisprudência relevante\n"
            "4. Conclusão técnica\n"
            "Mantenha o tom formal e utilize termos jurídicos adequados."
        )

        contexto_texto = f"Contexto: {context}" if context else "Sem contexto adicional."

        return f"""{instrucao}

{contexto_texto}

Pergunta: {prompt}

Resposta:"""

    def generate_response(self, prompt: str, contextos: Optional[List[str]] = None, alternative_version: bool = False) -> str:
        """Gera resposta do modelo, com fallback para métodos alternativos"""
        try:
            # Limpa e prepara o contexto
            context_str = ""
            if contextos:
                cleaned_contexts = [self.clean_context(c) for c in contextos]
                context_str = " ".join(cleaned_contexts)

            # Constrói o prompt completo
            full_prompt = self._build_prompt(prompt, context_str, alternative_version)

            # Decide qual método usar para gerar a resposta
            if self.api_key:
                logger.info("Gerando resposta com modelo online OpenRouter")
                return self._generate_online(full_prompt)
            elif self.llm and LLAMA_AVAILABLE:
                logger.info("Gerando resposta com modelo local")
                return self._generate_local(full_prompt, alternative_version)
            else:
                logger.warning("Nenhum modelo disponível para gerar resposta")
                return self._generate_fallback(prompt, context_str)
        except Exception as e:
            logger.error(f"Erro inesperado ao gerar resposta: {str(e)}")
            traceback.print_exc()
            return "Ocorreu um erro ao processar sua solicitação. Por favor, tente novamente mais tarde."

    def _generate_local(self, prompt, alternative=False):
        """Gera resposta usando o modelo local com tratamento robusto de erros"""
        try:
            start_time = time.time()
            # Se o modelo não estiver carregado ou tiver passado muito tempo, reinicializa
            if not self.llm or (time.time() - self.last_loaded) > 3600:  # 1 hora
                logger.info("Modelo precisa ser reinicializado")
                self._initialize_model()
                if not self.llm:
                    logger.error("Modelo não disponível para geração local")
                    return self._generate_fallback_response(prompt)
            
            # Prevenir entrada muito longa para evitar erros de contexto
            if len(prompt) > CONTEXT_WINDOW * 0.8:  # 80% do tamanho máximo do contexto
                logger.warning(f"Prompt muito longo ({len(prompt)} caracteres), truncando...")
                prompt = prompt[:int(CONTEXT_WINDOW * 0.7)]  # Truncar para 70% do contexto
            
            # Definir temperatura com base no modo alternativo ou não
            temperature = 0.9 if alternative else DEFAULT_TEMPERATURE
            
            # Gera a resposta com timeout
            try:
                # Cria um objeto de evento para interromper a geração se demorar muito
                timeout_event = threading.Event()
                
                # Configura um timer para interromper a geração após 30 segundos
                def _timeout_handler():
                    logger.warning("Timeout atingido na geração de resposta local")
                    timeout_event.set()
                
                timer = threading.Timer(30.0, _timeout_handler)
                timer.daemon = True
                timer.start()
                
                # Gera a resposta
                response = self.llm(
                    prompt, 
                    max_tokens=MAX_TOKENS,
                    stop=["\n\n", "Pergunta:", "pergunta:", "Humano:", "humano:", "###"], 
                    echo=False,
                    temperature=temperature
                )
                
                # Cancela o timer se a resposta for gerada antes do timeout
                timer.cancel()
                
                if timeout_event.is_set():
                    logger.warning("Geração interrompida por timeout")
                    return self._generate_fallback_response(prompt)
                
                # Extrai e limpa a resposta
                full_response = response['choices'][0]['text']
                clean_response = self._clean_model_response(full_response)
                
                generation_time = time.time() - start_time
                logger.info(f"Resposta gerada em {generation_time:.2f} segundos")
                
                return clean_response
                
            except RuntimeError as e:
                if "out of memory" in str(e).lower():
                    logger.error("Erro de memória durante a geração, tentando recuperar modelo...")
                    # Força reload do modelo na próxima execução
                    self.llm = None
                    return self._generate_fallback_response(prompt)
                raise
                
        except KeyboardInterrupt:
            logger.warning("Geração interrompida pelo usuário")
            return "A geração foi interrompida. Por favor, tente novamente."
            
        except Exception as e:
            logger.error(f"Erro ao gerar resposta local: {str(e)}")
            logger.error(traceback.format_exc())
            return self._generate_fallback_response(prompt)
    
    def _clean_model_response(self, text):
        """Limpa a resposta do modelo removendo artefatos indesejados"""
        # Remove instruções ou texto desnecessario no início
        patterns_to_remove = [
            r'^[\s\n]*As (an|a) AI (language model|assistant)[^\n]*\n',
            r'^[\s\n]*I am an AI assistant[^\n]*\n',
            r'^[\s\n]*Based on [^\n]*\n',
            r'^[\s\n]*I apologize,[^\n]*\n',
        ]
        
        for pattern in patterns_to_remove:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
        # Remove whitespace extra no início e fim
        text = text.strip()
        
        return text
    
    def _generate_fallback_response(self, prompt):
        """Gera uma resposta simplificada quando tudo mais falha"""
        if self.api_key:
            # Tenta usar a API como fallback
            try:
                return self._generate_online(prompt)
            except:
                pass
        
        logger.warning("Usando resposta de fallback para o prompt")
        # Resposta genérica quando tudo falha
        return (
            "Não foi possível gerar uma resposta completa devido a limitações do sistema. "
            "Por favor, reformule sua pergunta de forma mais objetiva ou tente novamente mais tarde. "
            "Você também pode consultar diretamente a legislação pertinente ao seu caso."
        )

    def _generate_online(self, full_prompt: str) -> str:
        """Gera resposta usando a API OpenRouter"""
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://assistentejuridico.serverhome.top/",
                "X-Title": "Assistente Jurídico"
            }
            data = {
                "model": "mistralai/mistral-7b-instruct:free",
                "messages": [
                    {"role": "system", "content": self._build_prompt("", None, False)},
                    {"role": "user", "content": full_prompt}
                ],
                "max_tokens": 1024,  # Limite máximo de tokens para a resposta
                "temperature": 0.6,  # Um pouco mais criativo que o local
                "top_p": 0.9
            }

            # Tenta com retry em caso de falha temporária
            for attempt in range(3):
                try:
                    response = requests.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers=headers,
                        json=data,
                        timeout=30  # Timeout de 30s para evitar bloqueio
                    )
                    response.raise_for_status()
                    answer = response.json()['choices'][0]['message']['content']
                    return self._post_process(answer)
                except requests.exceptions.Timeout:
                    logger.warning(f"Timeout ao acessar OpenRouter (tentativa {attempt+1})")
                    if attempt == 2:  # Última tentativa
                        break
                    time.sleep(2 ** attempt)  # Backoff exponencial
                except requests.exceptions.RequestException as e:
                    logger.error(f"Erro de rede ao acessar OpenRouter: {str(e)}")
                    if attempt == 2:  # Última tentativa
                        break
                    time.sleep(2 ** attempt)  # Backoff exponencial
                except (KeyError, IndexError) as e:
                    logger.error(f"Erro no formato da resposta do OpenRouter: {str(e)}")
                    break  # Não tenta novamente para este tipo de erro
                except Exception as e:
                    logger.error(f"Erro desconhecido ao usar OpenRouter: {str(e)}")
                    break  # Não tenta novamente para erros gerais
            
            # Chegou aqui significa que todas as tentativas falharam
            return "⚠️ Não foi possível conectar ao serviço de IA. Tente novamente mais tarde."
        except Exception as e:
            logger.error(f"Erro fatal ao usar OpenRouter: {str(e)}")
            traceback.print_exc()
            return "⚠️ Erro ao consultar o modelo online."

    def _generate_local(self, full_prompt: str, alternative_version: bool) -> str:
        """Gera resposta usando o modelo local"""
        if not self.llm:
            return "⚠️ Modelo local não está disponível. Configure a variável OPENROUTER_API_KEY para usar o modelo online."

        try:
            # Tokenização e verificação do tamanho do prompt
            try:
                tokens = self.llm.tokenize(full_prompt.encode('utf-8'))
                if len(tokens) > CONTEXT_WINDOW:
                    logger.warning(f"Prompt excedeu o limite ({len(tokens)} > {CONTEXT_WINDOW}). Truncando.")
                    tokens = tokens[-(CONTEXT_WINDOW - 100):]  # Deixa espaço para a resposta
                    full_prompt = self.llm.detokenize(tokens).decode('utf-8', errors='ignore')
            except Exception as e:
                logger.warning(f"Erro ao tokenizar prompt: {str(e)}. Usando prompt original.")

            # Configuração mais conservadora para estabilidade
            stop_sequences = ["###", "Pergunta:", "</s>", "Resposta:"] if not alternative_version else ["###", "Pergunta:"]
            
            # Parâmetros mais conservadores para o modelo local
            output: Dict[str, Any] = self.llm(
                prompt=full_prompt,
                max_tokens=256,  # Reduzido para economia de memória
                temperature=0.5,
                top_p=0.7,
                echo=False,
                stop=stop_sequences,
                repeat_penalty=1.1  # Ajuda a evitar repetições
            )
            
            # Verifica e processa a resposta
            if 'choices' in output and len(output['choices']) > 0:
                answer = output['choices'][0]['text'].strip()
                return self._post_process(answer)
            else:
                logger.error("Resposta do modelo local não contém 'choices'")
                return "⚠️ O modelo não conseguiu gerar uma resposta válida."
        except Exception as e:
            logger.error(f"Erro ao gerar resposta local: {str(e)}")
            traceback.print_exc()
            return "⚠️ Erro ao usar o modelo local. Tente novamente mais tarde."

    def _generate_fallback(self, prompt, context_str):
        """Gera uma resposta inteligente mesmo quando não há modelos disponíveis"""
        try:
            # Primeiro, tenta usar a API online como fallback principal
            if self.api_key:
                try:
                    logger.info("Tentando usar API como fallback")
                    full_prompt = self._build_prompt(prompt, context_str, False)
                    return self._generate_online(full_prompt)
                except Exception as e:
                    logger.error(f"Erro ao usar API como fallback: {e}")
            
            # Se chegou aqui, a API também falhou ou não está disponível
            logger.warning("Usando fallback de resposta predefinida")
            
            # Tenta extrair palavras-chave do prompt para personalizar a resposta
            keywords = {
                'constituição': 'a Constituição Federal de 1988',
                'contrato': 'o Código Civil (Lei 10.406/2002) especialmente nos artigos 421 a 480',
                'consumidor': 'o Código de Defesa do Consumidor (Lei 8.078/90)',
                'trabalhista': 'a CLT (Decreto-Lei 5.452/1943)',
                'criminal': 'o Código Penal (Decreto-Lei 2.848/1940)',
                'processo': 'o Código de Processo Civil (Lei 13.105/2015) ou o Código de Processo Penal',
                'administrativa': 'a Lei de Processo Administrativo (Lei 9.784/1999)',
                'tributário': 'o Código Tributário Nacional (Lei 5.172/1966)',
                'ambiental': 'a Lei de Crimes Ambientais (Lei 9.605/1998) e o Código Florestal (Lei 12.651/2012)',
                'empresa': 'a Lei das Sociedades Anônimas (Lei 6.404/1976) ou o Código Civil',
                'aposentadoria': 'a legislação previdenciária (Lei 8.213/1991)',
                'familiar': 'o Código Civil nos capítulos referentes ao Direito de Família',
                'concurso': 'a Lei 8.112/1990 (estatuto dos servidores públicos federais)'
            }
            
            # Detecta se há palavras-chave relevantes
            found_keywords = []
            for keyword, source in keywords.items():
                if keyword in prompt.lower():
                    found_keywords.append(source)
            
            # Construção de resposta de fallback inteligente
            base_response = (
                "Lamento, mas no momento não consigo gerar uma resposta detalhada para sua pergunta. "
            )
            
            # Adiciona sugestões personalizadas se encontrou palavras-chave
            if found_keywords:
                sources_text = ", ".join(found_keywords)
                return base_response + (
                    f"Com base no tema da sua consulta, recomendo verificar {sources_text}. \n\n"
                    "Também sugiro:\n"
                    "1. Consultar a legislação específica no portal do Planalto (www.planalto.gov.br)\n"
                    "2. Verificar jurisprudência nos sites do STF (stf.jus.br) e STJ (stj.jus.br)\n"
                    "3. Buscar orientação de um profissional especializado para seu caso específico\n\n"
                    "Por favor, tente novamente mais tarde ou reformule sua pergunta."
                )
            else:
                # Resposta genérica quando não há palavras-chave
                return base_response + (
                    "Para questões jurídicas, recomendo:\n\n"
                    "1. Consultar o portal da legislação brasileira (www.planalto.gov.br)\n"
                    "2. Buscar informações no site do CNJ (www.cnj.jus.br)\n"
                    "3. Verificar os sites dos tribunais competentes (STF, STJ, TJs, etc.)\n"
                    "4. Procurar orientação jurídica profissional para seu caso específico\n\n"
                    "Por favor, tente novamente mais tarde ou reformule sua pergunta."
                )
        except Exception as e:
            logger.error(f"Erro no sistema de fallback: {e}")
            return "Desculpe, não foi possível processar sua solicitação. Por favor, tente novamente mais tarde."
    def _post_process(self, response: str) -> str:
        response = "\n".join(line.strip() for line in response.split("\n") if line.strip())
        response = re.sub(r' +', ' ', response)
        if "Art." in response and "§" not in response:
            response = response.replace("Art.", "Art. ")
        return response


_llm_loader_instance = None
_llm_lock = threading.Lock()

def get_llm_instance() -> LLM_Loader:
    global _llm_loader_instance
    if _llm_loader_instance is None:
        with _llm_lock:
            if _llm_loader_instance is None:
                _llm_loader_instance = LLM_Loader()
    return _llm_loader_instance
