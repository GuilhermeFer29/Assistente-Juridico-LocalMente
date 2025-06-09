from db import create_db, salvar_interacao, get_historico, get_historico_completo
from embedding import segment_text_safe, index_all_files_parallel, iniciar_monitoramento, load_index, add_embedding_from_file, search_embedding, process_file, model
from llm_loader import get_llm_instance
from password_reset import enviar_email_recuperacao, gerar_token_recuperacao
from datetime import datetime
import os
import sys
import sqlite3
import gradio as gr
import numpy as np
import warnings
import traceback
from flask import send_from_directory
from flask import Flask, request, session, jsonify
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user, login_required
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
import re
import threading
import requests
from PIL import Image, ImageDraw
from datetime import timedelta
import time
import logging

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('assistent.log')
    ]
)
logger = logging.getLogger(__name__)

# Variável global para controle de sessão sem depender de Flask-Login
user_id_atual = None

# Suprime warnings específicos do ebooklib
warnings.filterwarnings("ignore", category=UserWarning, module='ebooklib')
warnings.filterwarnings("ignore", category=FutureWarning, module='ebooklib')

def setup_environment():
    """Cria todos os diretórios essenciais do projeto e verifica arquivos críticos"""
    logger.info("Verificando estrutura de diretórios do projeto...")
    # Cria diretórios essenciais
    directories = ['models', 'data', 'cache', 'cache/ocr', 'arquivos', 'static']
    for directory in directories:
        try:
            os.makedirs(directory, exist_ok=True)
            logger.info(f"Diretório {directory} verificado/criado")
        except Exception as e:
            logger.error(f"Erro ao criar diretório {directory}: {e}")
    
    # Verifica arquivos críticos
    if not os.path.exists('models/tinyllama-cpu.gguf'):
        logger.warning("AVISO: Modelo LLM não encontrado em models/tinyllama-cpu.gguf")
        logger.info("O sistema tentará usar a API OpenRouter se configurada")
    
    # Garante permissões corretas para os diretórios
    try:
        for directory in directories:
            os.chmod(directory, 0o777)  # Garante permissões completas
    except Exception as e:
        logger.warning(f"Não foi possível definir permissões para diretórios: {e}")
    
    # Verifica banco de dados
    try:
        if not os.path.exists('assistent.db'):
            logger.info("Banco de dados não encontrado, será criado automaticamente")
    except Exception as e:
        logger.error(f"Erro ao verificar banco de dados: {e}")
    
    return True

# Cores e tema jurídico
THEME = gr.themes.Default(
    primary_hue="indigo",
    secondary_hue="blue",
    neutral_hue="gray",
    font=[gr.themes.GoogleFont("Roboto"), "Arial", "sans-serif"]
).set(
    button_primary_background_fill="#2c3e50",
    button_primary_text_color="#ffffff",
    button_primary_background_fill_hover="#34495e",
    button_secondary_background_fill="#3498db",
    button_secondary_text_color="#ffffff",
)

# Configurações iniciais e app Flask
app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=90)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login_interface'

class User(UserMixin):
    def __init__(self, id, email=None):
        self.id = id
        self.email = email

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect('assistent.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, email FROM usuarios WHERE id = ?", (user_id,))
    usuario = cursor.fetchone()
    conn.close()
    return User(usuario[0], usuario[1]) if usuario else None

# Inicializa componentes
create_db()
index, textos = load_index()
llm_loader = get_llm_instance()

# Rotas de API para autenticação
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"error": "Preencha todos os campos"}), 400
    
    conn = sqlite3.connect('assistent.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, senha_hash, email FROM usuarios WHERE email = ?", (username,))
    usuario = cursor.fetchone()
    conn.close()
    
    if usuario and check_password_hash(usuario[1], password):
        user = User(usuario[0], usuario[2])
        login_user(user)
        return jsonify({"success": True, "message": "Login realizado", "user_id": usuario[0]})
    
    return jsonify({"error": "Credenciais inválidas"}), 401

@app.route('/api/logout', methods=['POST'])
@login_required
def api_logout():
    logout_user()
    return jsonify({"success": True, "message": "Logout realizado"})

@app.route('/api/check_auth', methods=['GET'])
def check_auth():
    return jsonify({"authenticated": current_user.is_authenticated})
@login_manager.unauthorized_handler
def unauthorized_callback():
    return jsonify({"success": False, "message": "Sessão expirada. Faça login novamente."}), 401
  
@app.route('/api/pergunta', methods=['POST'])
@login_required
def api_pergunta():
    data = request.get_json()
    question = data.get("question", "")
    # Passa o ID do usuário atualmente logado
    resposta, fonte = process_question(question, user_id=current_user.id)
    return jsonify({"resposta": resposta, "fonte": fonte})  
# Funções auxiliares
def index_files(files_dir='arquivos/'):
    """Indexa arquivos na pasta especificada"""
    if not os.path.exists(files_dir):
        return "Pasta de arquivos não encontrada."
    
    results = []
    for file in os.listdir(files_dir):
        file_path = os.path.join(files_dir, file)
        file_ext = file.split('.')[-1].lower()
        
        if file_ext not in ['pdf', 'epub', 'docx']:
            continue
            
        try:
            content = process_file(file_path, file_ext)
            if content:
                segments = segment_text_safe(content)
                add_embedding_from_file(index, textos, file_path, file)
                results.append(f"✓ Arquivo {file} indexado com sucesso")
        except Exception as e:
            results.append(f"✗ Erro ao processar {file}: {str(e)}")
    
    return "\n".join(results) if results else "Nenhum arquivo válido encontrado."

def process_question(question, use_history=True, use_embeddings=True, user_id=None):
    """Processa a pergunta e retorna resposta e fonte
    
    Args:
        question (str): A pergunta do usuário
        use_history (bool): Se deve verificar o histórico de perguntas similares
        use_embeddings (bool): Se deve usar embeddings para encontrar conteúdo relevante
        user_id (int): ID do usuário, opcional (usado para salvar a interação)
        
    Returns:
        tuple: (resposta, fonte)
    """
    resposta, fonte = "", "Modelo Jurídico"
    
    if use_history:
        # Se houver um user_id, busca no histórico do usuário
        # Caso contrário, busca no histórico geral (limitado)
        historico = get_historico(user_id, limite=5)
        # Verifica se alguma pergunta similar já foi respondida
        for h in historico:
            if question.lower() in h[0].lower() or h[0].lower() in question.lower():
                return f"📜 Pergunta: {h[0]}\n⚖️ Resposta: {h[1]}", "Histórico"
    
    if use_embeddings:
        similar = search_embedding(index, textos, question)
        if similar:
            resposta = llm_loader.generate_response(question, similar[:3])
            fonte = "Base de Conhecimento"
    
    if not resposta:
        resposta = llm_loader.generate_response(question)
    
    try:
        embedding = model.encode([question + " " + resposta])[0].tobytes()
    except Exception as e:
        logger.error(f"Erro ao gerar embedding: {str(e)}")
        embedding = None
    
    # Salva a interação associada ao usuário (se disponível)
    salvar_interacao(user_id, question, resposta, fonte, embedding)
    return resposta, fonte

def process_upload(files):
    """Processa upload de arquivo corrigido"""
    results = []
    for file in files:
        try:
            filename = file.name
            file_ext = filename.split('.')[-1].lower()
            
            if file_ext not in ['pdf', 'docx', 'epub']:
                results.append(f"✗ Formato {file_ext} não suportado: {filename}")
                continue
            
            os.makedirs('arquivos', exist_ok=True)
            file_path = os.path.join('arquivos', filename)
            
            with open(file_path, "wb") as f:
                f.write(file.read())
            
            results.append(f"✓ Arquivo {filename} carregado com sucesso")
        except Exception as e:
            results.append(f"✗ Erro ao processar arquivo: {str(e)}")
    
    return "\n".join(results) + "\n\n" + index_files()

def is_valid_email(email):
    """Valida o formato do e-mail"""
    return re.match(r"[^@]+@[^@]+\.[^@]+", email)

def create_favicon():
    static_dir = os.path.join(os.path.dirname(__file__), 'static')
    favicon_path = os.path.join(static_dir, 'favicon.ico')
    os.makedirs(static_dir, exist_ok=True)
    
    if not os.path.exists(favicon_path):
        img = Image.new('RGB', (32, 32), color=(44, 62, 80))
        draw = ImageDraw.Draw(img)
        draw.text((8, 8), "⚖", fill=(255, 255, 255))
        img.save(favicon_path, format='ICO')

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                            'favicon.ico', mimetype='image/vnd.microsoft.icon')

def create_interface():
    """Cria interface Gradio com tema jurídico e autenticação"""
    with gr.Blocks(
        title="Assistente Jurídico Digital",
        theme=THEME,
        css="""
        .login-box {
            max-width: 500px;
            margin: auto;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .main-interface {
            margin-top: 20px;
        }
        """
    ) as demo:
        # Estado da sessão
        logged_in = gr.State(False)
        current_user = gr.State(None)

        # Tela de login (inicialmente visível)
        with gr.Column(visible=True, elem_classes="login-box") as login_col:
            gr.Markdown("## 🔐 Login - Assistente Jurídico")
            username = gr.Textbox(label="E-mail")
            password = gr.Textbox(label="Senha", type="password")
            login_btn = gr.Button("Entrar", variant="primary")
            login_status = gr.Markdown()
            
            with gr.Accordion("Primeiro acesso? Cadastre-se", open=False):
                new_username = gr.Textbox(label="E-mail")
                new_password = gr.Textbox(label="Nova senha", type="password")
                confirm_password = gr.Textbox(label="Confirmar senha", type="password")
                register_btn = gr.Button("Cadastrar")
                register_status = gr.Markdown()

            with gr.Accordion("Esqueci minha senha", open=False):
                recovery_email = gr.Textbox(label="E-mail cadastrado")
                recovery_btn = gr.Button("Enviar Link de Recuperação")
                recovery_status = gr.Markdown()

        # Interface principal (inicialmente oculta)
        with gr.Column(visible=False, elem_classes="main-interface") as main_col:
            # Cabeçalho profissional
            with gr.Row():
                gr.HTML("""
                <div style="text-align: center; width: 100%;">
                    <h1 style="color: #2c3e50; font-weight: 600;">⚖️ Assistente Jurídico Digital</h1>
                    <p style="color: #7f8c8d;">Consultoria jurídica inteligente baseada em IA</p>
                    <hr style="border-top: 2px solid #bdc3c7; margin: 10px 0;">
                </div>
                """)
            
            # Abas principais
            with gr.Tabs():
                # Tab de Consulta
                with gr.Tab("📚 Consulta Jurídica", id="consulta"):
                    with gr.Row():
                        with gr.Column(scale=2):
                            question = gr.Textbox(
                                label="Sua Consulta Jurídica",
                                placeholder="Digite sua pergunta sobre Direito Brasileiro...",
                                lines=3,
                                max_lines=6
                            )
                            with gr.Row():
                                submit_btn = gr.Button(
                                    "Enviar Consulta",
                                    variant="primary",
                                    size="lg"
                                )
                                clear_btn = gr.Button(
                                    "Limpar",
                                    variant="secondary"
                                )
                                logout_btn = gr.Button(
                                    "Sair",
                                    variant="stop"
                                )
                        
                        with gr.Column(scale=3):
                            answer = gr.Textbox(
                                label="Parecer Jurídico",
                                interactive=False,
                                lines=12,
                                show_copy_button=True
                            )
                            source = gr.Textbox(
                                label="Fonte da Resposta",
                                interactive=False,
                                visible=True
                            )
                    
                    # Exemplos de perguntas
                    gr.Examples(
                        examples=[
                            "Quais são os requisitos para um contrato de locação válido?",
                            "Como funciona o despejo por falta de pagamento?",
                            "Cite a diferença entre dolo e culpa no Direito Penal"
                        ],
                        inputs=question,
                        label="Exemplos de Perguntas"
                    )
                
                # Tab de Gerenciamento
                with gr.Tab("🗄️ Gerenciamento de Documentos", id="gerenciamento"):
                    with gr.Row():
                        with gr.Column():
                            gr.Markdown("### 📤 Carregar Documentos Jurídicos")
                            upload_btn = gr.UploadButton(
                                "Selecionar Arquivos (PDF/DOCX/EPUB)",
                                file_types=[".pdf", ".docx", ".epub"],
                                file_count="multiple",
                                variant="primary"
                            )
                            gr.Markdown("### 🔍 Indexar Documentos")
                            index_btn = gr.Button(
                                "Processar Documentos",
                                variant="primary"
                            )
                        
                        with gr.Column():
                            output = gr.Textbox(
                                label="Relatório de Processamento",
                                interactive=False,
                                lines=10,
                                show_copy_button=True
                            )
            
            # Rodapé
            gr.HTML("""
            <div style="text-align: center; margin-top: 20px; color: #7f8c8d; font-size: 0.9em;">
                <hr style="border-top: 1px solid #bdc3c7; margin: 10px 0;">
                <p>Assistente Jurídico Digital v1.0 - © 2025 - Não substitui aconselhamento jurídico profissional</p>
            </div>
            """)
        
        # Sessão HTTP
        session_http = requests.Session()

        # Lógica de login integrada diretamente
        def perform_login(username, password):
            if not username or not password:
                return [
                    "❌ Preencha todos os campos", 
                    False, 
                    None, 
                    gr.update(visible=True),  
                    gr.update(visible=False)  
                ]
            
            try:
                # Usa diretamente a lógica de login do Flask
                conn = sqlite3.connect('assistent.db')
                cursor = conn.cursor()
                cursor.execute("SELECT id, senha_hash, email FROM usuarios WHERE email = ?", (username,))
                usuario = cursor.fetchone()
                conn.close()
                
                if usuario and check_password_hash(usuario[1], password):
                    user = User(usuario[0], usuario[2])
                    
                    # Cria uma sessão manualmente - solução alternativa sem Flask-Login
                    try:
                        # Armazena diretamente o ID do usuário em uma variável global
                        global user_id_atual
                        user_id_atual = usuario[0]
                        logger.info(f"Login manual realizado para: {username}")
                        return [
                            "✅ Login realizado com sucesso", 
                            True, 
                            username, 
                            gr.update(visible=False),  
                            gr.update(visible=True)    
                        ]
                    except Exception as inner_e:
                        logger.error(f"Erro no login manual: {inner_e}")
                        raise
                else:
                    return [
                        "❌ Credenciais inválidas", 
                        False, 
                        None, 
                        gr.update(visible=True),  
                        gr.update(visible=False)  
                    ]
            except Exception as e:
                logger.error(f"Erro na autenticação: {str(e)}")
                return [
                    f"❌ Erro na autenticação: {str(e)}", 
                    False, 
                    None, 
                    gr.update(visible=True),  
                    gr.update(visible=False)  
                ]


        # Lógica de cadastro
        def perform_register(new_username, new_password, confirm_password):
            if not all([new_username, new_password, confirm_password]):
                return "❌ Preencha todos os campos", "", ""
            
            if not is_valid_email(new_username):
                return "❌ Formato de e-mail inválido", "", ""
                
            if new_password != confirm_password:
                return "❌ As senhas não coincidem", "", ""
            
            if len(new_password) < 8:
                return "❌ Senha deve ter pelo menos 8 caracteres", "", ""
            
            try:
                conn = sqlite3.connect('assistent.db')
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO usuarios (email, senha_hash, nome, data_cadastro) VALUES (?, ?, ?, ?)",
                    (new_username, generate_password_hash(new_password), "Novo Usuário", datetime.now().isoformat())
                )
                conn.commit()
                return "✅ Cadastro realizado! Faça login.", new_username, ""
            except sqlite3.IntegrityError:
                return "❌ Este e-mail já está cadastrado", "", ""
            except Exception as e:
                print(f"Erro no cadastro: {e}")
                return "❌ Erro ao cadastrar. Tente novamente.", "", ""
            finally:
                conn.close()

        # Lógica de recuperação de senha
        def perform_recovery(email):
            if not email:
                return "❌ Informe um e-mail"
            
            if not is_valid_email(email):
                return "❌ Formato de e-mail inválido"
            
            conn = sqlite3.connect('assistent.db')
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM usuarios WHERE email = ?", (email,))
            if not cursor.fetchone():
                conn.close()
                return "❌ E-mail não encontrado"
            conn.close()
            
            token = gerar_token_recuperacao(email)
            if enviar_email_recuperacao(email, token):
                return "✅ E-mail de recuperação enviado. Verifique sua caixa de entrada."
            return "❌ Erro ao enviar e-mail de recuperação"

        # Lógica de logout integrada (versão alternativa sem Flask-Login)
        def perform_logout():
            try:
                # Usa nossa variável global para gerenciar a sessão
                global user_id_atual
                user_id_atual = None
                logger.info("Logout manual realizado com sucesso.")
            except Exception as e:
                logger.error(f"Erro no logout: {str(e)}")
            return [
                False, 
                None, 
                gr.update(visible=True),  # login_col
                gr.update(visible=False), # main_col
                ""  # login_status
            ]

        # Conecta os eventos
        login_btn.click(
            perform_login,
            inputs=[username, password],
            outputs=[login_status, logged_in, current_user, login_col, main_col]
        )
        
        register_btn.click(
            perform_register,
            inputs=[new_username, new_password, confirm_password],
            outputs=[register_status, username, password]
        )
        
        recovery_btn.click(
            perform_recovery,
            inputs=[recovery_email],
            outputs=[recovery_status]
        )
        
        logout_btn.click(
            perform_logout,
            outputs=[logged_in, current_user, login_col, main_col, login_status]
        )

        def protected_process_question(question, user):
            try:
                # Verifica autenticação usando nossa variável global
                global user_id_atual
                if user_id_atual is None:
                    return "Sessão expirada. Faça login novamente.", "Acesso negado"
                
                # Chama diretamente a função de processamento com o ID do usuário
                resposta, fonte = process_question(question, user_id=user_id_atual)
                return resposta, fonte
            except Exception as e:
                logger.error(f"Erro ao processar pergunta: {str(e)}")
                return f"Erro ao processar pergunta: {str(e)}", "Erro"


        submit_btn.click(
            protected_process_question,
            inputs=[question, current_user],
            outputs=[answer, source]
        )
        
        clear_btn.click(
          lambda: ("", "", ""),
          outputs=[question, answer, source]
        )

        def protected_process_upload(files, user):
            try:
                # Verifica autenticação usando nossa variável global
                global user_id_atual
                if user_id_atual is None:
                    return "Sessão expirada. Faça login novamente."
                    
                # Processa o upload normalmente
                return process_upload(files)
            except Exception as e:
                logger.error(f"Erro ao processar upload: {str(e)}")
                return f"Erro ao processar upload: {str(e)}"

        upload_btn.upload(
            protected_process_upload,
            inputs=[upload_btn, current_user],
            outputs=output
        )

        index_btn.click(
            lambda: index_files(),
            inputs=None,
            outputs=output
        )

        # Final dos handlers da interface
        return demo

def main():
    """Função principal que inicializa todos os componentes"""
    # Configuração inicial do log
    error_log = None
    
    try:
        # Cria arquivo de log detalhado
        error_log = open('error_log.txt', 'a')
        error_log.write(f"\n\n==== INÍCIO DA APLICAÇÃO {datetime.now().isoformat()} ====\n")
    except Exception as e:
        logger.error(f"Erro ao criar arquivo de log: {e}")
        # Continua sem o arquivo de log
    
    try:
        # Instala dependências críticas em runtime, se necessário
        try:
            import pkg_resources
            # Verifica se psutil está instalado
            pkg_resources.get_distribution('psutil')
            logger.info("Dependências críticas verificadas")
        except (pkg_resources.DistributionNotFound, ImportError):
            logger.warning("psutil não encontrado. Tentando instalar...")
            try:
                import subprocess
                subprocess.call([sys.executable, "-m", "pip", "install", "psutil"])
                logger.info("psutil instalado com sucesso")
            except Exception as e:
                logger.error(f"Erro ao instalar dependências: {e}")
                # Continua mesmo sem psutil
        
        # Configura o ambiente
        setup_environment()
        logger.info("Ambiente configurado com sucesso")
        
        # Criação de recursos estáticos
        try:
            create_favicon()
            logger.info("Favicon criado com sucesso")
        except Exception as e:
            logger.error(f"Erro ao criar favicon: {e}")
        
        # Verifica e cria banco de dados - APENAS UMA VEZ
        try:
            create_db()
            logger.info("Banco de dados inicializado com sucesso")
        except Exception as e:
            logger.error(f"Erro ao inicializar banco de dados: {e}")
            logger.warning("Continuando mesmo sem banco de dados")
            traceback.print_exc(file=error_log)
        
        # Inicializa o modelo LLM
        try:
            llm = get_llm_instance()
            if llm and llm.model_available:
                logger.info("Modelo LLM inicializado com sucesso")
            else:
                logger.warning("LLM não disponível. Algumas funcionalidades estarão limitadas.")
        except Exception as e:
            logger.error(f"Erro ao inicializar LLM: {e}")
            logger.warning("Continuando sem LLM. Funcionalidade será limitada")
            traceback.print_exc(file=error_log)
        
        # Cria usuário admin se necessário
        try:
            conn = sqlite3.connect('assistent.db')
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM usuarios WHERE email='admin'")
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO usuarios (email, senha_hash, nome, data_cadastro) VALUES (?, ?, ?, ?)",
                    ("admin", generate_password_hash("admin123"), "Administrador", datetime.now().isoformat())
                )
                conn.commit()
                logger.info("✅ Usuário admin criado com sucesso")
            conn.close()
        except Exception as e:
            logger.error(f"⚠️ Erro ao criar usuário admin: {str(e)}")
            traceback.print_exc(file=error_log)
        
        # Inicializa componentes em paralelo com melhor tratamento de erros
        observer = None
        observers_and_threads = []
        
        # Inicia o monitoramento da pasta 'arquivos/' em background (retorna o observer)
        try:
            observer = iniciar_monitoramento()
            if observer:
                observers_and_threads.append(("observer", observer))
                logger.info("✅ Monitoramento de arquivos iniciado")
            else:
                logger.warning("Monitoramento de arquivos não pôde ser iniciado, continuando...")
        except Exception as e:
            logger.error(f"⚠️ Erro ao iniciar monitoramento: {str(e)}")
            traceback.print_exc(file=error_log)

        # Indexa arquivos já existentes (apenas os novos se force=False)
        def background_index():
            try:
                logger.info("⏳ Iniciando indexação em segundo plano...")
                # Mais conservador nos recursos
                index_all_files_parallel(force=False, num_procs=1)  
                logger.info("✅ Indexação inicial concluída.")
            except Exception as e:
                logger.error(f"⚠️ Erro na indexação: {str(e)}")
                traceback.print_exc(file=error_log)
        
        # Dispara thread separada para indexação com menor prioridade
        try:
            thread_index = threading.Thread(target=background_index, daemon=True, name="IndexThread")
            thread_index.start()
            observers_and_threads.append(("thread_index", thread_index))
            logger.info("Thread de indexação iniciada com sucesso")
        except Exception as e:
            logger.error(f"Erro ao iniciar thread de indexação: {e}")

        logger.info("🧠 Sistema de embeddings está pronto e monitorando novos arquivos.")

        # Configura o Flask para integração com Gradio
        try:
            app.config['SERVER_NAME'] = None  # Previne conflitos de porta
            app.config['APPLICATION_ROOT'] = '/'
            app.config['PREFERRED_URL_SCHEME'] = 'http'
            app.config['SESSION_COOKIE_SECURE'] = False
            app.config['SESSION_COOKIE_HTTPONLY'] = True
            app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Limita uploads a 16MB
            logger.info("✅ Flask configurado para integrar com Gradio")
        except Exception as e:
            logger.error(f"⚠️ Erro ao configurar Flask: {str(e)}")
            traceback.print_exc(file=error_log)

        # Verifica se o LLM foi carregado corretamente
        try:
            llm = get_llm_instance()
            logger.info("LLM carregado com sucesso")
        except Exception as e:
            logger.warning(f"Aviso ao carregar LLM (continuará sem modelo local): {e}")

        # Cria e inicia interface Gradio
        try:
            logger.info("🔄 Iniciando interface Gradio na porta 7861...")
            interface = create_interface()
            try:
                # Configuração de servidor mais robusta
                os.environ['GRADIO_SERVER_NAME'] = "0.0.0.0"
                os.environ['GRADIO_SERVER_PORT'] = "7861"
                # Configuração para evitar conflitos de threading
                os.environ['GRADIO_ALLOW_FLAGGING'] = "never"
                os.environ['GRADIO_NUM_WORKERS'] = "1"
                
                logger.info("Iniciando interface web...")
                
                # Primeiro, tenta iniciar com Gradio
                try:
                    # Inicia a interface Gradio
                    demo = create_interface()
                    
                    # Configura app Flask para servir Gradio
                    app.app = demo.app
                    
                    # Lança Gradio com configurações para estabilidade
                    demo.queue(max_size=10).launch(
                        server_name="0.0.0.0",
                        server_port=7861,
                        share=False,
                        inbrowser=False,
                        auth=None,
                        prevent_thread_lock=True,
                        favicon_path="static/favicon.ico",
                        quiet=True,
                        show_error=True,
                        max_threads=2  # Limita uso de threads
                    )
                    logger.info("Interface Gradio iniciada com sucesso na porta 7861")
                    
                    # Loop principal com tratamento de exceções
                    while True:
                        try:
                            time.sleep(30)  # Heartbeat a cada 30 segundos
                        except KeyboardInterrupt:
                            logger.info("Aplicação encerrada pelo usuário")
                            break
                        except Exception as e:
                            logger.error(f"Erro no loop principal: {e}")
                            # Continua o loop mesmo com erros
                        
                except Exception as gradio_error:
                    # Se falhar com Gradio, tenta apenas Flask
                    logger.error(f"Erro ao iniciar Gradio: {gradio_error}")
                    try:
                        logger.info("Tentando iniciar apenas com Flask...")
                        app.run(
                            host="0.0.0.0", 
                            port=7861, 
                            debug=False, 
                            use_reloader=False, 
                            threaded=True
                        )
                    except Exception as flask_error:
                        logger.error(f"Erro ao iniciar Flask: {flask_error}")
                        raise
            
            except Exception as e:
                logger.critical(f"ERRO FATAL: {e}")
                logger.info("Modo de emergência - Mantendo processo ativo para diagnóstico")
                
                # Modo de emergência mantendo o processo vivo
                contador = 0
                try:
                    while True:
                        time.sleep(10)
                        contador += 1
                        if contador % 6 == 0:  # A cada minuto
                            logger.info(f"HEARTBEAT - {datetime.now().isoformat()}")
                except KeyboardInterrupt:
                    logger.info("Aplicação encerrada pelo usuário")
                        
        except Exception as e:
            logger.critical(f"ERRO FATAL INESPERADO: {str(e)}")
            traceback.print_exc()
            return False
    except Exception as e:
        logger.critical(f"ERRO CATASTRÓFICO: {str(e)}")
        return False
    return True



# A aplicação Flask e o LoginManager já foram inicializados anteriormente
# Atualiza algumas configurações adicionais
app.config['UPLOAD_FOLDER'] = 'arquivos'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)

# Cria a interface Gradio e a integra com Flask
def run_app():
    """Função para iniciar a aplicação Gradio"""
    # Cria a interface
    demo = create_interface()
    
    # Configura o servidor
    return demo.launch(
        server_name=os.getenv('GRADIO_SERVER_NAME', '0.0.0.0'),
        server_port=int(os.getenv('GRADIO_SERVER_PORT', '7861')),
        share=False,
        debug=False,
        show_error=True
    )

# Initialize application on first import
if main():
    interface = run_app()
else:
    logger.critical("Falha ao iniciar a aplicação. Verifique os logs para mais detalhes.")

# Flask entry point
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=7861, debug=False)
