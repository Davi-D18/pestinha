"""
Dinâmica nova: carga da máquina (HEAT), tempestade de Alt+Tab, música que vira dança,
malhação, sonhos e a comida (biscoito do menu). Roda em offscreen com app de verdade.
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
from pestinha.app import PestinhaApp  # noqa: E402
from pestinha.core.nervous_system import SENSORY_SPEC, CONNECTIONS  # noqa: E402
from pestinha.paths import Paths  # noqa: E402
from pestinha.plataforma._comum import clamp_carga, carga_sistema  # noqa: E402
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


# ---------------------------------------------------------------- carga (HEAT)


def test_canais_anacones_existe():
    assert "HEAT" in SENSORY_SPEC and "FOOD" in SENSORY_SPEC
    assert ("HEAT", "TIRED", 0.07, 0.6) in CONNECTIONS
    assert ("FOOD", "CURIOUS", 0.09, 0.6) in CONNECTIONS


def test_carga_clamp():
    assert clamp_carga(50.0) == 0.0          # máquina leve não aquece
    assert clamp_carga(70.0) == 0.0
    assert 0.19 <= clamp_carga(75.0) <= 0.21
    assert clamp_carga(95.0) == 1.0
    assert clamp_carga(float("nan")) == 0.0


def test_carga_entre_0_e_1_e_cachemira(monkeypatch):
    monkeypatch.setattr("pestinha.plataforma._comum._primeira_carga", [False])
    monkeypatch.setattr("pestinha.plataforma._comum._ultima_carga", [time.monotonic(), 120.0])
    valor = carga_sistema()                   # dentro da janela de 0,9 s vem do cache
    assert 0.0 <= valor <= 1.0


def test_heating_entra_na_intensidade(pet_app):
    pet_app.carga = 1.0
    pet_app._ultimo_think = None
    pet_app.think()
    assert pet_app.intensities["HEAT"] == 1.0


# ---------------------------------------------------------------- tempestade de Alt+Tab


def test_muitas_trocas_dizem_tempestade(pet_app):
    agora = time.monotonic()
    pet_app._trocas_janelas.extend([agora - 3.0] * 7)     # sete antes + a nova
    pet_app._tempestade(["APP_CHANGED"])
    assert pet_app._tempestade_ate > agora + 100.0        # guardou o silêncio entre crises
    assert pet_app.pet_state.dizzy_until > agora          # ficou tonto no susto


def test_tempestade_precisa_de_8_trocas(pet_app):
    agora = time.monotonic()
    pet_app._trocas_janelas.extend([agora - 3.0] * 6)
    pet_app._tempestade(["APP_CHANGED"])
    assert pet_app._tempestade_ate == 0.0


# ---------------------------------------------------------------- susto com tela cheia


def test_susto_de_tela_cheia_vira_pulo(pet_app):
    """A via do susto (fullscreen abrindo força 'assustado'): ao trocar a emoção, o corpo pula."""
    b = pet_app.behavior
    b.emotion = "observando"
    b.body.grounded = True
    agora = time.monotonic()
    pet_app.emotion.force("assustado", 1.0, agora, 40)          # o susto usa prioridade de assustado
    emotion = pet_app.emotion.update({}, 0.016, pet_app.prof)
    assert emotion == "assustado"
    b.on_emotion(emotion, agora)
    assert not b.body.grounded                                  # pulinho de susto


# ---------------------------------------------------------------- música, malhação


def test_qualquer_player_e_musica():
    from pestinha.sense.senses import detect_activity
    assert detect_activity("vlc", 0.0, 60.0) == "MUSIC"          # qualquer player vale
    assert detect_activity("rhythmbox", 0.0, 60.0) == "MUSIC"    # gnome
    assert detect_activity("MusicBee.exe", 0.0, 60.0) == "MUSIC" # windows, com .exe
    assert detect_activity("Youtube-Music", 0.0, 60.0) == "MUSIC"
    assert detect_activity("nautilus", 0.0, 60.0) == "IDLE"      # gerente de arquivos não é música


def test_musica_alta_vira_pulinho_no_compasso(pet_app):
    b = pet_app.behavior
    b.groove = 1.0
    b._beat = 0.0
    b.emotion = "observando"
    b.body.grounded = True
    b.tick(0.016, time.monotonic(), (0, 0), b.body.x and (0, 0, 1600, 900), config.PROFILES["teste"])
    assert b._beat > 0.0                                  # marcou o compasso
    assert not b.body.grounded                            # e pulou


def test_malhacao_dispara_e_gasta(pet_app, monkeypatch):
    monkeypatch.setattr("pestinha.body.behavior.random.random", lambda: 0.0)
    b = pet_app.behavior
    b.energy = 1.0
    b.next_treino = 0.0
    b.next_roam = 0.0
    b.emotion = "feliz"
    b.body.grounded = True
    b.tick(0.016, time.monotonic(), (0, 0), (0, 0, 1600, 900), config.PROFILES["teste"])
    assert b.treino is not None                           # começou a roda
    antes = pet_app.drives.energy
    pet_app.behavior.treino = (time.monotonic() + 10.0, time.monotonic() - 1.0)
    pet_app._ultimo_think = None
    pet_app.think()
    assert pet_app.drives.energy < antes                  # os pulinhos gastam


# ---------------------------------------------------------------- comida


def test_menu_comida_aparece_e_ele_come(pet_app):
    antes = pet_app.drives.energy
    pet_app.menu_comida()
    assert pet_app.comida.isVisible()
    pet_app.think()                                       # o alvo entra no comportamento no think
    assert pet_app.behavior.comida is not None
    pet_app._comer("biscoito", time.monotonic())          # ele alcançou: mordida
    assert not pet_app._comida_na_tela
    assert pet_app.drives.energy >= min(1.0, antes + 0.35)
    assert pet_app._premio_comida == 0.30                 # recompensa pendente para o learn


def test_comida_na_mao_tambem_e_mordida(pet_app, monkeypatch):
    """Você encostando o biscoito na boca dele (arrastado) conta como mordida na hora."""
    biscoito = pet_app.comida
    pet_app.menu_comida()
    pet_app.pet.body.grounded = True                      # sem loop de quadros no teste, forço o chão
    biscoito.dragging = True                              # está na sua mão
    monkeypatch.setattr(biscoito, "handled_by_user", lambda now: True)   # antes: isso travava a mordida
    biscoito.body.x = pet_app.pet.body.x                  # encosto na cabecinha
    biscoito.body.y = pet_app.pet.body.y
    pet_app.drives.energy = 0.5                           # energia baixa para a refeição aparecer
    antes = pet_app.drives.energy
    pet_app.think()
    assert not pet_app._comida_na_tela                    # comeu mesmo com o biscoito na mão
    assert pet_app.drives.energy > antes


def test_ja_comida_sai_do_menu(pet_app):
    pet_app.menu_comida()
    pet_app.menu_comida()                                 # segunda chamada recolhe
    assert not pet_app.comida.isVisible()
    assert pet_app.behavior.comida is None


# ---------------------------------------------------------------- sonhos


def test_sonho_tem_campos_e_recolhe(pet_app):
    st = pet_app.pet_state
    agora = time.monotonic()
    st.dream_path = "x.png"
    st.dream_de = agora
    st.dream_ate = agora - 1.0
    pet_app._sonhos(agora + 1.0)
    assert st.dream_path is None                          # sonho vencido: o app recolhe


# ---------------------------------------------------------------- outro monitor


def test_troca_de_monitor_manda_o_pet_para_a_outra_tela(pet_app, monkeypatch):
    pet_app.pet.body.x, pet_app.pet.body.y = 400.0, 800.0
    monkeypatch.setattr(pet_app, "screen_bounds", lambda: [(0, 0, 1600, 1000), (1600, 0, 3200, 1000)])
    pet_app.menu_trocar_monitor()
    corpo = pet_app.pet.body
    assert corpo.x > 1600                                 # saiu da primeira tela
    assert corpo.grounded and corpo.y > 900               # pousa direto no chão da tela nova


def test_troca_de_monitor_sem_segunda_tela_e_passo_nulo(pet_app):
    x, y = pet_app.pet.body.x, pet_app.pet.body.y         # offscreen: uma tela só
    pet_app.menu_trocar_monitor()
    assert pet_app.pet.body.x == x and pet_app.pet.body.y == y


def test_mpris_nao_explode_sem_player():
    from pestinha.sense.senses import musica_tocando
    assert musica_tocando() in (True, False)      # com ou sem D-Bus, roda sem quebrar
