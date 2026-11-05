"""
LEMBRETES: recado com horário — dá no menu, na hora ele cutuca três vezes e cola
o bilhete. Offscreen com app real, como os outros momentos.
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
from pestinha.mind.lembretes import Lembretes  # noqa: E402
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


# ---------------------------------------------------------------- controlador

def test_adiciona_e_persiste(tmp_path):
    lembretes = Lembretes(tmp_path / "lembretes.json")
    agora = time.time()
    assert lembretes.adicionar("café para você", agora + 60.0)
    de_novo = Lembretes(tmp_path / "lembretes.json")     # arquivo é a fonte na próxima sessão
    assert [item["texto"] for item in de_novo.recados] == ["café para você"]


def test_recusa_vazio_e_passado(tmp_path):
    lembretes = Lembretes(tmp_path / "lembretes.json")
    agora = time.time()
    assert not lembretes.adicionar("   ", agora + 60.0)
    assert not lembretes.adicionar("café", agora - 1.0)
    assert lembretes.recados == []


def test_arquivo_corrompido_volta_vazio(tmp_path):
    caminho = tmp_path / "lembretes.json"
    caminho.write_text("{ quebra ", encoding="utf-8")
    assert Lembretes(caminho).recados == []


def test_vencer_da_o_vencido_e_tira_da_lista(tmp_path):
    lembretes = Lembretes(tmp_path / "lembretes.json")
    agora = time.time()
    lembretes.adicionar("café para você", agora + 30.0)
    lembretes.adicionar("café para você", agora + 5.0)   # o segundo vence primeiro
    lembretes.recados[0]["quando"] = agora - 1.0         # finge que a hora chegou
    assert lembretes.vencer() == "café para você"
    assert all(item["quando"] > agora - 60.0 for item in lembretes.recados)
    assert lembretes.vencer() is None                    # só um estava vencido


# ---------------------------------------------------------------- no app

def test_recado_vencido_cutuca_tres_e_entrega(pet_app, monkeypatch):
    pet_app.lembretes.adicionar("café para você", time.time() + 60.0)
    pet_app.lembretes.recados[0]["quando"] = time.time() - 1.0   # finge que a hora chegou
    pet_app.pet.body.grounded = True
    cutucadas = []
    monkeypatch.setattr(pet_app, "menu_poke", lambda: cutucadas.append(1))

    agora = time.monotonic()
    pet_app._lembrete_tick(agora)                        # venceu: arma o alerta
    for passo in (0.6, 1.2, 1.8):                        # três cutucadas espaçadas
        pet_app._lembrete_tick(agora + passo)
    assert len(cutucadas) == 3
    pet_app._lembrete_tick(agora + 2.4)                  # última: cola o bilhete
    assert pet_app.behavior.mission and pet_app.behavior.mission[0] == "deliver"
    thing = pet_app.mischief.things[-1]
    assert getattr(thing, "carried", False)
    assert text_is_carried(thing, "café para você")
    assert pet_app.lembretes.recados == []               # recado cumprido


def test_recado_nao_derruba_sem_corpo_livre(pet_app):
    pet_app.lembretes.adicionar("café para você", time.time() - 1.0)
    pet_app.pet.body.held = True                         # você está segurando-o
    for passo in range(8):
        pet_app._lembrete_tick(time.monotonic() + passo)
    assert pet_app.behavior.mission is None


def text_is_carried(thing, expected):
    """O bilhete carregado guarda o texto do recado no campo `text` do NoteThing."""
    return expected in getattr(thing, "text", "")
