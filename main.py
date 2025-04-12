from db import create_db, salvar_interacao, get_historico, get_historico_completo
from embedding import load_index, add_embedding, search_embedding, process_file, model, segment_text
from llm_loader import get_llm_instance
from password_reset import enviar_email_recuperacao, gerar_token_recuperacao
from datetime import datetime
import os
import sqlite3
import gradio as gr
import numpy as np
import warnings
from flask import send_from_directory
from flask import Flask, request, session, jsonify
from flask_login import LoginManager, UserMixin, current_user, login_user, logout_user, login_required
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
import re
import threading
import requests
from PIL import Image, ImageDraw

# Suprime warnings específicos do ebooklib
warnings.filterwarnings("ignore", category=UserWarning, module='ebooklib')
warnings.filterwarnings("ignore", category=FutureWarning, module='ebooklib')

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

# Configuração de autenticação
app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

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
                segments = segment_text(content)
                add_embedding(index, textos, segments)
                results.append(f"✓ Arquivo {file} indexado com sucesso")
        except Exception as e:
            results.append(f"✗ Erro ao processar {file}: {str(e)}")
    
    return "\n".join(results) if results else "Nenhum arquivo válido encontrado."

def process_question(question, use_history=True, use_embeddings=True):
    """Processa a pergunta e retorna resposta e fonte"""
    resposta, fonte = "", "Modelo Jurídico"
    
    if use_history:
        historico = get_historico(question)
        if historico:
            return "\n\n".join(f"📜 Pergunta: {h[0]}\n⚖️ Resposta: {h[1]}" for h in historico), "Histórico"
    
    if use_embeddings:
        similar = search_embedding(index, textos, question)
        if similar:
            context = "\n".join(similar[:3])
            resposta = llm_loader.generate_response(question, context)
            fonte = "Base de Conhecimento"
    
    if not resposta:
        resposta = llm_loader.generate_response(question)
    
    try:
        embedding = model.encode([question + " " + resposta])[0].tobytes()
    except Exception as e:
        print(f"Erro ao gerar embedding: {str(e)}")
        embedding = None
    
    salvar_interacao(question, resposta, fonte, embedding)
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

        # Lógica de login via API
        def perform_login(username, password):
            if not username or not password:
                return [
                    "❌ Preencha todos os campos", 
                    False, 
                    None, 
                    gr.update(visible=True),  # login_col
                    gr.update(visible=False)  # main_col
                ]
            
            try:
                response = requests.post(
                    "http://localhost:5000/api/login",
                    json={"username": username, "password": password},
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code == 200:
                    return [
                        "✅ Login realizado com sucesso", 
                        True, 
                        username, 
                        gr.update(visible=False),  # login_col
                        gr.update(visible=True)    # main_col
                    ]
                else:
                    error = response.json().get("error", "Erro desconhecido")
                    return [
                        f"❌ {error}", 
                        False, 
                        None, 
                        gr.update(visible=True),  # login_col
                        gr.update(visible=False)  # main_col
                    ]
            except Exception as e:
                return [
                    f"❌ Erro na conexão: {str(e)}", 
                    False, 
                    None, 
                    gr.update(visible=True),  # login_col
                    gr.update(visible=False)  # main_col
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

        # Lógica de logout via API
        def perform_logout():
            try:
                requests.post("http://localhost:5000/api/logout")
            except Exception as e:
                print(f"Erro no logout: {str(e)}")
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

        # Funções protegidas
        def protected_process_question(question, user):
            try:
                response = requests.get("http://localhost:5000/api/check_auth")
                if not response.json().get("authenticated", False):
                    raise gr.Error("Sessão expirada. Faça login novamente.")
                return process_question(question)
            except Exception as e:
                raise gr.Error(f"Erro ao verificar autenticação: {str(e)}")

        submit_btn.click(
            protected_process_question,
            inputs=[question, current_user],
            outputs=[answer, source]
        )

        def protected_process_upload(files, user):
            try:
                response = requests.get("http://localhost:5000/api/check_auth")
                if not response.json().get("authenticated", False):
                    raise gr.Error("Sessão expirada. Faça login novamente.")
                return process_upload(files)
            except Exception as e:
                raise gr.Error(f"Erro ao verificar autenticação: {str(e)}")

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

    return demo

def main():
    """Função principal"""
    # Cria favicon e banco de dados
    create_favicon()
    create_db()
    
    # Cria usuário admin se necessário
    conn = sqlite3.connect('assistent.db')
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM usuarios WHERE email='admin'")
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO usuarios (email, senha_hash, nome, data_cadastro) VALUES (?, ?, ?, ?)",
            ("admin", generate_password_hash("admin123"), "Administrador", datetime.now().isoformat())
        )
        conn.commit()
    conn.close()

    # Cria thread para executar o Flask
    flask_thread = threading.Thread(
        target=lambda: app.run(port=5000, debug=False, use_reloader=False),
        daemon=True
    )
    flask_thread.start()

    # Cria interface Gradio
    interface = create_interface()
    interface.launch(
        server_name="0.0.0.0",
        server_port=7861,
        share=False,
        favicon_path=None
    )

if __name__ == "__main__":
    main()