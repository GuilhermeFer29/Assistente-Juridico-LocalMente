from sentence_transformers import SentenceTransformer
import faiss
import numpy as np
import os
import pickle
import re
from ebooklib import epub
import pdfplumber
from docx import Document
from bs4 import BeautifulSoup

EMBEDDING_PATH = 'data/faiss_index'
MODEL_NAME = 'all-MiniLM-L6-v2'

# Carregar o modelo de embeddings
model = SentenceTransformer(MODEL_NAME)

def load_index():
    """Carrega o índice FAISS existente ou cria um novo"""
    if os.path.exists(f"{EMBEDDING_PATH}.index") and os.path.exists(f"{EMBEDDING_PATH}.pkl"):
        index = faiss.read_index(f"{EMBEDDING_PATH}.index")
        with open(f"{EMBEDDING_PATH}.pkl", "rb") as f:
            textos = pickle.load(f)
        return index, textos
    else:
        dim = model.get_sentence_embedding_dimension()
        index = faiss.IndexFlatL2(dim)
        return index, []

def save_index(index, textos):
    """Salva o índice FAISS e os textos associados"""
    os.makedirs('data', exist_ok=True)
    faiss.write_index(index, f"{EMBEDDING_PATH}.index")
    with open(f"{EMBEDDING_PATH}.pkl", "wb") as f:
        pickle.dump(textos, f)

def add_embedding(index, textos_existentes, novos_textos):
    """Adiciona novos textos e seus embeddings ao índice"""
    embeddings = model.encode(novos_textos)
    index.add(embeddings)
    textos_existentes.extend(novos_textos)
    save_index(index, textos_existentes)

def search_embedding(index, textos, consulta, k=3):
    """Busca textos similares usando embeddings"""
    if index.ntotal == 0:
        return []

    embedding = model.encode([consulta])
    distancias, indices = index.search(embedding, k)
    
    resultados = []
    for i in indices[0]:
        if i >= 0 and i < len(textos):
            resultados.append(textos[i])
    
    return resultados

# Funções de processamento de texto
def clean_text(text):
    """Limpa o texto removendo caracteres indesejados"""
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^\x00-\x7F]+', '', text)
    return text.strip()

def segment_text(text, max_tokens=512):
    """Segmenta o texto em partes menores"""
    words = text.split()
    segments = []
    current_segment = []
    current_length = 0
    
    for word in words:
        if current_length + len(word) + 1 > max_tokens:
            segments.append(' '.join(current_segment))
            current_segment = []
            current_length = 0
        current_segment.append(word)
        current_length += len(word) + 1
    
    if current_segment:
        segments.append(' '.join(current_segment))
    
    return segments

# Funções para leitura de arquivos
def read_epub(file_path):
    """Lê conteúdo de arquivo EPUB"""
    book = epub.read_epub(file_path)
    text = ''
    for item in book.get_items():
        if item.get_type() == epub.ITEM_DOCUMENT:
            soup = BeautifulSoup(item.get_content(), 'html.parser')
            text += soup.get_text()
    return clean_text(text)

def read_pdf(file_path):
    """Lê conteúdo de arquivo PDF"""
    with pdfplumber.open(file_path) as pdf:
        text = ''
        for page in pdf.pages:
            text += page.extract_text() or ''
    return clean_text(text)

def read_docx(file_path):
    """Lê conteúdo de arquivo DOCX"""
    doc = Document(file_path)
    return clean_text('\n'.join(para.text for para in doc.paragraphs))

def process_file(file_path, file_type):
    """Processa um arquivo e retorna seu texto"""
    if file_type == 'pdf':
        return read_pdf(file_path)
    elif file_type == 'epub':
        return read_epub(file_path)
    elif file_type == 'docx':
        return read_docx(file_path)
    return None

__all__ = ['model', 'load_index', 'save_index', 'add_embedding', 
           'search_embedding', 'clean_text', 'segment_text',
           'read_pdf', 'read_epub', 'read_docx', 'process_file']