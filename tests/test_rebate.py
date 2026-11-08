"""
REBATE (v2): ele corre atrás da bolinha, pega (carrega), leva ao canto e chuta de
volta (com pulinho de chute); você devolve com estilingue (arrastar e soltar); o
ponteiro não empurra a bolinha dentro do rali. Placas ocasionais. Offscreen.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import random
import pytest  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pestinha import config  # noqa: E402
from pestinha.app import PestinhaApp  # noqa: E402
from pestinha.mind.rebate import CANTO_MARGEM, RebateController  # noqa: E402
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
    def __init__(self, x=100.0, grounded=True):
        self.x, self.y = x, 682.0
        self.half_w, self.half_h = 60.0, 45.0
        self.vx = 0.0
        self.grounded = grounded
        self.pulos = []

    def extents(self):
        return self.half_w, self.half_h

    def jump(self, vx, vy, giro=0.0):
        self.pulos.append((vx, vy))


class BolaFalsa:
    def __init__(self, x=180.0, y=682.0, vx=0.0, vy=0.0):
        from types import SimpleNamespace
        self.body = SimpleNamespace(x=x, y=y, vx=vx, vy=vy, grounded=True)
        self.dragging = False
        self.carried = False
        self.last_release = -1e9
        self.tocos = []

    def kick(self, vx, vy):
        self.tocos.append((vx, vy))
        self.body.vx, self.body.vy = vx, vy
        self.carried = False


ESQ, DIR = 0.0, 1920.0


def _controlador(tmp_path):
    cont = RebateController(lambda: True, tmp_path / "nada")
    cont.ativo = True
    return cont


# ---------------------------------------------------------------- o controlador

def test_persegue_quando_voce_joga_o_estilingue(tmp_path):
    cont = _controlador(tmp_path)
    bola = BolaFalsa(x=900.0, vx=900.0)
    bola.last_release = 10.0                                   # você soltou o estilingue
    alvo, ev = cont.tick(0.0, CorpoFalso(x=100.0), bola, 682.0, ESQ, DIR, livre=True)
    assert alvo == 900.0 and ev == []                          # correu atrás da devolução


def test_pescado_e_leva_para_o_canto_longe(tmp_path):
    cont = _controlador(tmp_path)
    bola = BolaFalsa(x=300.0)
    alvo, _ev = cont.tick(0.0, CorpoFalso(x=280.0), bola, 682.0, ESQ, DIR, livre=True)
    assert bola.carried and alvo == DIR - CANTO_MARGEM         # pegou e leva para o canto longe


def test_leva_no_pe_e_chuta_do_canto(tmp_path, monkeypatch):
    monkeypatch.setattr("pestinha.mind.rebate.REBATE_PLACA_CHANCE", 0.0)
    cont = _controlador(tmp_path)
    cont.fase, cont.lado, cont.canto_x = "levar", 1, DIR - CANTO_MARGEM
    bola = BolaFalsa(x=1750.0, vx=0.0)
    bola.carried = True
    corpo = CorpoFalso(x=DIR - CANTO_MARGEM - 10.0)
    alvo, ev = cont.tick(0.0, corpo, bola, 682.0, ESQ, DIR, livre=True)
    assert ev == ["tocou"]
    assert bola.tocos and bola.tocos[0][0] < 0                 # canto direito chuta para a esquerda
    assert not bola.carried                                    # a bolinha solta e vai
    cont.tick(0.2, corpo, bola, 682.0, ESQ, DIR, livre=True)
    assert cont.fase == "espera"                               # e ele espera a sua próxima


def test_chutinho_no_app_solta_e_troca_de_fase(pet_app, monkeypatch):
    monkeypatch.setattr("pestinha.mind.rebate.REBATE_PLACA_CHANCE", 0.0)
    pet_app.pet.body.grounded = True
    pet_app.pet.body.y = pet_app.bounds()[3] - 45
    pet_app.menu_rebate()
    cont = pet_app.rebate
    cont.fase, cont.lado = "levar", -1                         # canto à direita dele
    cont.canto_x = pet_app.bounds()[2] - CANTO_MARGEM
    pet_app.pet.body.x = cont.canto_x
    bola = pet_app.ball
    bola.carried = True
    pet_app._rebate_frame(time.monotonic())
    assert cont.fase == "espera" and not bola.carried          # chutou: soltou e espera


def test_bolinha_na_mao_espera_o_estilingue(tmp_path):
    cont = _controlador(tmp_path)
    bola = BolaFalsa(x=900.0)
    bola.dragging = True
    alvo, ev = cont.tick(0.0, CorpoFalso(x=100.0), bola, 682.0, ESQ, DIR, livre=True)
    assert alvo is None and bola.carried is False              # na sua mão: ele espera


def test_livre_falso_larga_o_colo(tmp_path):
    cont = _controlador(tmp_path)
    bola = BolaFalsa(x=1500.0)
    bola.carried = True
    cont.fase, cont.lado, cont.canto_x = "levar", 1, 130.0
    alvo, _ev = cont.tick(0.0, CorpoFalso(x=1500.0), bola, 682.0, ESQ, DIR, livre=False)
    assert bola.carried is False and alvo is None              # no ar/segurado: solta e espera


def test_sem_jogada_sua_o_rali_vive_pela_bolinha_vinda(tmp_path):
    """Sem soltar novo, ele não recomeça por conta própria; se a bolinha veio até ele,
    corre e leva até o canto — e o chute CRUZA a tela (não é um vx=0 que só pula em pé)."""
    cont = _controlador(tmp_path)          # sem lado definido: o chutão vale pelo canto DELE
    bola = BolaFalsa(x=150.0)
    cont.fase = "espera"
    cont._ultimo_release = bola.last_release                   # sem soltar novo jamais
    corpo = CorpoFalso(x=140.0)
    toco_em = None
    for _passo in range(3000):                                 # a vida: pega, leva e chuta uma vez
        alvo, ev = cont.tick(_passo * 0.016, corpo, bola, 682.0, ESQ, DIR, livre=True)
        if alvo is not None:                                   # ele desliza ao alvo (aproxima)
            corpo.x += 12.0 if alvo > corpo.x else -12.0
        if "tocou" in ev and toco_em is None:
            toco_em = _passo
    assert toco_em is not None and bola.tocos                  # o toco do rali saiu
    assert bola.tocos[0][0] != 0                               # o chutão CRUZA (não pula no lugar)
    assert len(bola.tocos) == 1                                # sem repetição sem nova devolução


def test_frase_da_secao_brincadeira(tmp_path):
    cont = _controlador(tmp_path)
    assert isinstance(cont.frase(), str) and cont.frase()


# ---------------------------------------------------------------- no app

def test_menu_liga_e_desliga(pet_app):
    pet_app.pet.body.grounded = True
    pet_app.menu_rebate()
    assert pet_app.rebate.ativo and pet_app.rebate.fase == "correr"
    assert pet_app.pet_state.rebate is True
    assert abs(pet_app.ball.body.x - (pet_app.pet.body.x + 80.0)) < 2   # a bola nos pezinhos dele
    pet_app.menu_rebate()
    assert not (pet_app.rebate.ativo or pet_app.pet_state.rebate)
    assert pet_app.ball.carried is False


def test_rali_rodando_no_app(pet_app, monkeypatch):
    monkeypatch.setattr("pestinha.mind.rebate.REBATE_PLACA_CHANCE", 0.0)
    pet_app.pet.body.grounded = True
    pet_app.pet.body.y = pet_app.bounds()[3] - 45
    pet_app.menu_rebate()
    for _ in range(500):                                       # pesca, leva e chuta sozinho
        pet_app.frame()
        time.sleep(0.004)
        if pet_app.rebate.fase == "espera" and pet_app.rebate.lado != 0:
            break
    assert pet_app.rebate.lado != 0                            # o rali viveu (o toco saiu)
    pet_app.menu_rebate()                                      # desliga sem deixar nada pela frente
    assert pet_app.pet_state.rebate is False and pet_app.ball.carried is False


def test_placa_nasce_na_cabecinha_e_sai_sozinha(pet_app):
    pet_app.pet.body.grounded = True
    agora = time.monotonic()
    pet_app._placa_do_rali("TOCA DE NOVO!", agora)
    placa, _prazo = pet_app._placa_rali
    assert placa.isVisible() and placa.text == "TOCA DE NOVO!"
    pet_app._rebate_frame(agora + 16.0)                        # passou a vida da placa
    assert pet_app._placa_rali is None and not placa.isVisible()


def test_placa_no_clique_sai_logo(pet_app):
    agora = time.monotonic()
    pet_app._placa_do_rali("BOA!", agora)
    placa, _prazo = pet_app._placa_rali
    pet_app._fechar_placa(placa)                               # o clique nela
    assert pet_app._placa_rali is None and not placa.isVisible()


def test_ponteiro_nao_empurra_no_rali(pet_app):
    pet_app.pet.body.grounded = True
    pet_app.menu_rebate()
    bola = pet_app.ball
    bola.body.x, bola.body.y = 500.0, pet_app.bounds()[3] - 18
    bola.body.vx = bola.body.vy = 0.0
    pet_app.last_cursor_push = time.monotonic() - 10.0
    for _ in range(6):                                         # cursor por cima da bolinha
        pet_app.frame()
        time.sleep(0.004)
    assert abs(bola.body.vx) < 1                               # o ponteiro não derruba o estilingue
