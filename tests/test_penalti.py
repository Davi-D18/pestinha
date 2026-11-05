"""
PENALTI: arremessa a bolinha nele — goleiro desconfiado, defesa em cartaz, gol
em fogos. Offscreen com app real, como os outros momentos.
"""
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pestinha import config  # noqa: E402
from pestinha.app import PestinhaApp  # noqa: E402
from pestinha.mind.penalti import PenaltiController  # noqa: E402
from pestinha.paths import Paths  # noqa: E402
from pestinha.settings_store import SettingsStore  # noqa: E402


@pytest.fixture
def pet_app(tmp_path):
    app_qt = QApplication.instance() or QApplication([])
    app_qt.setQuitOnLastWindowClosed(False)
    paths = Paths(root=tmp_path)
    store = SettingsStore(paths)
    store.update(dict(config.DEFAULT_PERMISSIONS))
    app = PestinhaApp(store, paths)
    yield app
    for timer in app.findChildren(QTimer):
        timer.stop()
    for w in list(app.floats.windows.values()):
        w.close()


class CorpoFalso:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.vx = 0.0
        self.pulos = []

    def jump(self, vx, vy, giro=0.0):
        self.pulos.append((vx, vy))


class BolaFalsa:
    def __init__(self, x=100.0, y=700.0, vx=0.0, vy=0.0, dragging=False, release=-1e9):
        from types import SimpleNamespace
        self.body = SimpleNamespace(x=x, y=y, vx=vx, vy=vy)
        self.dragging = dragging
        self.last_release = release


def _controller(tmp_path, historico=(0, 0)):
    caminho = tmp_path / "penalti.json"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(f'{{"esquerda": {historico[0]}, "direita": {historico[1]}}}', encoding="utf-8")
    controle = PenaltiController(caminho)
    controle.ativo = True
    return controle


def _jogada(tmp_path, historico=(0, 0), x_goleiro=400.0, chao=760.0):
    corpo = CorpoFalso(x_goleiro, chao - 90.0)
    return corpo, chao, _controller(tmp_path, historico=historico)


# ---------------------------------------------------------------- desconfiança

def test_desconfia_do_lado_de_sempre(tmp_path):
    random.seed(3)
    corpo, chao, controle = _jogada(tmp_path, historico=(4, 1))   # você sempre mira à esquerda
    for _ in range(6):
        assert controle.lado_da_desconfianca(-1) == -1            # o pulinho vai para o seu lado de sempre


def test_sem_maioria_e_sorte(tmp_path):
    random.seed(3)
    corpo, chao, controle = _jogada(tmp_path, historico=(1, 1))
    resultados = {controle.lado_da_desconfianca(-1) for _ in range(40)}
    assert resultados == {-1, 1}                                  # sem histórico firme, dá nos dois lados


def test_historico_persiste_e_recusa_lixo(tmp_path):
    corpo, chao, controle = _jogada(tmp_path)
    controle.registrar_arremesso(0.0, -600.0, 300.0)
    de_novo = PenaltiController(controle.path)
    assert de_novo.miras["esquerda"] == 1 and de_novo.miras["direita"] == 0
    controle.path.write_text('{"esquerda": "muito", "direita": null}', encoding="utf-8")
    assert PenaltiController(controle.path).miras == {"esquerda": 0, "direita": 0}


# ---------------------------------------------------------------- jogada

def test_arremesso_fraco_nao_arma_jogada(tmp_path):
    corpo, chao, controle = _jogada(tmp_path)
    bola = BolaFalsa(x=200.0, vx=200.0, release=0.0)
    assert controle.tick(0.0, bola, corpo, chao, 140.0, 200.0, 64.0, 5.0) is None
    assert controle.arremesso is None                       # chutão fraco nem conta mira


def test_mergulho_vem_pela_desconfianca(tmp_path):
    corpo, chao, controle = _jogada(tmp_path, historico=(5, 0))
    bola = BolaFalsa(x=600.0, vx=-800.0, release=100.0)     # bola do lado direito dele, chutada para a esquerda
    controle.tick(0.1, bola, corpo, chao, 140.0, 200.0, 64.0, 5.0)     # o release novo arma a jogada
    acao = controle.tick(0.6, bola, corpo, chao, 140.0, 200.0, 64.0, 5.0)
    assert acao == ("dive", -1)                             # desconfiou: pula para a sua esquerda
    bola.body.x = corpo.x - 10.0                            # a bolinha chega a tempo do corpo
    bola.body.y = corpo.y
    assert controle.tick(1.0, bola, corpo, chao, 140.0, 200.0, 64.0, 5.0) == ("defesa",)


def test_bola_nele_e_defesa(tmp_path):
    corpo, chao, controle = _jogada(tmp_path, historico=(4, 1))
    bola = BolaFalsa(x=corpo.x + 600.0, vx=-900.0, release=10.0)
    controle.tick(0.0, bola, corpo, chao, 140.0, 200.0, 64.0, 5.0)
    controle.tick(0.5, bola, corpo, chao, 140.0, 200.0, 64.0, 5.0)     # o mergulho sai antes
    bola.body.x, bola.body.y = corpo.x - 10.0, corpo.y
    assert controle.tick(1.0, bola, corpo, chao, 140.0, 200.0, 64.0, 5.0) == ("defesa",)


def test_bola_passando_e_gol(tmp_path):
    corpo, chao, controle = _jogada(tmp_path, historico=(4, 1))
    bola = BolaFalsa(x=corpo.x - 600.0, vx=900.0, release=10.0)
    controle.tick(0.0, bola, corpo, chao, 140.0, 200.0, 64.0, 5.0)
    controle.tick(0.5, bola, corpo, chao, 140.0, 200.0, 64.0, 5.0)     # mergulhou do lado errado
    bola.body.x, bola.body.y = corpo.x + 200.0, chao - 20.0
    assert controle.tick(1.0, bola, corpo, chao, 140.0, 200.0, 64.0, 5.0) == ("gol",)
    assert controle.arremesso is None                       # jogada acabou


def test_modo_desligado_nao_joga(tmp_path):
    corpo, chao, controle = _jogada(tmp_path)
    controle.ativo = False
    bola = BolaFalsa(x=200.0, vx=-900.0, release=5.0)
    assert controle.tick(0.0, bola, corpo, chao, 140.0, 200.0, 64.0, 5.0) is None


# ---------------------------------------------------------------- no app

def test_menu_penalti_liga_mira_e_goleiro(pet_app):
    pet_app.pet.body.grounded = True
    pet_app.menu_penalti()
    assert pet_app.penalti.ativo and pet_app.penalti.miras == {"esquerda": 0, "direita": 0}
    assert pet_app.pet_state.penalti is True                # parado de goleiro
    assert pet_app.ball.aim_hint is True                    # linha de mira no arraste
    pet_app.menu_penalti()
    assert not pet_app.penalti.ativo and not pet_app.pet_state.penalti
    assert pet_app.ball.aim_hint is False


def test_gol_solta_fogos_e_defesa_solta_cartaz(pet_app, monkeypatch):
    pet_app.pet.body.grounded = True
    pet_app.menu_penalti()
    pet_app.ball.last_release = 123.0
    pet_app.ball.body.vx = 900.0
    pet_app.ball.dragging = False
    fogos = []
    monkeypatch.setattr(pet_app.festa.fogos, "launch", lambda x, y: fogos.append((x, y)))
    corpo, bola = pet_app.pet.body, pet_app.ball
    bola.body.x, bola.body.y = corpo.x - 600.0, pet_app.bounds()[3] - 20.0
    t0 = time.monotonic()
    pet_app._penalti_frame(t0, corpo, bola)                 # soltou: registra e arma
    pet_app._penalti_frame(t0 + 0.5, corpo, bola)           # o mergulho do goleiro
    bola.body.x = corpo.x + 250.0                           # passou da trave
    pet_app._penalti_frame(t0 + 1.0, corpo, bola)
    assert fogos                                            # gol: fogos de artifício
    pet_app.penalti.arremesso = {"lado_visto": -1, "mergulhou": True, "mergulho_em": 0.0,
                                 "resolvido": False, "t0": time.monotonic()}
    pet_app.ball.body.x, pet_app.ball.body.y = corpo.x - 8.0, corpo.y
    cartazes_antes = len(pet_app.mischief.things)
    pet_app._penalti_frame(time.monotonic(), corpo, pet_app.ball)
    assert len(pet_app.mischief.things) == cartazes_antes + 1   # defesa: cartaz na tela
