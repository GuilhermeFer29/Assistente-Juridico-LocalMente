import smtplib
import secrets
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from db import get_db
from flask import url_for

# Configurações de e-mail (substitua com suas credenciais)
SMTP_SERVER = 'smtp.seuservidor.com'
SMTP_PORT = 587
SMTP_USER = 'orchestrasmartai@gmail.com'
SMTP_PASSWORD = 'dyoz szhj tswy jpmt'
EMAIL_FROM = 'no-reply@assistentejuridico.com'

def gerar_token_recuperacao(email):
    """Gera e salva um token de recuperação"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Invalida tokens anteriores
    cursor.execute(
        "UPDATE reset_tokens SET usado = 1 WHERE email = ?",
        (email,)
    )
    
    # Gera novo token
    token = secrets.token_urlsafe(32)
    expiracao = (datetime.now() + timedelta(hours=1)).isoformat()
    
    cursor.execute(
        "INSERT INTO reset_tokens (email, token, expiracao) VALUES (?, ?, ?)",
        (email, token, expiracao)
    )
    conn.commit()
    return token

def enviar_email_recuperacao(email, token):
    """Envia e-mail com link de recuperação"""
    reset_url = url_for('reset_password', token=token, _external=True)
    
    mensagem = f"""
    <html>
    <body>
        <h2>Recuperação de Senha - Assistente Jurídico</h2>
        <p>Clique no link abaixo para redefinir sua senha:</p>
        <p><a href="{reset_url}">{reset_url}</a></p>
        <p>O link expira em 1 hora.</p>
        <p>Caso não tenha solicitado esta alteração, ignore este e-mail.</p>
    </body>
    </html>
    """
    
    msg = MIMEText(mensagem, 'html')
    msg['Subject'] = 'Redefinição de Senha - Assistente Jurídico'
    msg['From'] = EMAIL_FROM
    msg['To'] = email
    
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Erro ao enviar e-mail: {e}")
        return False

def verificar_token(token):
    """Verifica se o token é válido"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT email, expiracao FROM reset_tokens WHERE token = ? AND usado = 0",
        (token,)
    )
    resultado = cursor.fetchone()
    
    if not resultado:
        return None
    
    email, expiracao = resultado
    if datetime.now() > datetime.fromisoformat(expiracao):
        return None
    
    return email

def invalidar_token(token):
    """Marca um token como utilizado"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE reset_tokens SET usado = 1 WHERE token = ?",
        (token,)
    )
    conn.commit()