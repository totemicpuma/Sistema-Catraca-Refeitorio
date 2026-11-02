# Funções auxiliares

from functools import wraps
from flask import session, flash, redirect, url_for
from datetime import datetime as dt_datetime

def servidor_expirado(servidor):
    """vrifica se um servidor está expirado"""
    if servidor.data_expiracao:
        try:
            data_expiracao = dt_datetime.strptime(servidor.data_expiracao, '%Y-%m-%d').date()
            hoje = dt_datetime.now().date()
            return hoje > data_expiracao
        except:
            return False
    return False

def login_obrigatorio(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'usuario_logado' not in session:
            flash("você precisa estar logado!", "erro")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper

def admin_obrigatorio(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'usuario_logado' not in session:
            flash("você precisa estar logado!", "erro")
            return redirect(url_for('login'))
        
        if session.get('tipo_usuario') == 'master':
            return f(*args, **kwargs)
        
        from models import Servidor
        if session.get('tipo_usuario') == 'admin':
            usuario = Servidor.query.get(session.get('usuario_logado'))
            if usuario and usuario.adm:
                return f(*args, **kwargs)
        
        flash("Acesso restrito a administradores!", "erro")
        return redirect(url_for('dashboard'))
    return wrapper

def servidor_obrigatorio(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'usuario_logado' not in session:
            flash("você precisa estar logado!", "erro")
            return redirect(url_for('login'))
        
        if session.get('tipo_usuario') == 'master':
            return f(*args, **kwargs)
        
        if session.get('tipo_usuario') not in ['admin', 'servidor']:
            flash("acesso restrito!", "erro")
            return redirect(url_for('login'))
        
        if session.get('tipo_usuario') == 'servidor':
            from models import Servidor
            servidor = Servidor.query.get(session.get('usuario_logado'))
            if servidor and servidor_expirado(servidor):
                session.pop('usuario_logado', None)
                session.pop('tipo_usuario', None)
                flash("Sua conta expirou. Entre em contato com o administrador.", "erro")
                return redirect(url_for('login'))
        
        return f(*args, **kwargs)
    return wrapper

#msm verificação de smp so q pro master
def master_obrigatorio(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'usuario_logado' not in session:
            flash("você precisa estar logado!", "erro")
            return redirect(url_for('login'))
        
        if session.get('tipo_usuario') == 'master':
            return f(*args, **kwargs)
        
        flash("acesso restrito!", "erro")
        return redirect(url_for('login'))
    return wrapper

def inject_theme():
    tema = session.get("tema", "dark")
    session["tema"] = tema
    return dict(tema=tema)