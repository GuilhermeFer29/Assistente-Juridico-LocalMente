from db import init_db, cadastrar_usuario
import gradio as gr

def interface_cadastro():
    with gr.Blocks() as demo:
        gr.Markdown("## 📝 Cadastro - Assistente Jurídico")
        nome = gr.Textbox(label="Nome Completo")
        email = gr.Textbox(label="E-mail")
        senha = gr.Textbox(label="Senha", type="password")
        confirmar_senha = gr.Textbox(label="Confirmar Senha", type="password")
        btn_cadastrar = gr.Button("Cadastrar")
        status = gr.Markdown()
        
        def cadastrar(nome, email, senha, confirmar_senha):
            if senha != confirmar_senha:
                return "❌ As senhas não coincidem"
            
            if len(senha) < 8:
                return "❌ Senha deve ter pelo menos 8 caracteres"
                
            if cadastrar_usuario(email, senha, nome):
                return "✅ Cadastro realizado! Faça login."
            return "❌ E-mail já cadastrado"
            
        btn_cadastrar.click(
            cadastrar,
            inputs=[nome, email, senha, confirmar_senha],
            outputs=status
        )
    
    return demo