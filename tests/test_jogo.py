"""
JOGO: o modo companhia — ele pega o controle quando você abre um jogo da lista,
reage ao seu input, cochila se você sumir e recolhe ao sair. Offscreen com app real
(quando mexe no app) e testes puros no controlador (`mind/jogo.py`).
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
from pestinha.ajustes import (  # noqa: E402
    JOGO_AFK_COCHILO,
    JOGO_CONTROLE_EM,
    JOGO_PAUSA_REACAO,
    JOGO_RECOLHER,
)
from pestinha.app import PestinhaApp  # noqa: E402
from pestinha.mind.jogo import JogoController  # noqa: E402
from pestinha.paths import Paths  # noqa: E402
from pestinha.sense.senses import detect_activity  # noqa: E402
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


@pytest.fixture
def jogo():
    cont = JogoController(lambda: True)
    return cont


# ---------------------------------------------------------------- detecção

def test_detecta_o_jogo_da_lista():
    assert detect_activity("csgo.exe", 0.0, 600.0) == "GAMING"          # a lista de sempre
    assert detect_activity("minecraft", 0.0, 600.0, jogos=["minecraft"]) == "GAMING"
    assert detect_activity("minecraft", 0.0, 600.0, jogos=["valorant"]) == "IDLE"


def test_lista_de_jogos_da_configuracao():
    assert config.lista_de_jogos("Minecraft, Valorant.EXE,, valorant") == ["minecraft", "valorant"]
    assert config.lista_de_jogos("") == []
    assert config.lista_de_jogos(None) == []


# ---------------------------------------------------------------- o controlador

def tick(cont, t, jogando=True, input_ativo=False, afk=0.0, livre=True):
    return cont.tick(t, jogando=jogando, input_ativo=input_ativo, afk_segundos=afk, livre=livre)


def test_entrada_com_festa_e_controle(jogo):
    assert tick(jogo, 0.0) == ["festejar"]                                # o jogo entrou: festa!
    assert jogo.controle is False
    assert tick(jogo, 0.1) == []                                          # esperando se ajeitar
    res = tick(jogo, JOGO_CONTROLE_EM + 0.1)
    assert res == ["pegou_controle"] and jogo.modo and jogo.controle


def test_pico_de_acao_reage_com_respiro(jogo, monkeypatch):
    monkeypatch.setattr("pestinha.mind.jogo.JOGO_CHANCE_REACAO", 1.0)
    assert tick(jogo, 0.0, input_ativo=True) == ["festejar"]
    momento = None
    res = []
    for k in range(12):                                       # 1 s de input ligado: arma e dispara o pico
        t = 0.1 * k + 1.0
        res = tick(jogo, t, input_ativo=True)
        if res and res != ["pegou_controle"]:
            momento = t
            break
    assert res == ["pico"] and momento is not None            # o pico saltou
    assert tick(jogo, momento + 0.1, input_ativo=True) == []  # respiro entre reações
    fim = momento + JOGO_PAUSA_REACAO                         # quando o respiro termina
    t = momento + 0.2
    while t < fim - 0.05:
        assert tick(jogo, t, input_ativo=True) == []          # o tempo corre (o app chama a cada 100 ms)
        t += 0.1
    assert tick(jogo, fim, input_ativo=True) == ["pico"]      # liberou de novo: pico outra vez


def test_sem_input_muito_tempo_cochila_e_acorda(jogo):
    assert tick(jogo, 0.0) == ["festejar"]
    tick(jogo, 0.1)
    assert tick(jogo, JOGO_CONTROLE_EM + 0.1) == ["pegou_controle"]
    res = tick(jogo, JOGO_CONTROLE_EM + 1.0, afk=JOGO_AFK_COCHILO + 1.0)
    assert res == ["cochilar"] and jogo.cochilando and jogo.controle is False
    assert tick(jogo, JOGO_CONTROLE_EM + 2.0, afk=JOGO_AFK_COCHILO + 2.0) == []
    assert tick(jogo, JOGO_CONTROLE_EM + 3.0, input_ativo=True) == ["acordou"]
    assert jogo.controle is True and jogo.cochilando is False


def test_o_jogo_saiu_recolhe_depois_de_um_pouco(jogo):
    assert tick(jogo, 0.0, input_ativo=True) == ["festejar"]
    assert tick(jogo, JOGO_CONTROLE_EM + 0.1, input_ativo=True) == ["pegou_controle"]
    assert tick(jogo, 2.0, jogando=False) == []                           # saiu agora: um instante
    assert tick(jogo, 2.0 + JOGO_RECOLHER + 0.1, jogando=False) == ["soltou"]
    assert jogo.modo is False and jogo.controle is False


def test_algo_na_frente_recolhe_na_hora(jogo):
    assert tick(jogo, 0.0, input_ativo=True) == ["festejar"]
    assert tick(jogo, JOGO_CONTROLE_EM + 0.1, input_ativo=True) == ["pegou_controle"]
    assert tick(jogo, 2.0, livre=False) == ["soltou"]                     # castigo/sono/missão: fora
    assert jogo.modo is False


def test_sem_livre_nem_comeca(jogo):
    assert tick(jogo, 0.0, livre=False) == []                             # dormindo, Tacinho, no ar
    assert jogo.modo is False and jogo.controle is False


def test_sai_e_volta_do_lobby_refaz_a_festa(jogo):
    assert tick(jogo, 0.0) == ["festejar"]
    assert tick(jogo, 1.0, jogando=False) == []                           # desistiu antes de se ajeitar
    assert tick(jogo, 2.0, jogando=False) == []
    assert tick(jogo, 3.0) == ["festejar"]                                # voltou ao lobby: festa de novo
    assert jogo.modo is False


# ---------------------------------------------------------------- no app

def test_app_entering_keeps_visible_fullscreen(pet_app):
    pet_app.pet.body.grounded = True
    agora = time.monotonic()
    pet_app.activity = "GAMING"
    pet_app.fullscreen = True
    pet_app._aplicar_jogo(["festejar"], agora)
    assert pet_app.pet_state.modo_jogo is True
    assert pet_app.pet.isVisible()                                        # festa mesmo com tela cheia
    pet_app.update_visibility()
    assert pet_app.pet.isVisible()
    pet_app.activity = "IDLE"                                             # saiu do jogo (sem tela cheia ainda)
    pet_app._aplicar_jogo(["soltou"], agora)
    pet_app.update_visibility()
    assert not pet_app.pet.isVisible()                                    # fim do modo: volta ao normal


def test_behavior_parado_e_de_olho_no_jogo(pet_app):
    pet_app.pet.body.grounded = True
    st = pet_app.pet_state
    st.modo_jogo = True
    pet_app.pet.body.vx = 100.0
    now = time.monotonic()
    cursor = (pet_app.pet.body.x, pet_app.pet.body.y)
    pet_app.behavior.tick(0.02, now, cursor, pet_app.bounds(), pet_app.prof)
    assert pet_app.pet.body.vx == 0.0                                     # acompanha: parado
    assert st.gaze == pet_app.behavior.mirada_jogo                        # olho na tela
    st.modo_jogo = False


def test_configuracao_guarda_a_lista_de_jogos(pet_app):
    pet_app.apply_perms({"jogos": ["aurora", "elden ring"]})
    assert pet_app.perms["jogos"] == ["aurora", "elden ring"]             # as configurações guardam a lista
    assert pet_app.store.perms["jogos"] == ["aurora", "elden ring"]
    assert detect_activity("elden ring", 0.0, 600.0,
                           jogos=pet_app.perms["jogos"]) == "GAMING"      # e a detecção usa a lista


def test_no_modo_jogo_um_objeto_pela_vez_e_vida_curta(pet_app):
    from pestinha.ajustes import JOGO_MEME_VIDA as VIDA
    from pestinha.world.objetos import NoteThing
    perms = dict(pet_app.perms, ativo=True, travessuras=True, memes=True)
    # a faxina: objetos velhos saem sozinhos no modo jogo
    velho = NoteThing("velho")
    velho.born -= VIDA + 1.0                                       # nasceu há mais que a vida do modo
    novo = NoteThing("novo")
    pet_app.mischief._add(velho)
    pet_app.mischief._add(novo)
    assert not pet_app.mischief.allowed(perms, pet_app.prof, False, modo_jogo=True)   # limite 1 na tela
    saido = pet_app.mischief.recolher_antigos(VIDA)
    assert saido == 1 and velho not in pet_app.mischief.things and novo in pet_app.mischief.things
    assert not pet_app.mischief.allowed(perms, pet_app.prof, False, modo_jogo=True)   # ainda 1: lotado
    novo.born -= VIDA + 1.0                                        # o "novo" envelheceu: sai na próxima
    pet_app.mischief.recolher_antigos(VIDA)
    assert pet_app.mischief.things == [] and pet_app.mischief.allowed(perms, pet_app.prof, False, modo_jogo=True)


def test_desenho_do_controle_pulsa_sem_quebra_no_paint(pet_app):
    now = time.monotonic()
    st = pet_app.pet_state
    st.controle = True
    st.controle_pulse = now + 1.0                                  # a entrada: sobe de baixo
    pix = pet_app.pet.grab()
    assert not pix.isNull()
    st.controle_pulse = now + 0.3                                  # um pico: treme na pata
    pix = pet_app.pet.grab()
    assert not pix.isNull()
    st.controle, st.controle_pulse = False, 0.0
