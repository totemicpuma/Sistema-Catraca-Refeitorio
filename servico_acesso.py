# servico_acesso.py
# -----------------------------------------------------------------------------
# Lógica central de PASSAGEM pelo refeitório.
#
# Esta é a "cola" da unificação: tanto a câmera integrada (camera_catraca.py)
# quanto o receptor MQTT opcional (receptor_mqtt.py, para catracas remotas)
# chamam ESTA MESMA função. Assim, a regra de negócio (aluno existe? tem
# permissão? já comeu esta refeição hoje?) fica em um único lugar, coerente com
# o banco usado pelo dashboard.
#
# REGRA: o sistema apenas REGISTRA a passagem — não há saída. Cada aluno pode
# passar uma única vez por refeição por dia. A segunda leitura da mesma
# matrícula, dentro da mesma refeição e no mesmo dia, é recusada.
# -----------------------------------------------------------------------------

from datetime import datetime as dt

from models import db, Aluno, Log, Refeicao


def refeicao_vigente(agora=None):
    """Devolve a Refeicao cuja janela contém `agora`, ou None.

    Só considera refeições ATIVAS não seria suficiente: precisamos distinguir
    "fora de horário" de "refeição bloqueada pelo admin", então buscamos a
    janela pelo horário e deixamos o chamador olhar o campo `ativa`.
    """
    agora = agora or dt.now()
    hora = agora.time()
    for refeicao in Refeicao.query.order_by(Refeicao.hora_inicio).all():
        if refeicao.contem(hora):
            return refeicao
    return None


def _registro_de_hoje(aluno_id, refeicao_id, agora):
    """Passagem já registrada por este aluno, nesta refeição, hoje."""
    inicio_do_dia = dt(agora.year, agora.month, agora.day)
    return Log.query.filter(
        Log.aluno_id == aluno_id,
        Log.refeicao_id == refeicao_id,
        Log.data_entrada >= inicio_do_dia,
    ).first()


def processar_matricula(app, matricula):
    """Processa uma matrícula lida pela câmera/catraca dentro do contexto Flask.

    Retorna um dicionário padronizado para a UI:
        {"status": "...", "matricula": ..., "nome": ..., "mensagem": ...}

    status possíveis:
        - "entrada"        -> passagem registrada (liberado)
        - "duplicado"      -> já registrou esta refeição hoje
        - "fora_horario"   -> nenhuma refeição acontecendo agora
        - "refeicao_bloqueada" -> refeição existe mas está bloqueada pelo admin
        - "bloqueado"      -> aluno existe mas está sem permissão
        - "nao_cadastrado" -> matrícula não encontrada
        - "erro"           -> falha inesperada
    """
    matricula = (matricula or "").strip()

    with app.app_context():
        try:
            aluno = Aluno.query.filter_by(matricula=matricula).first()

            if not aluno:
                return {
                    "status": "nao_cadastrado",
                    "matricula": matricula,
                    "nome": None,
                    "mensagem": f"Matrícula {matricula} não cadastrada.",
                }

            primeiro_nome = aluno.nome.split()[0] if aluno.nome else "Aluno"

            if not aluno.permissao:
                return {
                    "status": "bloqueado",
                    "matricula": matricula,
                    "nome": aluno.nome,
                    "mensagem": f"{primeiro_nome} está sem permissão.",
                }

            agora = dt.now()
            refeicao = refeicao_vigente(agora)

            if not refeicao:
                return {
                    "status": "fora_horario",
                    "matricula": matricula,
                    "nome": aluno.nome,
                    "mensagem": "Nenhuma refeição está sendo servida agora.",
                }

            if not refeicao.ativa:
                return {
                    "status": "refeicao_bloqueada",
                    "matricula": matricula,
                    "nome": aluno.nome,
                    "mensagem": f"{refeicao.nome} está bloqueado no momento.",
                }

            if _registro_de_hoje(aluno.id, refeicao.id, agora):
                return {
                    "status": "duplicado",
                    "matricula": matricula,
                    "nome": aluno.nome,
                    "mensagem": f"{primeiro_nome} já registrou {refeicao.nome.lower()} hoje.",
                }

            db.session.add(Log(aluno_id=aluno.id, refeicao_id=refeicao.id))
            db.session.commit()
            return {
                "status": "entrada",
                "matricula": matricula,
                "nome": aluno.nome,
                "mensagem": f"Bem-vindo, {primeiro_nome}!",
                "refeicao": refeicao.nome,
            }

        except Exception as e:
            db.session.rollback()
            return {
                "status": "erro",
                "matricula": matricula,
                "nome": None,
                "mensagem": f"Erro no banco de dados: {e}",
            }
