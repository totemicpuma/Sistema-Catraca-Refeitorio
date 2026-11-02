# Define as tabelas do banco de dados (Servidor, Aluno, Log, etc.)

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime as dt

db = SQLAlchemy()

class Servidor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100))
    matricula = db.Column(db.String(100), unique=True)
    senha = db.Column(db.String(255))
    data_ingresso = db.Column(db.String(20))
    data_expiracao = db.Column(db.String(20))
    adm = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<Servidor {self.nome}>'


class Aluno(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100))
    matricula = db.Column(db.String(50), unique=True)
    curso = db.Column(db.String(100))
    turma = db.Column(db.String(14))
    horario_entrada = db.Column(db.String(20))
    horario_saida = db.Column(db.String(20))
    permissao = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<Aluno {self.nome}>'


class RegistroAcesso(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    aluno_id = db.Column(db.Integer, db.ForeignKey('aluno.id'), nullable=False)
    data_hora = db.Column(db.DateTime, default=dt.now)

    aluno = db.relationship('Aluno', backref=db.backref('acessos', lazy=True))


class TurmaStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    curso = db.Column(db.String(100))
    turma = db.Column(db.String(14))
    permissao_ativa = db.Column(db.Boolean, default=True)


class Refeicao(db.Model):
    """Janela de horário em que o refeitório atende (café, almoço, jantar...).

    O admin cadastra estas janelas na tela de Refeições. Cada passagem de aluno
    é vinculada à refeição vigente no momento da leitura, e é isso que permite a
    regra "uma passagem por refeição por dia".
    """
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), nullable=False)
    hora_inicio = db.Column(db.Time, nullable=False)
    hora_fim = db.Column(db.Time, nullable=False)
    # Bloqueia a refeição sem precisar apagá-la (ex: refeitório fechado hoje).
    ativa = db.Column(db.Boolean, default=True)

    def contem(self, hora):
        """True se `hora` cai dentro da janela. Fim é exclusivo."""
        return self.hora_inicio <= hora < self.hora_fim

    def __repr__(self):
        return f'<Refeicao {self.nome}>'


class Log(db.Model):
    """Uma passagem registrada. Não existe saída: o aluno passa uma única vez
    por refeição por dia, e a catraca apenas registra essa passagem."""
    id = db.Column(db.Integer, primary_key=True)
    aluno_id = db.Column(db.Integer, db.ForeignKey('aluno.id'), nullable=False)
    data_entrada = db.Column(db.DateTime, default=dt.now)
    # Nulo em registros antigos, anteriores ao cadastro de refeições.
    refeicao_id = db.Column(db.Integer, db.ForeignKey('refeicao.id'), nullable=True)

    aluno = db.relationship('Aluno', backref=db.backref('logs', lazy=True))
    refeicao = db.relationship('Refeicao', backref=db.backref('logs', lazy=True))