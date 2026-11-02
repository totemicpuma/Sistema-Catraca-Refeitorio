import os
import random
import sys
from datetime import datetime as dt, timedelta, time
import pandas as pd

from app import app, db
from models import Servidor, Aluno, Log, TurmaStatus, Refeicao
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

SERVIDORES = [
    {"nome": "Master",      "matricula": "0", "senha": "0", "adm": True},
    {"nome": "Admin",       "matricula": "1", "senha": "1", "adm": True},
    {"nome": "Admin 2",     "matricula": "2", "senha": "2", "adm": True},
    {"nome": "Servidor",    "matricula": "3", "senha": "3", "adm": False},
    {"nome": "Servidor 2",  "matricula": "4", "senha": "4", "adm": False},
]

REFEICOES = [
    {"nome": "Café da manhã", "hora_inicio": time(6, 0), "hora_fim": time(9, 0)},
    {"nome": "Almoço",        "hora_inicio": time(11, 0), "hora_fim": time(14, 0)},
    {"nome": "Jantar",        "hora_inicio": time(17, 0), "hora_fim": time(20, 0)},
]

# Dados sintéticos de demonstração (sem dados pessoais reais)
CURSOS_DEMO = [
    ("Engenharia de Controle e Automação", ["1", "2", "3", "4"]),
    ("Ciência da Computação", ["1", "2", "3", "4"]),
    ("Técnico em Informática", ["1", "2", "3"]),
    ("Técnico em Eletrotécnica", ["1", "2", "3"]),
]

NOMES_DEMO = [
    "Lucas Ferreira", "Mariana Costa", "Gabriel Almeida", "Beatriz Oliveira",
    "Rafael Santos", "Camila Rodrigues", "Bruno Carvalho", "Larissa Gomes",
    "Thiago Ribeiro", "Amanda Martins", "Felipe Araújo", "Júlia Rocha",
    "Vinícius Barbosa", "Carolina Dias", "Gustavo Castro", "Natália Pinto",
    "Daniel Cardoso", "Letícia Moura", "Henrique Teixeira", "Isabela Correia",
    "Leonardo Mendes", "Sofia Cavalcanti", "Eduardo Monteiro", "Helena Moreira",
    "Rodrigo Freitas", "Clara Vieira", "André Santana", "Laura Marques",
    "Pedro Nogueira", "Alice Machado", "Matheus Azevedo", "Valentina Lima",
    "Caio Lopes", "Lívia Ramos", "Igor Fernandes", "Bianca Soares",
]


def seed():
    with app.app_context():
        db.drop_all()
        db.create_all()

        # --- Servidores ---
        for srv in SERVIDORES:
            s = Servidor(
                nome=srv["nome"],
                matricula=srv["matricula"],
                senha=generate_password_hash(srv["senha"]),
                data_ingresso="2024-02-01",
                adm=srv["adm"]
            )
            db.session.add(s)
        db.session.commit()
        print(f"{len(SERVIDORES)} servidores criados.")
        print("  Matrícula 0, senha 0 -> Master")
        print("  Matrícula 1, senha 1 -> Admin")
        print("  Matrícula 2, senha 2 -> Admin 2")
        print("  Matrícula 3, senha 3 -> Servidor")
        print("  Matrícula 4, senha 4 -> Servidor 2")

        # --- Alunos (Planilha opcional ou geração sintética para demonstração) ---
        caminho_ods = os.environ.get("PLANILHA_ALUNOS", os.path.join(BASE_DIR, "alunos_importacao.ods"))
        alunos = []

        if os.path.exists(caminho_ods):
            df = pd.read_excel(caminho_ods, engine='odf')
            status_excluir = ['PERÍODO FECHADO', 'CANCELADA', 'EM ABERTO']
            if 'Situação Período' in df.columns:
                df = df[~df['Situação Período'].str.strip().str.upper().isin(status_excluir)]

            for _, linha in df.iterrows():
                a = Aluno(
                    nome=linha['Nome'],
                    matricula=str(linha['Matrícula']),
                    curso=linha['Curso'],
                    turma=str(linha['Turma']),
                    permissao=True
                )
                db.session.add(a)
                alunos.append(a)
            db.session.commit()
            print(f"{len(alunos)} alunos importados da planilha.")
        else:
            random.seed(42)
            for idx, nome in enumerate(NOMES_DEMO, start=1):
                curso, turmas = random.choice(CURSOS_DEMO)
                turma = random.choice(turmas)
                matricula = f"202610{idx:05d}"  # Compatível com o padrão 20\d{9} do OCR
                a = Aluno(
                    nome=nome,
                    matricula=matricula,
                    curso=curso,
                    turma=turma,
                    permissao=True
                )
                db.session.add(a)
                alunos.append(a)
            db.session.commit()
            print(f"{len(alunos)} alunos fictícios de demonstração gerados (ex.: matrícula 20261000001).")

        if not alunos:
            print("Nenhum aluno para gerar logs. Seed finalizado.")
            return

        # --- TurmaStatus ---
        combinacoes = set((a.curso, a.turma) for a in alunos)
        for curso, turma in combinacoes:
            db.session.add(TurmaStatus(curso=curso, turma=turma, permissao_ativa=True))
        db.session.commit()
        print(f"{len(combinacoes)} status de turma criados.")

        # --- Refeições ---
        refeicoes = [Refeicao(**r, ativa=True) for r in REFEICOES]
        db.session.add_all(refeicoes)
        db.session.commit()
        print(f"{len(refeicoes)} refeições criadas.")

        # --- Logs (últimos 30 dias) ---
        agora = dt.now()
        logs_criados = 0
        for dias_atras in range(30, -1, -1):
            dia = agora - timedelta(days=dias_atras)
            if dia.weekday() >= 5:
                continue

            for refeicao in refeicoes:
                qtd = random.randint(5, min(len(alunos), 35))
                for aluno in random.sample(alunos, qtd):
                    inicio = dia.replace(
                        hour=refeicao.hora_inicio.hour,
                        minute=refeicao.hora_inicio.minute,
                        second=0
                    )
                    fim = dia.replace(
                        hour=refeicao.hora_fim.hour,
                        minute=refeicao.hora_fim.minute,
                        second=0
                    )
                    data_entrada = inicio + timedelta(
                        seconds=random.randint(0, int((fim - inicio).total_seconds()) - 1)
                    )
                    if data_entrada > agora:
                        continue

                    db.session.add(Log(
                        aluno_id=aluno.id,
                        data_entrada=data_entrada,
                        refeicao_id=refeicao.id
                    ))
                    logs_criados += 1

        db.session.commit()
        print(f"{logs_criados} passagens registradas.")
        print("\nSeed concluído com sucesso!")


if __name__ == "__main__":
    seed()
