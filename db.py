import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
import os
import logging
import traceback

# Configura logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('db')

DB_PATH = 'assistent.db'

def create_db():
    """Cria todas as tabelas necessárias no banco de dados com tratamento de erros robusto"""
    # Verifica se o diretório para o banco de dados existe
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir, exist_ok=True)
            logger.info(f"Diretório {db_dir} criado para o banco de dados")
        except Exception as e:
            logger.error(f"Erro ao criar diretório para banco de dados: {e}")
            traceback.print_exc()
            raise
    
    conn = None
    try:
        # Tenta conectar com retry em caso de falha
        for attempt in range(3):
            try:
                conn = sqlite3.connect(DB_PATH, timeout=30.0)  # Aumenta timeout para evitar problemas de bloqueio
                conn.isolation_level = None  # Autocommit mode
                cursor = conn.cursor()
                
                # Habilita foreign keys
                cursor.execute('PRAGMA foreign_keys = ON')
                
                # Inicia uma transação para garantir consistência das operações
                cursor.execute('BEGIN TRANSACTION')
                
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
                
                # Adiciona índices para melhorar performance de consultas comuns
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_historico_user_id ON historico(user_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_reset_tokens_email ON reset_tokens(email)')
                
                # Commit da transação
                cursor.execute('COMMIT')
                logger.info("Banco de dados criado/verificado com sucesso")
                return True
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < 2:
                    logger.warning(f"Banco de dados bloqueado, tentativa {attempt+1}/3. Aguardando...")
                    import time
                    time.sleep(2 ** attempt)  # Backoff exponencial
                else:
                    raise
            except Exception as e:
                logger.error(f"Erro ao criar banco de dados (tentativa {attempt+1}): {e}")
                raise
    except Exception as e:
        logger.error(f"Erro crítico ao criar banco de dados: {e}")
        traceback.print_exc()
        if conn:
            try:
                conn.rollback()  # Tenta fazer rollback em caso de erro
            except:
                pass
        raise  # Re-lança a exceção para tratamento em nível superior
    finally:
        # Garante que a conexão sempre será fechada
        if conn:
            try:
                conn.close()
            except Exception as e:
                logger.error(f"Erro ao fechar conexão com banco de dados: {e}")

def salvar_interacao(user_id, pergunta, resposta, fonte=None, embedding=None):
    """Salva uma interação no banco de dados com tratamento de erros"""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        cursor = conn.cursor()
        
        # Verifica se a tabela existe
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='historico'")
        if not cursor.fetchone():
            logger.warning("Tabela 'historico' não encontrada. Criando banco de dados...")
            conn.close()
            create_db()
            conn = sqlite3.connect(DB_PATH, timeout=10.0)
            cursor = conn.cursor()
        
        # Limita o tamanho da pergunta e resposta para evitar erros
        pergunta_safe = pergunta[:2000] if pergunta and len(pergunta) > 2000 else pergunta
        resposta_safe = resposta[:5000] if resposta and len(resposta) > 5000 else resposta
        
        cursor.execute('''
            INSERT INTO historico (user_id, pergunta, resposta, fonte, data)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, pergunta_safe, resposta_safe, fonte, datetime.now().isoformat()))
        conn.commit()
        logger.debug(f"Interação salva para usuário {user_id}")
        return True
    except Exception as e:
        logger.error(f"Erro ao salvar interação: {e}")
        if conn:
            try:
                conn.rollback()
            except:
                pass
        return False
    finally:
        if conn:
            conn.close()

def get_historico(user_id=None, limite=5):
    """Recupera o histórico de interações com tratamento de erros
    
    Args:
        user_id (int): ID do usuário para filtrar o histórico. Se None, retorna histórico geral.
        limite (int): Número máximo de registros a retornar (limitado a 100 por segurança).
        
    Returns:
        list: Lista de tuplas contendo (pergunta, resposta, fonte, data)
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        cursor = conn.cursor()
        
        # Protege contra SQL injection com parâmetros
        if user_id is not None:
            cursor.execute('''
                SELECT pergunta, resposta, fonte, data
                FROM historico
                WHERE user_id = ?
                ORDER BY data DESC
                LIMIT ?
            ''', (user_id, min(limite, 100)))
        else:
            cursor.execute('''
                SELECT pergunta, resposta, fonte, data
                FROM historico
                ORDER BY data DESC
                LIMIT ?
            ''', (min(limite, 100),))
        
        resultados = cursor.fetchall()
        return resultados
    except Exception as e:
        logger.error(f"Erro ao recuperar histórico: {e}")
        return []
    finally:
        if conn:
            conn.close()

def get_historico_completo(user_id):
    """Retorna todo o histórico de um usuário com tratamento de erros"""
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        cursor = conn.cursor()
        
        # Limite de segurança para evitar sobrecarga de memória
        cursor.execute('''
            SELECT id, pergunta, resposta 
            FROM historico 
            WHERE user_id = ?
            ORDER BY data DESC
            LIMIT 500
        ''', (user_id,))
        
        resultados = cursor.fetchall()
        return resultados
    except Exception as e:
        logger.error(f"Erro ao recuperar histórico completo: {e}")
        traceback.print_exc()
        return []
    finally:
        if conn:
            conn.close()

def get_db():
    """Retorna uma conexão com o banco de dados com timeout aumentado"""
    try:
        return sqlite3.connect(DB_PATH, timeout=30.0)
    except Exception as e:
        logger.error(f"Erro ao conectar ao banco de dados: {e}")
        raise