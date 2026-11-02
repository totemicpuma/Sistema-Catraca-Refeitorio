# migrar_refeicoes.py
# -----------------------------------------------------------------------------
# Migração única: adapta um banco existente ao modelo de PASSAGEM por refeição.
#
# O que faz:
#   1. cria a tabela `refeicao` e, se estiver vazia, cadastra as refeições padrão
#   2. adiciona `log.refeicao_id`
#   3. classifica os registros antigos na refeição correspondente ao horário
#   4. remove `log.data_saida` (o sistema não registra mais saída)
#
# Rodar uma vez:  python migrar_refeicoes.py
# É seguro rodar de novo: cada passo verifica se já foi aplicado.
# -----------------------------------------------------------------------------

from datetime import time

from sqlalchemy import inspect, text

from app import app
from models import db, Refeicao

REFEICOES_PADRAO = [
    ("Café da manhã", time(6, 0), time(9, 0)),
    ("Almoço", time(11, 0), time(14, 0)),
    ("Jantar", time(17, 0), time(20, 0)),
]


def _colunas(tabela):
    return {c["name"] for c in inspect(db.engine).get_columns(tabela)}


def migrar():
    with app.app_context():
        db.create_all()

        if not Refeicao.query.first():
            for nome, inicio, fim in REFEICOES_PADRAO:
                db.session.add(Refeicao(nome=nome, hora_inicio=inicio, hora_fim=fim, ativa=True))
            db.session.commit()
            print(f"[OK] {len(REFEICOES_PADRAO)} refeições padrão cadastradas.")
        else:
            print("[--] Refeições já cadastradas, mantidas como estão.")

        colunas = _colunas("log")

        if "refeicao_id" not in colunas:
            db.session.execute(text("ALTER TABLE log ADD COLUMN refeicao_id INTEGER REFERENCES refeicao(id)"))
            db.session.commit()
            print("[OK] Coluna log.refeicao_id adicionada.")
        else:
            print("[--] log.refeicao_id já existe.")

        # Classifica os registros antigos pelo horário da entrada. Os que caírem
        # fora de qualquer janela ficam com refeicao_id nulo — são passagens que
        # aconteceram em horários que hoje não correspondem a nenhuma refeição.
        classificados = 0
        for refeicao in Refeicao.query.all():
            resultado = db.session.execute(
                text(
                    "UPDATE log SET refeicao_id = :rid "
                    "WHERE refeicao_id IS NULL "
                    "AND time(data_entrada) >= :inicio AND time(data_entrada) < :fim"
                ),
                {
                    "rid": refeicao.id,
                    "inicio": refeicao.hora_inicio.strftime("%H:%M:%S"),
                    "fim": refeicao.hora_fim.strftime("%H:%M:%S"),
                },
            )
            classificados += resultado.rowcount
        db.session.commit()
        print(f"[OK] {classificados} registros antigos classificados por refeição.")

        orfaos = db.session.execute(
            text("SELECT COUNT(*) FROM log WHERE refeicao_id IS NULL")
        ).scalar()
        if orfaos:
            print(f"[!!] {orfaos} registros antigos ficaram sem refeição (horário fora das janelas).")

        if "data_saida" in colunas:
            db.session.execute(text("ALTER TABLE log DROP COLUMN data_saida"))
            db.session.commit()
            print("[OK] Coluna log.data_saida removida.")
        else:
            print("[--] log.data_saida já removida.")

        print("\nMigração concluída.")


if __name__ == "__main__":
    migrar()
