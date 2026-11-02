from flask import render_template, request, redirect, url_for, flash, session, jsonify, send_file
import os
import pandas as pd
import secrets
from datetime import datetime as dt, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from collections import defaultdict
from sqlalchemy import func

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from io import BytesIO

from models import Servidor, Aluno, RegistroAcesso, TurmaStatus, Log, Refeicao
from utils import login_obrigatorio, admin_obrigatorio, servidor_obrigatorio, master_obrigatorio
from servico_acesso import processar_matricula, refeicao_vigente

# Status devolvidos por processar_matricula que representam passagem registrada.
_STATUS_SUCESSO = ("entrada",)

_attempts = defaultdict(list)

def _limpar_tentativas():
    agora = dt.now()
    for ip in list(_attempts.keys()):
        _attempts[ip] = [t for t in _attempts[ip] if agora - t < timedelta(minutes=15)]
        if not _attempts[ip]:
            del _attempts[ip]

def _rate_limit():
    _limpar_tentativas()
    ip = request.remote_addr or "unknown"
    tentativas = len(_attempts[ip])
    if tentativas >= 10:
        return True
    _attempts[ip].append(dt.now())
    return False

def configure_routes(app, db):
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))

    def _publico_payload():
        hoje = dt.now().date()
        hoje_inicio = dt(hoje.year, hoje.month, hoje.day, 0, 0, 0)

        logs = db.session.query(Log, Aluno).join(Aluno).filter(
            Log.data_entrada >= hoje_inicio
        ).order_by(Log.data_entrada.desc()).limit(12).all()
        total_hoje = Log.query.filter(Log.data_entrada >= hoje_inicio).count()

        items = []
        for log, aluno in logs:
            items.append({
                "id": log.id,
                "nome": aluno.nome,
                "curso": aluno.curso or "",
                "turma": aluno.turma or "",
                "entrada": log.data_entrada.strftime('%H:%M'),
                "refeicao": log.refeicao.nome if log.refeicao else "",
            })

        refeicao = refeicao_vigente()
        return {
            "total_hoje": total_hoje,
            "logs": items,
            "refeicao_atual": refeicao.nome if refeicao and refeicao.ativa else None,
        }

    def _ids_ja_registrados(refeicao):
        """Alunos que já passaram nesta refeição hoje — usado para marcar quem
        não pode mais passar e desabilitar o registro manual."""
        if not refeicao:
            return set()
        hoje = dt.now().date()
        hoje_inicio = dt(hoje.year, hoje.month, hoje.day, 0, 0, 0)
        return {
            log.aluno_id
            for log in Log.query.filter(
                Log.refeicao_id == refeicao.id, Log.data_entrada >= hoje_inicio
            ).all()
        }

    def _csrf_token():
        if '_csrf_token' not in session:
            session['_csrf_token'] = secrets.token_hex(32)
        return session['_csrf_token']

    @app.context_processor
    def inject_csrf():
        return dict(csrf_token=_csrf_token())

    def _validar_csrf():
        token = request.form.get('_csrf_token')
        if not token or token != session.get('_csrf_token'):
            flash("Requisição inválida. Tente novamente.", "erro")
            return False
        return True

    def _verificar_senha_admin(senha):
        usuario = Servidor.query.get(session.get('usuario_logado'))
        return usuario and check_password_hash(usuario.senha, senha)

    def _senha_valida(senha):
        if len(senha) < 4:
            return False
        return True

    @app.route("/", methods=["GET", "POST"])
    def pagina_publica():
        if request.method == "POST":
            # A página pública chama esta rota via fetch (sem reload) pra poder
            # tocar o som certo e mostrar o aviso de matrícula errada. O form
            # continua funcionando sem JS (fallback), por isso os dois caminhos.
            quer_json = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            matricula_form = request.form.get('matricula', '').strip()

            if not matricula_form:
                if quer_json:
                    return jsonify(status="vazio", matricula="", nome=None,
                                    mensagem="Informe sua matrícula para continuar."), 400
                flash("Informe sua matrícula para continuar.", "erro")
                return redirect(url_for('pagina_publica'))

            resultado = processar_matricula(app, matricula_form)

            if quer_json:
                return jsonify(**resultado)

            categoria = "sucesso" if resultado["status"] in _STATUS_SUCESSO else "erro"
            flash(resultado["mensagem"], categoria)
            return redirect(url_for('pagina_publica'))

        payload = _publico_payload()
        return render_template("publico_refeitorio.html",
                               logs=payload["logs"],
                               total_hoje=payload["total_hoje"],
                               refeicao_atual=payload["refeicao_atual"])

    @app.route("/api/publico_status")
    def api_publico_status():
        return jsonify(_publico_payload())

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            if _rate_limit():
                flash("Muitas tentativas. Aguarde 15 minutos.", "erro")
                return render_template("login.html")

            matricula_form = request.form.get('matricula', '').strip()
            senha_form = request.form.get('senha', '')

            usuario = Servidor.query.filter_by(matricula=matricula_form).first()

            if not matricula_form or not senha_form:
                flash("Matrícula ou senha incorretas.", "erro")
                return render_template("login.html")

            if usuario and check_password_hash(usuario.senha, senha_form):
                if usuario.data_expiracao:
                    try:
                        data_expiracao = dt.strptime(usuario.data_expiracao, '%Y-%m-%d').date()
                        hoje = dt.now().date()
                        if hoje > data_expiracao:
                            flash("Sua conta expirou. Entre em contato com o administrador.", "erro")
                            return redirect(url_for('login'))
                    except:
                        pass

                session.clear()
                session['usuario_logado'] = usuario.id
                session['nome_usuario'] = usuario.nome
                if usuario.adm and usuario.matricula == "0":
                    session['tipo_usuario'] = 'master'
                else:
                    session['tipo_usuario'] = 'admin' if usuario.adm else 'servidor'
                return redirect(url_for('dashboard'))

            flash("Matrícula ou senha incorretas.", "erro")
        return render_template("login.html")

    @app.route("/menu")
    @admin_obrigatorio
    def redirect_menu():
        return redirect(url_for('painel'), 301)

    @app.route("/painel")
    @admin_obrigatorio
    def painel():
        from utils import servidor_expirado
        from datetime import date
        lista_servidores = Servidor.query.all()

        hoje = date.today()
        for servidor in lista_servidores:
            servidor.esta_expirado = servidor_expirado(servidor)
            servidor.dias_restantes = None
            if servidor.data_expiracao and not servidor.esta_expirado:
                try:
                    data_exp = dt.strptime(servidor.data_expiracao, '%Y-%m-%d').date()
                    servidor.dias_restantes = (data_exp - hoje).days
                except:
                    pass

        total = len(lista_servidores)
        admins = sum(1 for s in lista_servidores if s.adm)
        servidores_count = total - admins
        expirados = sum(1 for s in lista_servidores if s.esta_expirado)
        ativos = total - expirados

        return render_template("painelAdm.html",
                               servidores=lista_servidores,
                               stats={"total": total, "admins": admins,
                                      "servidores": servidores_count,
                                      "expirados": expirados, "ativos": ativos})

    @app.route("/painel_master")
    @master_obrigatorio
    def painel_master():
        from utils import servidor_expirado
        from datetime import date
        lista_servidores = Servidor.query.all()

        hoje = date.today()
        for servidor in lista_servidores:
            servidor.esta_expirado = servidor_expirado(servidor)
            servidor.dias_restantes = None
            if servidor.data_expiracao and not servidor.esta_expirado:
                try:
                    data_exp = dt.strptime(servidor.data_expiracao, '%Y-%m-%d').date()
                    servidor.dias_restantes = (data_exp - hoje).days
                except:
                    pass

        return render_template("painelMaster.html", servidores=lista_servidores)

    @app.route("/editar_servidor/<int:id>", methods=["GET", "POST"])
    @admin_obrigatorio
    def editar_servidor(id):
        servidor = Servidor.query.get_or_404(id)

        if session.get('tipo_usuario') != 'master' and servidor.adm:
            flash("Você não pode gerenciar outro administrador.", "erro")
            return redirect(url_for('painel'))

        if request.method == "POST":
            if not _validar_csrf():
                return redirect(url_for('painel_master' if session.get('tipo_usuario') == 'master' else 'painel'))

            acao = request.form.get('acao')

            if session.get('tipo_usuario') != 'master' and acao == 'promover':
                flash("Apenas o Master pode promover servidores.", "erro")
                return redirect(url_for('painel' if session.get('tipo_usuario') == 'admin' else 'painel_master'))

            if acao in ('promover', 'rebaixar', 'excluir') and not _verificar_senha_admin(request.form.get("senha", "")):
                flash("Senha incorreta. Operação cancelada.", "erro")
                return redirect(url_for('painel' if session.get('tipo_usuario') == 'admin' else 'painel_master'))

            if acao == 'promover':
                servidor.adm = True
                db.session.commit()
                flash(f"Servidor {servidor.nome} promovido a administrador com sucesso!", "sucesso")
            elif acao == 'rebaixar':
                servidor.adm = False
                db.session.commit()
                flash(f"Servidor {servidor.nome} rebaixado de adm com sucesso!", "sucesso")
            elif acao == 'excluir':
                nome_servidor = servidor.nome
                db.session.delete(servidor)
                db.session.commit()
                flash(f"Servidor {nome_servidor} removido com sucesso!", "sucesso")

            if session.get('tipo_usuario') == 'master':
                return redirect(url_for('painel_master'))
            return redirect(url_for('painel'))

        return render_template("editar_servidor.html", servidor=servidor)

    @app.route("/tabelas")
    @servidor_obrigatorio
    def redirect_tabelas():
        return redirect(url_for('gestao_turmas'), 301)

    @app.route("/gestao_turmas")
    @servidor_obrigatorio
    def gestao_turmas():
        turmas = db.session.query(Aluno.curso, Aluno.turma).distinct().order_by(Aluno.curso).all()
        status_list = TurmaStatus.query.all()
        todos_alunos = Aluno.query.order_by(Aluno.nome).all()
        alunos_por_turma = {}
        for aluno in todos_alunos:
            chave = (aluno.curso, aluno.turma)
            if chave not in alunos_por_turma:
                alunos_por_turma[chave] = []
            alunos_por_turma[chave].append(aluno)

        total_turmas = len(turmas)
        total_alunos = len(todos_alunos)
        turmas_liberadas = 0
        turmas_bloqueadas = 0
        status_map = {(s.curso, s.turma): s.permissao_ativa for s in status_list}
        for curso, turma in turmas:
            perm = status_map.get((curso, turma), True)
            if perm:
                turmas_liberadas += 1
            else:
                turmas_bloqueadas += 1

        alunos_json = [{"nome": a.nome, "matricula": a.matricula, "curso": a.curso, "turma": a.turma}
                        for a in todos_alunos]

        return render_template("gestao_turmas.html", turmas=turmas, status_list=status_list,
                               alunos_por_turma=alunos_por_turma, total_turmas=total_turmas,
                               total_alunos=total_alunos, turmas_liberadas=turmas_liberadas,
                               turmas_bloqueadas=turmas_bloqueadas, alunos_json=alunos_json)

    @app.route("/fluxo")
    @servidor_obrigatorio
    def redirect_fluxo():
        return redirect(url_for('fluxo_refeitorio'), 301)

    @app.route("/fluxo_refeitorio")
    @servidor_obrigatorio
    def fluxo_refeitorio():
        hoje = dt.now().date()
        hoje_inicio = dt(hoje.year, hoje.month, hoje.day, 0, 0, 0)
        todos_logs = db.session.query(Log, Aluno).join(Aluno).filter(
            Log.data_entrada >= hoje_inicio
        ).order_by(Log.data_entrada.desc()).all()
        alunos_unicos = len({log.aluno_id for log, _ in todos_logs})
        refeicao = refeicao_vigente()
        return render_template("fluxo_refeitorio.html",
                               logs=todos_logs,
                               alunos_unicos=alunos_unicos,
                               refeicao_atual=refeicao.nome if refeicao and refeicao.ativa else None)

    @app.route("/cadastro")
    @admin_obrigatorio
    def redirect_cadastro():
        return redirect(url_for('cadastro_servidor'), 301)

    @app.route("/cadastro_servidor", methods=["GET", "POST"])
    @admin_obrigatorio
    def cadastro_servidor():
        form = dict(nome="", matricula="", adm=False,
                     data_ingresso=dt.now().strftime("%Y-%m-%d"),
                     usar_expiracao=False, data_expiracao="")
        if request.method == "POST":
            form["nome"] = request.form.get('nome', '').strip()
            form["matricula"] = request.form.get('matricula', '').strip()
            form["data_ingresso"] = request.form.get('data_ingresso', '')
            form["usar_expiracao"] = request.form.get('usar_expiracao') == 'on'
            form["data_expiracao"] = request.form.get('data_expiracao', '')
            form["adm"] = session.get('tipo_usuario') == 'master' and request.form.get('cargo') == 'admin'
            senha_form = request.form.get('senha', '')

            if not _validar_csrf():
                return render_template("cadastro_servidor.html", **form)

            if not _verificar_senha_admin(request.form.get("senha_admin", "")):
                flash("Senha do administrador incorreta.", "erro")
                return render_template("cadastro_servidor.html", **form)

            if not form["nome"] or not form["matricula"] or not senha_form:
                flash("Preencha todos os campos obrigatórios.", "erro")
                return render_template("cadastro_servidor.html", **form)

            if not _senha_valida(senha_form):
                flash("A senha deve ter no mínimo 4 caracteres.", "erro")
                return render_template("cadastro_servidor.html", **form)

            if Servidor.query.filter_by(matricula=form["matricula"]).first():
                flash("Já existe um servidor com essa matrícula", "erro")
                return render_template("cadastro_servidor.html", **form)

            senha_hash = generate_password_hash(senha_form)
            data_expiracao = form["data_expiracao"] if form["usar_expiracao"] and form["data_expiracao"] else None

            novo_servidor = Servidor(nome=form["nome"], matricula=form["matricula"],
                                     senha=senha_hash, adm=form["adm"],
                                     data_ingresso=form["data_ingresso"],
                                     data_expiracao=data_expiracao)

            db.session.add(novo_servidor)
            db.session.commit()

            if session.get('tipo_usuario') == 'master':
                return redirect(url_for('painel_master'))
            return redirect(url_for('painel'))

        return render_template("cadastro_servidor.html")

    @app.route("/logout", methods=["POST"])
    def logout():
        session.clear()
        flash("Você saiu do sistema.", "sucesso")
        return redirect(url_for('login'))

    @app.route("/remover/<int:id>", methods=["POST"])
    @admin_obrigatorio
    def remover_servidor(id):
        if not _validar_csrf():
            return redirect(url_for('painel_master' if session.get('tipo_usuario') == 'master' else 'painel'))

        if session.get('tipo_usuario') != 'master':
            servidor_alvo = Servidor.query.get(id)
            if servidor_alvo and servidor_alvo.adm:
                flash("Você não pode remover outro administrador.", "erro")
                return redirect(url_for('painel'))
        if not _verificar_senha_admin(request.form.get("senha", "")):
            flash("Senha incorreta. Operação cancelada.", "erro")
            return redirect(url_for('painel_master' if session.get('tipo_usuario') == 'master' else 'painel'))
        servidor_deletar = Servidor.query.get_or_404(id)
        try:
            db.session.delete(servidor_deletar)
            db.session.commit()
            flash("Servidor removido com sucesso", "sucesso")
        except:
            flash("Erro ao tentar remover o servidor.", "erro")
        if session.get('tipo_usuario') == 'master':
            return redirect(url_for('painel_master'))
        return redirect(url_for('painel'))

    @app.route("/importar_aluno", methods=["POST"])
    @servidor_obrigatorio
    def importar_aluno():
        if not _validar_csrf():
            return redirect(url_for('painel'))

        matricula_digitada = request.form.get('matricula', '')

        if not matricula_digitada:
            flash("Informe uma matrícula.", "erro")
            return redirect(url_for('painel'))

        try:
            caminho_arquivo = os.environ.get("PLANILHA_ALUNOS", os.path.join(BASE_DIR, "alunos_importacao.ods"))
            df = pd.read_excel(caminho_arquivo, engine='odf')
            aluno_dados = df[df['Matrícula'].astype(str) == str(matricula_digitada)]

            if not aluno_dados.empty:
                dados = aluno_dados.iloc[0]
                novo_aluno = Aluno(
                    nome=dados['Nome'],
                    matricula=str(dados['Matrícula']),
                    curso=dados['Curso'],
                    turma=str(dados['Turma']),
                    permissao=True
                )
                db.session.add(novo_aluno)
                db.session.commit()
                flash(f"Aluno {dados['Nome']} importado com sucesso!", "sucesso")
            else:
                flash("Matrícula não encontrada no Excel.", "erro")
        except Exception:
            flash("Erro ao processar a planilha.", "erro")

        return redirect(url_for('painel'))

    @app.route("/importar_todos_alunos", methods=["POST"])
    @admin_obrigatorio
    def importar_todos_alunos():
        if not _validar_csrf():
            return redirect(url_for('gestao_turmas'))

        if not _verificar_senha_admin(request.form.get("senha", "")):
            flash("Senha incorreta. Operação cancelada.", "erro")
            return redirect(url_for('gestao_turmas'))

        try:
            caminho_arquivo = os.environ.get("PLANILHA_ALUNOS", os.path.join(BASE_DIR, "alunos_importacao.ods"))
            df = pd.read_excel(caminho_arquivo, engine='odf')

            status_excluir = ['PERÍODO FECHADO', 'CANCELADA', 'EM ABERTO']
            df = df[~df['Situação Período'].str.strip().str.upper().isin(status_excluir)]

            matriculas_existentes = set(a.matricula for a in Aluno.query.all())

            novos_cadastros = 0
            for index, linha in df.iterrows():
                matricula_str = str(linha['Matrícula'])

                if matricula_str not in matriculas_existentes:
                    novo_aluno = Aluno(
                        nome=linha['Nome'],
                        matricula=matricula_str,
                        curso=linha['Curso'],
                        turma=str(linha['Turma']),
                        permissao=True
                    )
                    db.session.add(novo_aluno)
                    novos_cadastros += 1

            db.session.commit()
            if novos_cadastros > 0:
                flash(f"Sucesso! {novos_cadastros} novos alunos foram importados.", "sucesso")
            else:
                flash("A planilha foi lida, mas todos os alunos já estavam cadastrados", "sucesso")
        except Exception:
            db.session.rollback()
            flash("Erro ao processar a planilha.", "erro")

        return redirect(url_for('gestao_turmas'))

    @app.route("/limpar_tabelas", methods=["POST"])
    @admin_obrigatorio
    def limpar_tabela():
        if not _validar_csrf():
            return redirect(url_for('gestao_turmas'))

        if not _verificar_senha_admin(request.form.get("senha", "")):
            flash("Senha incorreta. Operação cancelada.", "erro")
            return redirect(url_for('gestao_turmas'))
        try:
            db.session.query(Log).delete()
            db.session.query(RegistroAcesso).delete()
            db.session.query(TurmaStatus).delete()
            db.session.query(Aluno).delete()
            db.session.commit()
            flash("Todos os dados de alunos, logs e turmas foram apagados com sucesso!", "sucesso")
        except Exception:
            db.session.rollback()
            flash("Erro ao tentar limpar o sistema.", "erro")
        return redirect(url_for('gestao_turmas'))

    @app.route("/turma/<curso>/<turma>")
    @servidor_obrigatorio
    def redirect_turma_antigo(curso, turma):
        return redirect(url_for('turma_alunos', curso=curso, turma=turma), 301)

    @app.route("/turma_alunos/<curso>/<turma>")
    @servidor_obrigatorio
    def turma_alunos(curso, turma):
        alunos_turma = Aluno.query.filter_by(curso=curso, turma=turma).all()
        refeicao = refeicao_vigente()
        destaque = request.args.get("destaque", "")
        return render_template("turma_alunos.html",
                               alunos=alunos_turma,
                               curso=curso,
                               turma=turma,
                               registrados_ids=_ids_ja_registrados(refeicao),
                               refeicao_atual=refeicao.nome if refeicao and refeicao.ativa else None,
                               destaque=destaque)

    @app.route("/alternar_permissao_aluno/<int:aluno_id>")
    @servidor_obrigatorio
    def alternar_permissao_aluno(aluno_id):
        aluno = Aluno.query.get_or_404(aluno_id)
        aluno.permissao = not aluno.permissao
        db.session.commit()
        return redirect(url_for('turma_alunos', curso=aluno.curso, turma=aluno.turma))

    @app.route("/alternar_permissao_turma/<curso>/<turma>")
    @servidor_obrigatorio
    def alternar_permissao_turma(curso, turma):
        status = TurmaStatus.query.filter_by(curso=curso, turma=turma).first()
        if not status:
            status = TurmaStatus(curso=curso, turma=turma, permissao_ativa=True)
            db.session.add(status)

        status.permissao_ativa = not status.permissao_ativa
        alunos_turma = Aluno.query.filter_by(curso=curso, turma=turma).all()

        for aluno in alunos_turma:
            aluno.permissao = status.permissao_ativa

        db.session.commit()
        return redirect(url_for('gestao_turmas'))

    # ── Refeições (janelas de horário) ────────────────────────────────────────
    def _parse_hora(valor):
        """Converte "HH:MM" (input type=time) em datetime.time, ou None."""
        try:
            return dt.strptime(valor, "%H:%M").time()
        except (ValueError, TypeError):
            return None

    def _validar_refeicao(nome, inicio, fim, ignorar_id=None):
        """Devolve uma mensagem de erro, ou None se estiver tudo certo."""
        if not nome:
            return "Informe o nome da refeição."
        if inicio is None or fim is None:
            return "Informe horários válidos de início e fim."
        if inicio >= fim:
            return "O horário de início deve ser antes do fim."

        # Janelas sobrepostas tornariam ambíguo em qual refeição uma passagem
        # cai, então não permitimos.
        outras = Refeicao.query.filter(Refeicao.id != ignorar_id) if ignorar_id else Refeicao.query
        for outra in outras.all():
            if inicio < outra.hora_fim and outra.hora_inicio < fim:
                return f"O horário conflita com {outra.nome} ({outra.hora_inicio.strftime('%H:%M')}–{outra.hora_fim.strftime('%H:%M')})."
        return None

    @app.route("/refeicoes")
    @admin_obrigatorio
    def gestao_refeicoes():
        refeicoes = Refeicao.query.order_by(Refeicao.hora_inicio).all()
        atual = refeicao_vigente()
        return render_template("gestao_refeicoes.html",
                               refeicoes=refeicoes,
                               refeicao_atual_id=atual.id if atual else None)

    @app.route("/refeicoes/criar", methods=["POST"])
    @admin_obrigatorio
    def criar_refeicao():
        if not _validar_csrf():
            return redirect(url_for('gestao_refeicoes'))

        nome = request.form.get('nome', '').strip()
        inicio = _parse_hora(request.form.get('hora_inicio', ''))
        fim = _parse_hora(request.form.get('hora_fim', ''))

        erro = _validar_refeicao(nome, inicio, fim)
        if erro:
            flash(erro, "erro")
            return redirect(url_for('gestao_refeicoes'))

        db.session.add(Refeicao(nome=nome, hora_inicio=inicio, hora_fim=fim, ativa=True))
        db.session.commit()
        flash(f"Refeição {nome} cadastrada!", "sucesso")
        return redirect(url_for('gestao_refeicoes'))

    @app.route("/refeicoes/editar/<int:refeicao_id>", methods=["POST"])
    @admin_obrigatorio
    def editar_refeicao(refeicao_id):
        if not _validar_csrf():
            return redirect(url_for('gestao_refeicoes'))

        refeicao = Refeicao.query.get_or_404(refeicao_id)
        nome = request.form.get('nome', '').strip()
        inicio = _parse_hora(request.form.get('hora_inicio', ''))
        fim = _parse_hora(request.form.get('hora_fim', ''))

        erro = _validar_refeicao(nome, inicio, fim, ignorar_id=refeicao.id)
        if erro:
            flash(erro, "erro")
            return redirect(url_for('gestao_refeicoes'))

        refeicao.nome = nome
        refeicao.hora_inicio = inicio
        refeicao.hora_fim = fim
        db.session.commit()
        flash(f"Refeição {nome} atualizada!", "sucesso")
        return redirect(url_for('gestao_refeicoes'))

    @app.route("/refeicoes/alternar/<int:refeicao_id>", methods=["POST"])
    @admin_obrigatorio
    def alternar_refeicao(refeicao_id):
        if not _validar_csrf():
            return redirect(url_for('gestao_refeicoes'))

        refeicao = Refeicao.query.get_or_404(refeicao_id)
        refeicao.ativa = not refeicao.ativa
        db.session.commit()
        flash(f"{refeicao.nome} {'liberado' if refeicao.ativa else 'bloqueado'}.", "sucesso")
        return redirect(url_for('gestao_refeicoes'))

    @app.route("/refeicoes/excluir/<int:refeicao_id>", methods=["POST"])
    @admin_obrigatorio
    def excluir_refeicao(refeicao_id):
        if not _validar_csrf():
            return redirect(url_for('gestao_refeicoes'))

        refeicao = Refeicao.query.get_or_404(refeicao_id)
        # Os registros históricos apontam para a refeição; se apagássemos a
        # linha, o relatório perderia o rótulo. Só permitimos excluir refeições
        # que nunca registraram passagem — para as demais, o admin bloqueia.
        if Log.query.filter_by(refeicao_id=refeicao.id).first():
            flash(f"{refeicao.nome} já possui registros e não pode ser excluída. Bloqueie-a.", "erro")
            return redirect(url_for('gestao_refeicoes'))

        nome = refeicao.nome
        db.session.delete(refeicao)
        db.session.commit()
        flash(f"Refeição {nome} excluída.", "sucesso")
        return redirect(url_for('gestao_refeicoes'))

    @app.route("/toggle-theme")
    def toggle_theme():
        tema_atual = session.get("tema", "dark")
        session["tema"] = "dark" if tema_atual == "light" else "light"
        return "", 204

    @app.route("/registrar_entrada/<int:aluno_id>")
    @servidor_obrigatorio
    def registrar_entrada(aluno_id):
        # Passa pelo servico_acesso de propósito: o registro manual segue
        # exatamente as mesmas regras da catraca (horário da refeição, refeição
        # bloqueada, uma passagem por refeição por dia).
        aluno = Aluno.query.get_or_404(aluno_id)
        resultado = processar_matricula(app, aluno.matricula)
        flash(resultado["mensagem"], "sucesso" if resultado["status"] in _STATUS_SUCESSO else "erro")
        return redirect(url_for('turma_alunos', curso=aluno.curso, turma=aluno.turma))

    @app.route("/api/registrados_ids")
    @servidor_obrigatorio
    def api_registrados_ids():
        return jsonify(registrados_ids=list(_ids_ja_registrados(refeicao_vigente())))

    @app.route("/api/fluxo_dados")
    @servidor_obrigatorio
    def api_fluxo_dados():
        hoje = dt.now().date()
        hoje_inicio = dt(hoje.year, hoje.month, hoje.day, 0, 0, 0)
        logs_data = db.session.query(Log, Aluno).join(Aluno).filter(
            Log.data_entrada >= hoje_inicio
        ).order_by(Log.data_entrada.desc()).all()

        lista_logs = []
        for log, aluno in logs_data:
            lista_logs.append({
                'id': log.id,
                'nome': aluno.nome,
                'matricula': aluno.matricula,
                'curso': aluno.curso,
                'turma': aluno.turma,
                'entrada': log.data_entrada.strftime('%H:%M:%S'),
                'entrada_raw': log.data_entrada.isoformat(),
                'refeicao': log.refeicao.nome if log.refeicao else '—',
            })

        cursos = sorted({l['curso'] for l in lista_logs if l['curso']})
        alunos_unicos = len({log.aluno_id for log, _ in logs_data})
        refeicao = refeicao_vigente()

        return jsonify(
            total_hoje=len(lista_logs),
            alunos_unicos=alunos_unicos,
            logs=lista_logs,
            cursos=cursos,
            refeicao_atual=refeicao.nome if refeicao and refeicao.ativa else None,
        )

    @app.route("/api/pesquisar_alunos")
    @servidor_obrigatorio
    def api_pesquisar_alunos():
        query = request.args.get('query', '').strip()
        if not query:
            return jsonify(alunos=[])

        alunos = Aluno.query.filter(
            (Aluno.nome.ilike(f'%{query}%')) | (Aluno.matricula.ilike(f'%{query}%'))
        ).order_by(Aluno.nome).all()

        alunos_data = [{
            'id': aluno.id,
            'nome': aluno.nome,
            'matricula': aluno.matricula,
            'curso': aluno.curso,
            'turma': aluno.turma
        } for aluno in alunos]

        return jsonify(alunos=alunos_data)

    @app.route("/relatorio_refeicoes", methods=["GET", "POST"])
    @servidor_obrigatorio
    def relatorio_refeicoes():
        hoje = dt.now().date()
        data_inicio = request.args.get('data_inicio', (hoje - timedelta(days=6)).isoformat())
        data_fim = request.args.get('data_fim', hoje.isoformat())

        try:
            di = dt.strptime(data_inicio, '%Y-%m-%d').date()
            df = dt.strptime(data_fim, '%Y-%m-%d').date()
        except:
            di, df = (hoje - timedelta(days=6)), hoje

        if di > df:
            di, df = df, di

        return render_template('relatorio_refeicoes.html',
                               hoje=hoje,
                               data_inicio=di.isoformat(),
                               data_fim=df.isoformat(),
                               data_7d_atras=(hoje - timedelta(days=6)).isoformat(),
                               data_30d_atras=(hoje - timedelta(days=29)).isoformat(),
                               data_mes_inicio=hoje.replace(day=1).isoformat())

    @app.route("/exportar_relatorio")
    @servidor_obrigatorio
    def exportar_relatorio():
        from weasyprint import HTML
        from io import BytesIO

        hoje = dt.now().date()
        data_inicio = request.args.get('data_inicio', (hoje - timedelta(days=29)).isoformat())
        data_fim = request.args.get('data_fim', hoje.isoformat())

        try:
            di = dt.strptime(data_inicio, '%Y-%m-%d').date()
            df = dt.strptime(data_fim, '%Y-%m-%d').date()
        except:
            di = hoje - timedelta(days=29)
            df = hoje

        if di > df:
            di, df = df, di

        periodo_label = f"{di.strftime('%d/%m/%Y')} a {df.strftime('%d/%m/%Y')}"

        logs = db.session.query(Log, Aluno).join(Aluno).filter(
            func.date(Log.data_entrada) >= di,
            func.date(Log.data_entrada) <= df
        ).order_by(Log.data_entrada).all()

        dias_traducao = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
        dias_abrev = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']

        # ── Resumo ──
        alunos_unicos = {aluno.id for _, aluno in logs}

        dados_agrupados = {}
        for log, aluno in logs:
            data_key = log.data_entrada.date()
            dados_agrupados[data_key] = dados_agrupados.get(data_key, 0) + 1

        dados_ordenados = sorted(dados_agrupados.items())
        total_entradas = len(logs)
        qtd_unicos = len(alunos_unicos)
        media_diaria = round(total_entradas / len(dados_agrupados), 1) if dados_agrupados else 0
        dia_mais = max(dados_ordenados, key=lambda x: x[1]) if dados_ordenados else ("", 0)
        dia_menos = min(dados_ordenados, key=lambda x: x[1]) if dados_ordenados else ("", 0)

        dia_mais_label = f"{dia_mais[0].strftime('%d/%m/%Y')} ({dia_mais[1]})" if dia_mais[0] else "-"
        dia_menos_label = f"{dia_menos[0].strftime('%d/%m/%Y')} ({dia_menos[1]})" if dia_menos[0] else "-"

        # ── Frequência Diária ──
        dados_diarios_dict = {}
        for log, aluno in logs:
            data_key = log.data_entrada.date()
            if data_key not in dados_diarios_dict:
                dados_diarios_dict[data_key] = {"entradas": 0, "alunos": set()}
            dados_diarios_dict[data_key]["entradas"] += 1
            dados_diarios_dict[data_key]["alunos"].add(aluno.id)

        dados_diarios = [
            {
                "dia_semana": dias_traducao[data_key.weekday()],
                "data": data_key.strftime('%d/%m/%Y'),
                "entradas": info["entradas"],
                "alunos_unicos": len(info["alunos"]),
            }
            for data_key, info in sorted(dados_diarios_dict.items())
        ]

        # ── Média por Dia da Semana ──
        acessos_dia_semana = defaultdict(list)
        for log, aluno in logs:
            dia = log.data_entrada.date()
            acessos_dia_semana[dia.weekday()].append(dia)

        total_geral = sum(len(v) for v in acessos_dia_semana.values())
        dados_dia_semana = [
            {
                "dia": dias_abrev[dia],
                "media": round(len(dias) / len(set(dias)), 1),
                "pct": round(len(dias) / total_geral * 100, 1) if total_geral else 0,
            }
            for dia, dias in sorted(acessos_dia_semana.items())
        ]

        # ── Por Hora ──
        hora_counts = {}
        for log, aluno in logs:
            hora = log.data_entrada.strftime("%H:00")
            hora_counts[hora] = hora_counts.get(hora, 0) + 1

        dados_horas = [
            {"hora": h, "total": total_h, "pct": round(total_h / total_entradas * 100, 1) if total_entradas else 0}
            for h, total_h in sorted(hora_counts.items())
        ]

        # ── Por Refeição ──
        refeicao_counts = defaultdict(int)
        for log, aluno in logs:
            refeicao_counts[log.refeicao.nome if log.refeicao else "Sem refeição"] += 1

        dados_refeicoes = [
            {"refeicao": nome, "total": total_r,
             "pct": round(total_r / total_entradas * 100, 1) if total_entradas else 0}
            for nome, total_r in sorted(refeicao_counts.items(), key=lambda x: -x[1])
        ]

        # ── Alunos ──
        aluno_info = {}
        for log, aluno in logs:
            if aluno.id not in aluno_info:
                aluno_info[aluno.id] = {"nome": aluno.nome, "matricula": aluno.matricula,
                                        "curso": aluno.curso or "", "turma": aluno.turma or "",
                                        "acessos": 0}
            aluno_info[aluno.id]["acessos"] += 1

        dados_alunos = [
            {"nome": info["nome"], "matricula": info["matricula"], "curso": info["curso"],
             "turma": info["turma"], "acessos": info["acessos"]}
            for info in sorted(aluno_info.values(), key=lambda x: -x["acessos"])
        ]

        html_str = render_template('relatorio_pdf.html',
            periodo_label=periodo_label,
            total_entradas=total_entradas,
            qtd_unicos=qtd_unicos,
            media_diaria=media_diaria,
            dia_mais_label=dia_mais_label,
            dia_menos_label=dia_menos_label,
            dados_diarios=dados_diarios,
            dados_dia_semana=dados_dia_semana,
            dados_horas=dados_horas,
            dados_refeicoes=dados_refeicoes,
            dados_alunos=dados_alunos,
            gerado_em=hoje.strftime('%d/%m/%Y %H:%M'),
        )

        pdf_bytes = HTML(string=html_str).write_pdf()

        nome_arquivo = f"relatorio_refeitorio_{di.strftime('%Y%m%d')}_{df.strftime('%Y%m%d')}.pdf"
        return send_file(BytesIO(pdf_bytes), mimetype='application/pdf',
                         as_attachment=True, download_name=nome_arquivo)

    @app.route("/dashboard")
    @servidor_obrigatorio
    def dashboard():
        return render_template("dashboard_executivo.html")

    @app.route("/api/dashboard_dados")
    @servidor_obrigatorio
    def api_dashboard_dados():
        hoje = dt.now().date()
        agora = dt.now()

        total_alunos = Aluno.query.count()

        logs_hoje = db.session.query(Log).filter(
            func.date(Log.data_entrada) == hoje
        ).order_by(Log.data_entrada).all()

        registros_hoje = len(logs_hoje)

        fluxo_por_hora = defaultdict(int)
        for log in logs_hoje:
            fluxo_por_hora[log.data_entrada.strftime("%H:00")] += 1

        fluxo_horas = [
            {"hora": h, "entradas": entradas}
            for h, entradas in sorted(fluxo_por_hora.items())
        ]

        sete_dias_atras = hoje - timedelta(days=7)
        logs_7dias = db.session.query(Log).filter(
            func.date(Log.data_entrada) >= sete_dias_atras
        ).count()
        media_diaria = round(logs_7dias / 7, 1) if logs_7dias > 0 else 0

        dia_semana_abrev = {0: "Seg", 1: "Ter", 2: "Qua", 3: "Qui", 4: "Sex", 5: "Sáb", 6: "Dom"}
        comparativo = []
        for i in range(6, -1, -1):
            dia = hoje - timedelta(days=i)
            dia_anterior = dia - timedelta(days=7)
            count_esta = db.session.query(Log).filter(
                func.date(Log.data_entrada) == dia
            ).count()
            count_anterior = db.session.query(Log).filter(
                func.date(Log.data_entrada) == dia_anterior
            ).count()
            comparativo.append({
                "dia": dia_semana_abrev[dia.weekday()],
                "esta_semana": count_esta,
                "semana_anterior": count_anterior,
            })

        # Sem saída não dá pra falar em "alunos simultâneos": o pico agora é a
        # hora que mais registrou passagens.
        pico_max = 0
        pico_horario = "--:--"
        if fluxo_por_hora:
            pico_horario, pico_max = max(fluxo_por_hora.items(), key=lambda x: x[1])

        insights = []
        hoje_count = len(logs_hoje)
        if hoje_count > 0:
            if hoje_count > media_diaria * 1.2:
                insights.append({
                    "label": "Movimento acima da media",
                    "valor": f"Hoje ({hoje_count}) esta {round((hoje_count/media_diaria - 1)*100)}% acima da media semanal ({media_diaria})"
                })
            elif hoje_count < media_diaria * 0.8:
                insights.append({
                    "label": "Movimento abaixo da media",
                    "valor": f"Hoje ({hoje_count}) esta {round((1 - hoje_count/media_diaria)*100)}% abaixo da media semanal ({media_diaria})"
                })
            else:
                insights.append({
                    "label": "Movimento normal",
                    "valor": f"Hoje: {hoje_count} alunos | Media semanal: {media_diaria}"
                })
        else:
            insights.append({
                "label": "Nenhum movimento hoje",
                "valor": "Ainda nao ha registros de acesso hoje"
            })

        if pico_max > 0:
            insights.append({
                "label": "Horario de pico hoje",
                "valor": f"{pico_max} passagens entre {pico_horario} e {int(pico_horario[:2]) + 1:02d}:00"
            })

        semana_passada = db.session.query(Log).filter(
            func.date(Log.data_entrada) >= sete_dias_atras,
            func.date(Log.data_entrada) < hoje
        ).count()
        semana_retrasada = db.session.query(Log).filter(
            func.date(Log.data_entrada) >= sete_dias_atras - timedelta(days=7),
            func.date(Log.data_entrada) < hoje - timedelta(days=7)
        ).count()

        trend_total = None
        trend_media = None
        if semana_retrasada > 0:
            pct = round((semana_passada - semana_retrasada) / semana_retrasada * 100)
            trend_total = {"direction": "up" if pct >= 0 else "down", "percentual": abs(pct)}
            trend_media = {"direction": "up" if pct >= 0 else "down", "percentual": abs(pct)}

        media_dia_semana = 0
        dia_semana_hoje = hoje.weekday()
        ocorrencias = 0
        for i in range(30):
            dia = hoje - timedelta(days=i)
            if dia.weekday() == dia_semana_hoje:
                count = db.session.query(Log).filter(
                    func.date(Log.data_entrada) == dia
                ).count()
                media_dia_semana += count
                ocorrencias += 1
        if ocorrencias > 0:
            media_dia_semana = round(media_dia_semana / ocorrencias, 1)

        if media_dia_semana > 0:
            dias_map = {0: "segunda", 1: "terca", 2: "quarta", 3: "quinta", 4: "sexta", 5: "sabado", 6: "domingo"}
            insights.insert(0, {
                "label": "Previsão para hoje",
                "valor": f"~{media_dia_semana} alunos (media de {dias_map[hoje.weekday()]} dos ultimos 30 dias)"
            })

        return jsonify(
            total_alunos=total_alunos,
            registros_hoje=registros_hoje,
            media_diaria=media_diaria,
            fluxo_por_hora=fluxo_horas,
            comparativo_semanal=comparativo,
            pico_hoje={"maximo": pico_max, "horario": pico_horario},
            insights=insights,
            trend_total=trend_total,
            trend_media=trend_media,
        )

    @app.route("/api/analytics_dados")
    @servidor_obrigatorio
    def api_analytics_dados():
        hoje = dt.now().date()
        sete_dias_atras = hoje - timedelta(days=7)

        # Distribuição por refeição nos últimos 7 dias — substitui o antigo
        # "tempo médio de permanência", que dependia da saída.
        logs_7d = db.session.query(Log).filter(
            func.date(Log.data_entrada) >= sete_dias_atras
        ).all()

        contagem_refeicoes = defaultdict(int)
        for log in logs_7d:
            contagem_refeicoes[log.refeicao.nome if log.refeicao else "Sem refeição"] += 1

        refeicoes_7d = [
            {"refeicao": nome, "total": total}
            for nome, total in sorted(contagem_refeicoes.items(), key=lambda x: -x[1])
        ]

        liberados = Aluno.query.filter_by(permissao=True).count()
        bloqueados = Aluno.query.filter_by(permissao=False).count()

        dia_semana_map = {0: "Seg", 1: "Ter", 2: "Qua", 3: "Qui", 4: "Sex", 5: "Sab", 6: "Dom"}
        acessos_por_dia_semana = defaultdict(int)
        for i in range(30):
            dia = hoje - timedelta(days=i)
            count = db.session.query(Log).filter(
                func.date(Log.data_entrada) == dia
            ).count()
            acessos_por_dia_semana[dia.weekday()] += count

        dia_semana_acessos = [
            {"dia": dia_semana_map[dia], "total": total}
            for dia, total in sorted(acessos_por_dia_semana.items())
        ]

        acessos_hoje = db.session.query(Log).filter(
            func.date(Log.data_entrada) == hoje
        ).count()

        return jsonify(
            refeicoes_7d=refeicoes_7d,
            liberados=liberados,
            bloqueados=bloqueados,
            acessos_hoje=acessos_hoje,
            dia_semana_acessos=dia_semana_acessos,
        )
