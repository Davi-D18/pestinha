"""
MOMENTOS: as interações novas — comida variada (biscoito/café/água), presente-surpresa,
balanço (gargalhada), beijo do dia, Tacinho e o tandem de digitação. Offscreen com app real.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402
from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pestinha import config  # noqa: E402
from pestinha.ajustes import (  # noqa: E402
    ENERGIA_AGUA,
    ENERGIA_CAFE,
    RECOMPENSA_BALANCO,
    RECOMPENSA_BEIJO,
    RECOMPENSA_PRESENTE,
)
from pestinha.app import PestinhaApp  # noqa: E402
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


@pytest.fixture
def com_recadinhos(tmp_path):
    """App com um recadinhos.txt no comum criado ANTES: é o caminho por onde a Notes carrega as frases."""
    app_qt = QApplication.instance() or QApplication([])
    app_qt.setQuitOnLastWindowClosed(False)
    paths = Paths(root=tmp_path)
    paths.comum.mkdir(parents=True, exist_ok=True)
    (paths.comum / "recadinhos.txt").write_text("gire de novo\ncaixa mágica\n", encoding="utf-8")
    store = SettingsStore(paths)
    store.update(dict(config.DEFAULT_PERMISSIONS))
    app = PestinhaApp(store, paths)
    yield app
    for timer in app.findChildren(QTimer):
        timer.stop()
    for w in list(app.floats.windows.values()):
        w.close()


# ---------------------------------------------------------------- comida variada

def test_menu_comida_troca_e_recolhe(pet_app):
    pet_app.menu_comida("cafe")
    assert pet_app._comida_na_tela and pet_app.comida.tipo == "cafe"
    pet_app.menu_comida("cafe")            # clicar de novo com o mesmo tipo recolhe
    assert not pet_app._comida_na_tela
    pet_app.menu_comida("agua")
    assert pet_app._comida_na_tela and pet_app.comida.tipo == "agua"


def test_cafe_enche_mais_e_fica_nervoso(pet_app):
    pet_app.drives.energy = 0.2
    antes = pet_app.drives.energy
    agora = time.monotonic()
    pet_app._comer("cafe", agora)
    assert pet_app.drives.energy == min(1.0, antes + ENERGIA_CAFE)
    assert pet_app.pet_state.cafeina_ate > agora
    assert not pet_app._comida_na_tela     # a comida some ao tomar


def test_agua_assenta_tira_a_tontura(pet_app):
    pet_app.drives.energy = 0.2
    agora = time.monotonic()
    pet_app.pet_state.dizzy_until = agora + 5.0
    pet_app._comer("agua", agora)
    assert pet_app.pet_state.dizzy_until == 0.0
    assert pet_app.drives.energy == min(1.0, 0.2 + ENERGIA_AGUA)


def test_biscoito_mantem_o_efeito_antigo(pet_app):
    pet_app.drives.energy = 0.1
    agora = time.monotonic()
    pet_app._comer("biscoito", agora)
    assert pet_app.pet_state.feliz_ate == agora + 2.5
    assert not pet_app._comida_na_tela


# ---------------------------------------------------------------- presente

def test_menu_presente_liga_e_desliga(pet_app):
    pet_app.menu_presente()
    assert pet_app._presente_na_tela and pet_app.presente.sprite is None
    pet_app.menu_presente()
    assert not pet_app._presente_na_tela


def test_presente_festa(monkeypatch, pet_app):
    monkeypatch.setattr("pestinha.app.random.random", lambda: 0.0)
    pet_app._presente_na_tela = True
    pet_app._premio_extra = 0.0
    pet_app.pet.body.grounded = True
    agora = time.monotonic()
    pet_app._abrir_presente(agora)
    assert not pet_app._presente_na_tela           # a caixinha some ao abrir
    assert pet_app._premio_extra == RECOMPENSA_PRESENTE
    assert pet_app.pet_state.feliz_ate == agora + 3.0


def test_presente_bilhete(monkeypatch, com_recadinhos):
    app = com_recadinhos
    app.perms["travessuras"] = True
    app.perms["bilhetes"] = True
    monkeypatch.setattr("pestinha.app.random.random", lambda: 0.5)
    app._presente_na_tela = True
    app._abrir_presente(time.monotonic())
    assert len(app.mischief.things) == 1           # veio o bilhete


def test_bilhete_sem_permissao_nao_sai(pet_app):
    assert pet_app.perms["travessuras"] is False
    assert pet_app._soltar_bilhete() is False
    assert not pet_app.mischief.things


# ---------------------------------------------------------------- balanço

def test_gargalhada_quando_chacoalha(pet_app):
    pet_app._premio_extra = 0.0
    pet_app.pet.body.grounded = True
    pet_app.on_shaken()
    assert pet_app._premio_extra == RECOMPENSA_BALANCO
    assert pet_app.pet_state.dizzy_until > time.monotonic()   # fica meio tonto


def test_balanco_detectado_no_arraste(monkeypatch, pet_app):
    relogio = [0.0]
    monkeypatch.setattr("pestinha.body.pet.time.monotonic", lambda: relogio[0])
    ouviu = []
    pet_app.pet.shaken.connect(lambda: ouviu.append(True))
    for x in (0.0, 90.0, 0.0, 90.0, 0.0):      # 3 trocas de lado em 0,6 s
        pet_app.pet._track_balanco(x)
        relogio[0] += 0.15
    assert ouviu and len(ouviu) == 1           # gargalha uma vez, não um alvoroço


def test_balanco_nao_dispara_de_novo_na_sequencia(monkeypatch, pet_app):
    relogio = [0.0]
    monkeypatch.setattr("pestinha.body.pet.time.monotonic", lambda: relogio[0])
    ouviu = []
    pet_app.pet.shaken.connect(lambda: ouviu.append(True))
    for volta in range(3):
        for x in (0.0, 90.0, 0.0, 90.0, 0.0):
            pet_app.pet._track_balanco(x)
            relogio[0] += 0.15
        relogio[0] += 1.0
    assert len(ouviu) >= 1                     # tem o intervalo entre gargalhadas


# ---------------------------------------------------------------- beijo

def test_beijo_primeiro_do_dia(monkeypatch, pet_app):
    monkeypatch.setattr("pestinha.controle.interacao.time.strftime", lambda *_: "2026-11-02")
    pet_app._premio_extra = 0.0
    pet_app.on_kiss()
    assert pet_app._premio_extra == RECOMPENSA_BEIJO
    assert pet_app.pet_state.beijo_para > time.monotonic()
    assert (pet_app.paths.memory / "beijos.json").exists()
    pet_app._premio_extra = 0.0
    pet_app.on_kiss()
    assert pet_app._premio_extra == 0.0        # o segundo beijo não premia de novo


# ---------------------------------------------------------------- Tacinho

def test_tacinho_entra_e_sai(pet_app):
    agora = time.monotonic()
    pet_app.menu_quieto()
    assert pet_app.pet_state.quieto(agora)
    pet_app.menu_quieto()
    assert not pet_app.pet_state.quieto(agora)


def test_tacinho_fica_no_canto(pet_app):
    pet_app.menu_quieto()
    body = pet_app.pet.body
    body.grounded = True
    body.x = 500.0
    body.vx = 0.0
    pet_app.behavior.tick(0.016, time.monotonic(), (400.0, 400.0),
                          (0, 0, 1000, 800), pet_app.prof, ())
    assert body.vx != 0.0                      # anda para o canto em vez de passear


# ---------------------------------------------------------------- tandem de digitação

@pytest.fixture
def tandem_trabalhando(pet_app, monkeypatch):
    """Pet em condições de tandem: medição real de idle e app de trabalho em primeiro plano."""
    from pestinha.sense import senses
    pet_app.activity = "PROGRAMMING"
    monkeypatch.setattr(senses, "idle_confiavel", lambda: True)
    return pet_app


def _digita(pet_app, segundos=35.0, agora=None):
    """Simula digitação contínua pelo tempo dado (o atraso do tandem é 30 s)."""
    base = time.monotonic() if agora is None else agora
    pet_app._digita_desde, pet_app._digita_bilhete_em = None, base - 1e9
    for k in range(int(segundos * 2)):
        pet_app._atualiza_tandem(base + k * 0.5, 1.0)
    return base


def test_trabalhando_tandem_ativa_e_para(tandem_trabalhando):
    st = tandem_trabalhando.pet_state
    agora = _digita(tandem_trabalhando, agora=time.monotonic())
    assert st.digitar_para > agora             # digitei junto: patinhas animam
    tandem_trabalhando._atualiza_tandem(agora + 40.0, 0.0)
    assert tandem_trabalhando._digita_desde is None       # parou de digitar, ele também para


def test_tandem_nao_rola_fora_do_trabalho_ou_sem_medicao(pet_app, monkeypatch):
    from pestinha.sense import senses
    st = pet_app.pet_state
    base = time.monotonic()
    pet_app._digita_desde, pet_app._digita_bilhete_em = None, base - 1e9
    for k in range(70):                        # app de fora da família trabalho: nada de tandem
        pet_app._atualiza_tandem(base + k * 0.5, 1.0)
    assert st.digitar_para <= base
    pet_app.activity = "PROGRAMMING"           # agora o app é de trabalho, mas...
    monkeypatch.setattr(senses, "idle_confiavel", lambda: False)   # sem medição real (Wayland)
    pet_app._digita_desde = None
    for k in range(70):
        pet_app._atualiza_tandem(base + 100.0 + k * 0.5, 1.0)
    assert st.digitar_para <= base + 100.0     # ...o 0 do fallback não é "você digitando"


def test_tandem_nao_rola_dormindo_bravo_ou_punido(tandem_trabalhando):
    app = tandem_trabalhando
    st = app.pet_state
    base = time.monotonic()
    estados = ("dormindo", "bravo", "triste", "assustado", "protesto", "castigo", "tacinho")
    for caso in estados:
        if caso == "protesto":
            st.protest_stage = 2
        elif caso == "castigo":
            st.castigo = True
        elif caso == "tacinho":
            st.quieto_ate = base + 60.0
        elif caso != "dormindo":
            app.behavior.emotion = caso
        else:
            app.sleep.asleep = True       # dormindo de verdade (o caminho que a propriedade lê)
        app._digita_desde, app._digita_bilhete_em = None, base - 1e9
        st.digitar_para = 0.0
        for k in range(70):                    # você digita, mas ele está fora de si
            app._atualiza_tandem(base + k * 0.5, 1.0)
        assert st.digitar_para <= base, caso
        app.sleep.asleep = False
        st.protest_stage, st.castigo, st.quieto_ate = 0, False, 0.0
        app.behavior.emotion = "observando"
