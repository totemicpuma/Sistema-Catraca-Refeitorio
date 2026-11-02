import os
import unittest
from datetime import datetime as dt, time, timedelta
from unittest.mock import patch

# Precisa ser setado ANTES do "from app import app": a engine do SQLAlchemy é
# criada uma única vez, na importação de app.py (db.init_app roda no import,
# não dá pra apontar pra outro banco depois). Sem isso, o app.py importa e liga
# o engine direto no refeitorio.db real, e o drop_all do tearDown apagaria o
# banco de verdade do dashboard.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app import app, db
from models import Aluno, Log, Refeicao
from servico_acesso import processar_matricula

# Um instante dentro da janela do almoço, usado para congelar o "agora".
DURANTE_O_ALMOCO = dt.now().replace(hour=12, minute=0, second=0, microsecond=0)
FORA_DE_QUALQUER_REFEICAO = dt.now().replace(hour=15, minute=30, second=0, microsecond=0)


class BaseRefeitorioTest(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config.update(TESTING=True)
        with self.app.app_context():
            db.drop_all()
            db.create_all()
            db.session.add(Aluno(nome="Ana Silva", matricula="12345",
                                 curso="Informática", turma="3", permissao=True))
            db.session.add(Refeicao(nome="Almoço", hora_inicio=time(11, 0),
                                    hora_fim=time(14, 0), ativa=True))
            db.session.commit()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def _almoco(self):
        return Refeicao.query.filter_by(nome="Almoço").first()


class PassagemUnicaTest(BaseRefeitorioTest):
    """A regra central: registra a passagem e não deixa passar de novo."""

    @patch("servico_acesso.dt")
    def test_primeira_passagem_e_registrada(self, mock_dt):
        mock_dt.now.return_value = DURANTE_O_ALMOCO
        mock_dt.side_effect = lambda *a, **kw: dt(*a, **kw)

        resultado = processar_matricula(self.app, "12345")

        self.assertEqual(resultado["status"], "entrada")
        with self.app.app_context():
            self.assertEqual(Log.query.count(), 1)

    @patch("servico_acesso.dt")
    def test_segunda_passagem_na_mesma_refeicao_e_recusada(self, mock_dt):
        mock_dt.now.return_value = DURANTE_O_ALMOCO
        mock_dt.side_effect = lambda *a, **kw: dt(*a, **kw)

        processar_matricula(self.app, "12345")
        resultado = processar_matricula(self.app, "12345")

        self.assertEqual(resultado["status"], "duplicado")
        self.assertIn("já registrou", resultado["mensagem"])
        with self.app.app_context():
            # A recusa não pode gerar um segundo registro.
            self.assertEqual(Log.query.count(), 1)

    @patch("servico_acesso.dt")
    def test_passagem_liberada_em_outra_refeicao_no_mesmo_dia(self, mock_dt):
        mock_dt.now.return_value = DURANTE_O_ALMOCO
        mock_dt.side_effect = lambda *a, **kw: dt(*a, **kw)
        processar_matricula(self.app, "12345")

        with self.app.app_context():
            db.session.add(Refeicao(nome="Jantar", hora_inicio=time(17, 0),
                                    hora_fim=time(20, 0), ativa=True))
            db.session.commit()

        mock_dt.now.return_value = DURANTE_O_ALMOCO.replace(hour=18)
        resultado = processar_matricula(self.app, "12345")

        self.assertEqual(resultado["status"], "entrada")
        with self.app.app_context():
            self.assertEqual(Log.query.count(), 2)

    @patch("servico_acesso.dt")
    def test_passagem_liberada_na_mesma_refeicao_no_dia_seguinte(self, mock_dt):
        # A passagem de ontem é inserida direto no banco: o default de
        # Log.data_entrada usa o relógio real, então passar por
        # processar_matricula gravaria com a data de hoje.
        with self.app.app_context():
            aluno = Aluno.query.filter_by(matricula="12345").first()
            db.session.add(Log(aluno_id=aluno.id, refeicao_id=self._almoco().id,
                               data_entrada=DURANTE_O_ALMOCO - timedelta(days=1)))
            db.session.commit()

        mock_dt.now.return_value = DURANTE_O_ALMOCO
        mock_dt.side_effect = lambda *a, **kw: dt(*a, **kw)
        resultado = processar_matricula(self.app, "12345")

        self.assertEqual(resultado["status"], "entrada")
        with self.app.app_context():
            self.assertEqual(Log.query.count(), 2)


class JanelaDeRefeicaoTest(BaseRefeitorioTest):
    @patch("servico_acesso.dt")
    def test_fora_do_horario_nao_registra(self, mock_dt):
        mock_dt.now.return_value = FORA_DE_QUALQUER_REFEICAO
        mock_dt.side_effect = lambda *a, **kw: dt(*a, **kw)

        resultado = processar_matricula(self.app, "12345")

        self.assertEqual(resultado["status"], "fora_horario")
        with self.app.app_context():
            self.assertEqual(Log.query.count(), 0)

    @patch("servico_acesso.dt")
    def test_refeicao_bloqueada_pelo_admin_nao_registra(self, mock_dt):
        mock_dt.now.return_value = DURANTE_O_ALMOCO
        mock_dt.side_effect = lambda *a, **kw: dt(*a, **kw)

        with self.app.app_context():
            self._almoco().ativa = False
            db.session.commit()

        resultado = processar_matricula(self.app, "12345")

        self.assertEqual(resultado["status"], "refeicao_bloqueada")
        with self.app.app_context():
            self.assertEqual(Log.query.count(), 0)

    @patch("servico_acesso.dt")
    def test_aluno_sem_permissao_nao_registra(self, mock_dt):
        mock_dt.now.return_value = DURANTE_O_ALMOCO
        mock_dt.side_effect = lambda *a, **kw: dt(*a, **kw)

        with self.app.app_context():
            Aluno.query.filter_by(matricula="12345").first().permissao = False
            db.session.commit()

        resultado = processar_matricula(self.app, "12345")

        self.assertEqual(resultado["status"], "bloqueado")
        with self.app.app_context():
            self.assertEqual(Log.query.count(), 0)


class PublicoStatusTest(BaseRefeitorioTest):
    def test_api_publico_status_reflects_total_and_logs(self):
        with self.app.app_context():
            aluno = Aluno.query.filter_by(matricula="12345").first()
            db.session.add(Log(aluno_id=aluno.id, refeicao_id=self._almoco().id))
            db.session.commit()

        with self.app.test_client() as client:
            response = client.get('/api/publico_status')

        self.assertEqual(response.status_code, 200)
        dados = response.get_json()
        self.assertEqual(dados['total_hoje'], 1)
        self.assertEqual(dados['logs'][0]['nome'], 'Ana Silva')
        self.assertEqual(dados['logs'][0]['refeicao'], 'Almoço')


if __name__ == '__main__':
    unittest.main()
