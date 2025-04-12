import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = 'assistent.db'

def create_db():
    """Cria todas as tabelas necessárias no banco de dados"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Tabela de usuários
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        senha_hash TEXT NOT NULL,
        nome TEXT NOT NULL,
        data_cadastro TEXT NOT NULL,
        perfil TEXT DEFAULT 'user'
    )''')
    
    # Tabela de histórico
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS historico (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        pergunta TEXT NOT NULL,
        resposta TEXT NOT NULL,
        fonte TEXT,
        data TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES usuarios(id)
    )''')
    
    # Tabela de tokens de recuperação
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS reset_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        token TEXT UNIQUE NOT NULL,
        expiracao TEXT NOT NULL,
        usado INTEGER DEFAULT 0
    )''')
    
    conn.commit()
    conn.close()

def salvar_interacao(user_id, pergunta, resposta, fonte=None):
    """Salva uma interação no banco de dados"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO historico (user_id, pergunta, resposta, fonte, data)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, pergunta, resposta, fonte, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_historico(user_id=None, limite=5):
    """Recupera o histórico de interações"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    if user_id:
        cursor.execute('''
            SELECT pergunta, resposta, fonte, data
            FROM historico
            WHERE user_id = ?
            ORDER BY data DESC
            LIMIT ?
        ''', (user_id, limite))
    else:
        cursor.execute('''
            SELECT pergunta, resposta, fonte, data
            FROM historico
            ORDER BY data DESC
            LIMIT ?
        ''', (limite,))
    
    resultados = cursor.fetchall()
    conn.close()
    return resultados

def get_historico_completo(user_id):
    """Retorna todo o histórico de um usuário"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, pergunta, resposta 
        FROM historico 
        WHERE user_id = ?
    ''', (user_id,))
    resultados = cursor.fetchall()
    conn.close()
    return resultados

def get_db():
    """Retorna uma conexão com o banco de dados"""
    return sqlite3.connect(DB_PATH)