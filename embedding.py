
# Bibliotecas principais e para processamento de dados
import os
import re
import gc
import sys
import time
import pickle
import hashlib
import logging
import traceback
import unicodedata
from datetime import datetime
from multiprocessing import Pool, cpu_count

# Bibliotecas para processamento de embeddings
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer

# Bibliotecas para processamento de documentos
from langchain_docling import DoclingLoader

# Bibliotecas para monitoramento de arquivos
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('embedding.log')
    ]
)
logger = logging.getLogger("embedding")


EMBEDDING_PATH = 'data/faiss_index'
MODEL_NAME = 'sentence-transformers/all-MiniLM-L6-v2'
PASTA_ARQUIVOS = 'arquivos'

model = SentenceTransformer(MODEL_NAME, device='cpu', cache_folder='model_cache')
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, cache_dir='model_cache')


def segment_text_safe(text, max_tokens=300):
    tokens = tokenizer.encode(text, add_special_tokens=False)
    segments = []
    for i in range(0, len(tokens), max_tokens):
        chunk = tokens[i:i+max_tokens]
        segments.append(tokenizer.decode(chunk))
    return segments

def load_index():
    try:
        logger.info("Tentando carregar índice existente...")
        if os.path.exists(f"{EMBEDDING_PATH}.index") and os.path.exists(f"{EMBEDDING_PATH}.pkl"):
            index = faiss.read_index(f"{EMBEDDING_PATH}.index")
            with open(f"{EMBEDDING_PATH}.pkl", "rb") as f:
                textos = pickle.load(f)
            logger.info(f"Índice carregado com sucesso. Contém {len(textos)} textos.")
            return index, textos
        else:
            logger.info("Índice não encontrado. Criando novo índice...")
            dim = model.get_sentence_embedding_dimension()
            logger.info(f"Dimensão do embedding: {dim}")
            
            # Criação do índice com sintaxe compatível com várias versões do FAISS
            quantizer = faiss.IndexFlatL2(dim)
            # Uso da sintaxe de posição, não de keyword, para maior compatibilidade
            index = faiss.IndexIVFFlat(quantizer, dim, 100)  # 100 = nlist
            
            # Apenas definir nprobe se o índice foi treinado
            if hasattr(index, "is_trained") and index.is_trained:
                index.nprobe = 10
            
            logger.info("Novo índice criado com sucesso")
            return index, []
    except Exception as e:
        logger.error(f"Erro ao carregar/criar índice FAISS: {e}")
        logger.error(traceback.format_exc())
        
        # Fallback para um índice mais simples em caso de erro
        logger.info("Criando índice simples como fallback...")
        dim = model.get_sentence_embedding_dimension()
        index = faiss.IndexFlatL2(dim)
        return index, []

def save_index(index, textos):
    os.makedirs('data', exist_ok=True)
    faiss.write_index(index, f"{EMBEDDING_PATH}.index")
    with open(f"{EMBEDDING_PATH}.pkl", "wb") as f:
        pickle.dump(textos, f)

def clean_text(text):
    text = re.sub(r'\s+', ' ', text)
    return unicodedata.normalize("NFC", text).strip()

def process_file(file_path, ext=None):
    try:
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        loader = DoclingLoader(file_path=[file_path])
        documents = loader.load()
        return clean_text("\n".join(doc.page_content for doc in documents[:15]))
    except Exception as e:
        print(f"Erro ao processar '{file_path}': {e}")
        return None

def extract_segments(file_path):
    content = process_file(file_path)
    if content:
        return segment_text_safe(content), os.path.basename(file_path)
    return None

def search_embedding(index, textos, consulta, k=3):
    if index.ntotal == 0:
        return []
    embedding = model.encode([consulta], batch_size=2, show_progress_bar=False)
    distancias, indices = index.search(embedding, k)
    return [f"{textos[i]['arquivo']} — {textos[i]['conteudo']}" for i in indices[0] if 0 <= i < len(textos)]

def index_all_files_parallel(force=True, num_procs=None):
    """Indexa arquivos em paralelo com melhor tratamento de erros
    
    Args:
        force (bool): Se True, força a indexação de todos os arquivos
        num_procs (int): Número de processos para usar no pool. Se None, usa ambiente ou default conservador.
    """
    try:
        # Garante que o diretório existe
        os.makedirs(PASTA_ARQUIVOS, exist_ok=True)
        os.makedirs('cache', exist_ok=True)
        os.makedirs('data', exist_ok=True)
        
        # Lista arquivos válidos para indexação
        try:
            arquivos_disponiveis = os.listdir(PASTA_ARQUIVOS)
        except Exception as e:
            logger.error(f"Erro ao listar diretório {PASTA_ARQUIVOS}: {e}")
            arquivos_disponiveis = []
            
        arquivos = [
            os.path.join(PASTA_ARQUIVOS, f)
            for f in arquivos_disponiveis
            if f.endswith(('pdf', 'docx', 'epub')) and (force or not processado_antes(f))
        ]

        # Limpa cache para forçar reprocessamento
        for f in arquivos:
            try:
                cache_path = get_cache_path(f)
                if os.path.exists(cache_path):
                    os.remove(cache_path)
            except Exception as e:
                logger.warning(f"Erro ao limpar cache para {f}: {e}")

        if not arquivos:
            logger.info("ℹ️ Nenhum novo arquivo para indexar")
            return

        # Determina número de processos
        if num_procs is None:
            # Usa o valor de ambiente ou um valor conservador (metade dos CPUs disponíveis, mínimo 1)
            available_cpus = max(1, cpu_count() // 2)
            num_procs = min(int(os.getenv("NUM_EMBED_PROCS", available_cpus)), available_cpus)
        
        logger.info(f"Iniciando indexação com {num_procs} processos para {len(arquivos)} arquivos")
        
        # Processa arquivos em paralelo com timeout para segurança
        with Pool(processes=num_procs) as pool:
            try:
                results = pool.map_async(extract_segments, arquivos).get(timeout=600)  # 10 minutos de timeout
            except Exception as e:
                logger.error(f"Erro durante extração paralela: {e}")
                results = []

        # Carrega índice de embeddings
        try:
            index, textos = load_index()
        except Exception as e:
            logger.error(f"Erro ao carregar índice FAISS: {e}")
            return

        # Processa resultados e adiciona ao índice
        sucessos = 0
        for result in results:
            if result:
                try:
                    segments, nome_arquivo = result
                    if not segments:  # Verificar se há segmentos válidos
                        continue
                        
                    # Usa batch size menor para economia de memória
                    logger.info(f"Gerando embeddings para {nome_arquivo} ({len(segments)} segmentos)")
                    embeddings = model.encode(segments, batch_size=1, show_progress_bar=False)
                    
                    # Treina o índice se necessário
                    if not index.is_trained:
                        logger.info("Treinando índice FAISS")
                        index.train(embeddings)
                        
                    # Adiciona embeddings ao índice
                    index.add(embeddings)
                    
                    # Adiciona metadados à lista de textos
                    for texto in segments:
                        textos.append({
                            "conteudo": texto,
                            "arquivo": nome_arquivo,
                            "data": datetime.now().isoformat()
                        })
                    sucessos += 1
                    
                    # Limpa memória para evitar vazamentos
                    del embeddings
                    gc.collect()
                except Exception as e:
                    logger.error(f"Erro ao processar resultado de {result[1] if len(result)>1 else 'arquivo desconhecido'}: {e}")

        # Salva o índice atualizado
        try:
            save_index(index, textos)
            logger.info(f"✅ {sucessos}/{len(arquivos)} arquivos indexados com sucesso")
        except Exception as e:
            logger.error(f"Erro ao salvar índice FAISS: {e}")
            
    except Exception as e:
        logger.error(f"Erro geral durante indexação paralela: {e}")
        traceback.print_exc()

def alimentar_faiss_com_json(index, textos_existentes, json_path="perguntas_modelo_assistente.json"):
    import json
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            perguntas = [item['pergunta'] for item in json.load(f).get("perguntas_juridicas", [])]

        novas_perguntas = [p for p in perguntas if not any(p == doc['conteudo'] for doc in textos_existentes)]
        if novas_perguntas:
            embeddings = model.encode(novas_perguntas, batch_size=2, show_progress_bar=True)
            if not index.is_trained:
                index.train(embeddings)
            index.add(embeddings)
            for texto in novas_perguntas:
                textos_existentes.append({
                    "conteudo": texto,
                    "arquivo": "perguntas_modelo_assistente.json",
                    "data": datetime.now().isoformat()
                })
            del embeddings
            gc.collect()
            save_index(index, textos_existentes)
            print(f"✅ {len(novas_perguntas)} novas perguntas adicionadas.")
        else:
            print("ℹ️ Nenhuma nova pergunta para adicionar.")
    except Exception as e:
        print(f"Erro ao alimentar com JSON: {e}")

def limpar_duplicatas_e_salvar(index, textos_existentes):
    vistos, textos_unicos = set(), []
    for doc in textos_existentes:
        if doc['conteudo'] not in vistos:
            textos_unicos.append(doc)
            vistos.add(doc['conteudo'])
    if len(textos_unicos) < len(textos_existentes):
        print(f"⚠️ Removendo {len(textos_existentes) - len(textos_unicos)} duplicatas.")
        textos_existentes[:] = textos_unicos
        save_index(index, textos_existentes)

def processado_antes(filename):
    cache_file = os.path.join('cache', hashlib.md5(filename.encode()).hexdigest() + '.pkl')
    return os.path.exists(cache_file)

def get_cache_path(file_path):
    return f"cache/{hashlib.md5(file_path.encode()).hexdigest()}.txt"

def add_embedding_from_file(index, textos_existentes, file_path, nome_arquivo):
    segments = segment_text_safe(process_file(file_path))
    if segments:
        embeddings = model.encode(segments, batch_size=2, show_progress_bar=True)
        if not index.is_trained:
            index.train(embeddings)
        index.add(embeddings)
        for texto in segments:
            textos_existentes.append({
                "conteudo": texto,
                "arquivo": nome_arquivo,
                "data": datetime.now().isoformat()
            })
        del embeddings
        gc.collect()
        save_index(index, textos_existentes)
        print(f"✅ {nome_arquivo} indexado com sucesso.")
    else:
        print(f"⚠️ Nenhum conteúdo válido encontrado em {nome_arquivo}")

class ArquivoNovoHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith(('pdf', 'docx', 'epub')):
            print(f"📥 Novo arquivo detectado: {event.src_path}")
            index, textos = load_index()
            add_embedding_from_file(index, textos, event.src_path, os.path.basename(event.src_path))

def iniciar_monitoramento():
    """Inicia o monitoramento da pasta 'arquivos/' e retorna o observer para o chamador"""
    try:
        # Verifica se o diretório existe e cria se necessário
        if not os.path.exists(PASTA_ARQUIVOS):
            os.makedirs(PASTA_ARQUIVOS, exist_ok=True)
            logger.info(f"Diretório {PASTA_ARQUIVOS} criado")
            
        observer = Observer()
        event_handler = ArquivoNovoHandler()
        observer.schedule(event_handler, path=PASTA_ARQUIVOS, recursive=False)
        observer.start()
        logger.info(f"👀 Monitoramento iniciado em '{PASTA_ARQUIVOS}/'")
        return observer  # Retorna o observer para que o chamador possa gerenciar
    except Exception as e:
        logger.error(f"Erro ao iniciar monitoramento: {e}")
        traceback.print_exc()
        return None  # Retorna None em caso de falha