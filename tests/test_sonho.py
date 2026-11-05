"""
SONHO: ao acordar, ele costura o que viveu (memória episódica de verdade) num sonho
e leva até você um bilhete contando. Offscreen com app real, como os outros momentos.
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
from pestinha.ajustes import SONHO_MIN_PAUSA  # noqa: E402
from pestinha.app import PestinhaApp  # noqa: E402
from pestinha.mind import sonho  # noqa: E402
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


def _ep(contexto, acao, valencia=0.5, resultado="ficou na tela 12 s"):
    return {"id": f"{contexto}-{acao}", "quando": "2026-01-01T10:00:00", "contexto": contexto,
            "acao": acao, "resultado": resultado, "valencia": valencia}


def _memoria(*episodios):
    class Memoria:
        pass
    mem = Memoria()
    mem.recent = list(episodios)
    return mem


# ---------------------------------------------------------------- texto do sonho

def test_sem_memoria_nao_ha_sonho():
    assert sonho.contar(_memoria(), chance=1.0) == ""


def test_um_episodio_sozinho_nao_vira_sonho():
    assert sonho.contar(_memoria(_ep("PROGRAMMING|curioso", "bilhete")), chance=1.0) == ""


def test_chance_zero_nao_sona():
    memoria = _memoria(_ep("PROGRAMMING|curioso", "bilhete"), _ep("BROWSING|feliz", "meme"))
    assert sonho.contar(memoria, chance=0.0) == ""


def test_sonho_costura_atividade_acao_e_fim_de_verdade():
    memoria = _memoria(_ep("PROGRAMMING|curioso", "bilhete", resultado="dispensado em 2,0 s"),
                       _ep("GAMING|feliz", "meme"))
    texto = sonho.contar(memoria, chance=1.0)
    assert "programando" in texto                # a atividade real do episódio
    assert "colei um bilhete" in texto           # o que de fato ele fez
    assert "dispensou" in texto                  # como o episódio acabou
    assert texto.endswith(".")                   # frase fechada
    assert any(h in texto for h in sonho.FELIZ + sonho.MAGOADO)   # humor no fim


def test_humor_do_sonho_vem_da_valencia():
    brava = _memoria(_ep("PROGRAMMING|bravo", "bilhete", valencia=-0.8),
                     _ep("PROGRAMMING|bravo", "meme", valencia=-0.7))
    texto_bravo = sonho.contar(brava, chance=1.0)
    assert any(m in texto_bravo for m in sonho.MAGOADO)
    contente = _memoria(_ep("BROWSING|feliz", "meme", valencia=0.9),
                        _ep("GAMING|feliz", "foto", valencia=0.8))
    texto_contente = sonho.contar(contente, chance=1.0)
    assert any(f in texto_contente for f in sonho.FELIZ)


# ---------------------------------------------------------------- entrega ao acordar

def test_acordar_descansado_entrega_o_sonho(pet_app, monkeypatch):
    monkeypatch.setattr(sonho, "contar", lambda memoria, chance=None: "Sonhei com você.")
    pet_app.pet.body.grounded = True
    pet_app._sonho_ao_acordar()
    assert pet_app.behavior.mission and pet_app.behavior.mission[0] == "deliver"
    thing = pet_app.mischief.things[-1]
    assert getattr(thing, "carried", False)      # o sonho nasce pendurado nele


def test_susto_nao_vira_sonho(pet_app, monkeypatch):
    chamado = {}
    monkeypatch.setattr(sonho, "contar", lambda memoria, chance=None: chamado.setdefault("ok", True))
    pet_app._sonho_ao_acordar(startled=True)
    assert not chamado                           # no susto ele fica quieto, sem recado


def test_sonho_sem_corpo_livre_nao_nasce(pet_app, monkeypatch):
    monkeypatch.setattr(sonho, "contar", lambda memoria, chance=None: "Sonhei com você.")
    pet_app.pet.body.grounded = True
    pet_app.pet.body.held = True                 # você está segurando-o
    assert pet_app._sonho_ao_acordar() is None
    assert pet_app.behavior.mission is None      # não entra em missão e não perde nada


def test_volta_de_pausa_longa_sonha(pet_app, monkeypatch):
    monkeypatch.setattr(sonho, "contar", lambda memoria, chance=None: "Sonhei que o tempo parou.")
    pet_app.pet.body.grounded = True
    pet_app.paused = True                        # já está pausado a tempo longo
    pet_app._pausado_em = time.monotonic() - SONHO_MIN_PAUSA - 1.0
    pet_app.toggle_pause()                       # a retomada é que conta o que sonhou
    assert pet_app.behavior.mission and pet_app.behavior.mission[0] == "deliver"


def test_volta_de_pausa_curta_nao_sonha(pet_app, monkeypatch):
    monkeypatch.setattr(sonho, "contar", lambda memoria, chance=None: "Sonhei que o tempo parou.")
    pet_app.paused = True
    pet_app._pausado_em = time.monotonic() - 5.0
    pet_app.toggle_pause()
    assert pet_app.behavior.mission is None      # pausa curta: sem sonho, sem recado
