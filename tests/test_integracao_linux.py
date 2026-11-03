"""
Integração Linux: sessão (Wayland/X11, ferramentas), o canal de pânico por sinal e a
integração de desktop por arquivos XDG (tudo em pastas temporárias, nada encosta na sua home).
"""
import os
import select
import signal
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pestinha.plataforma import linux  # noqa: E402
from pestinha.plataforma import _comum  # noqa: E402
from pestinha.plataforma import desktop_linux  # noqa: E402


def _home_temp(monkeypatch, tmp_path):
    """XDG redirecionado a pastas temporárias: o teste não toca em ~/.config nem ~/.local."""
    config = tmp_path / "config"
    dados = tmp_path / "dados"
    config.mkdir()
    dados.mkdir()
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    monkeypatch.setenv("XDG_DATA_HOME", str(dados))
    return config, dados


def _raiz_de_teste(tmp_path):
    """Uma pasta que parece a do programa (com main.py), para o Exec não depender do repo."""
    raiz = tmp_path / "programa"
    raiz.mkdir(parents=True)
    (raiz / "main.py").write_text("#", encoding="utf-8")
    return raiz


# ---------------------------------------------------------------- sessão


@pytest.mark.parametrize("ambiente,esperado", [
    ({"WAYLAND_DISPLAY": "wayland-0", "XDG_SESSION_TYPE": "x11"}, "wayland"),   # o display manda
    ({"XDG_SESSION_TYPE": "x11"}, "x11"),
    ({"XDG_SESSION_TYPE": "tty"}, "tty"),
    ({}, "desconhecido"),
])
def test_modo_sessao_pelo_ambiente(monkeypatch, ambiente, esperado):
    for chave in ("WAYLAND_DISPLAY", "XDG_SESSION_TYPE"):
        monkeypatch.delenv(chave, raising=False)
    for chave, valor in ambiente.items():
        monkeypatch.setenv(chave, valor)
    assert linux.modo_sessao() == esperado


def test_wayland_avisa_o_que_ele_nao_ve(monkeypatch):
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    avisos = "\n".join(linux.avisos_sessao())
    assert "Wayland" in avisos
    assert "janelas" in avisos and "ocioso" in avisos


def test_x11_sem_ferramentas_avisa(monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.setattr(linux, "_ferramentas_faltando", ["xdotool", "wmctrl"])
    avisos = linux.avisos_sessao()
    assert avisos and "xdotool" in avisos[0] and "wmctrl" in avisos[0]


def test_aviso_vazio_quando_esta_tudo_bem(monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.setattr(linux, "_ferramentas_faltando", [])
    assert linux.avisos_sessao() == []


def test_ferramentas_faltando_limpa_a_si_so(monkeypatch):
    monkeypatch.setattr(linux.shutil, "which", lambda nome: None if nome == "wmctrl" else "/usr/bin/" + nome)
    linux._ferramentas_faltando = None
    try:
        assert linux.ferramentas_faltando() == ["wmctrl"]
    finally:
        linux._ferramentas_faltando = None


# ---------------------------------------------------------------- pânico por sinal


def test_sinal_escreve_no_canal():
    leitura, escrita = os.pipe()
    anterior = signal.getsignal(signal.SIGUSR1)
    try:
        fd = _comum.canal_panic_sinal(_pipe=(leitura, escrita))
        assert fd == leitura
        os.kill(os.getpid(), signal.SIGUSR1)
        recebido = b""
        for _ in range(300):                       # o handler roda entre bytecodes: pequena espera
            pronto, _, _ = select.select([leitura], [], [], 0.01)
            if pronto:
                recebido = os.read(leitura, 16)
                break
        assert recebido == b"1"
    finally:
        signal.signal(signal.SIGUSR1, anterior)


# ---------------------------------------------------------------- desktop XDG


def test_exec_escapa_caminho_com_espacos(tmp_path):
    raiz = tmp_path / "programa do pet"
    raiz.mkdir()
    (raiz / "main.py").write_text("#", encoding="utf-8")
    conteudo = desktop_linux.texto_desktop(desktop_linux.ID, desktop_linux.comando_exec(raiz, "python"))
    assert f'"{raiz}/main.py" --direto' in conteudo
    assert conteudo.startswith("[Desktop Entry]")


def test_autostart_e_menu_segundo_o_arquivo(monkeypatch, tmp_path):
    config, dados = _home_temp(monkeypatch, tmp_path)
    raiz = _raiz_de_teste(tmp_path)

    assert not desktop_linux.autostart_ativo()
    assert desktop_linux.definir_autostart(True, raiz=raiz)
    caminho = config / "autostart" / "pestinha.desktop"
    texto = caminho.read_text(encoding="utf-8")
    assert texto.startswith("[Desktop Entry]")
    for parte in ("Name=Pestinha", "--direto", "X-GNOME-Autostart-enabled=true", str(raiz / "main.py")):
        assert parte in texto
    assert desktop_linux.autostart_ativo()

    assert desktop_linux.definir_autostart(False)
    assert not caminho.exists()
    assert not desktop_linux.autostart_ativo()

    assert not desktop_linux.menu_instalado()
    assert desktop_linux.definir_menu(True, raiz=raiz)
    menu = dados / "applications" / "pestinha.desktop"
    texto_menu = menu.read_text(encoding="utf-8")
    assert texto_menu.startswith("[Desktop Entry]")
    assert "X-GNOME-Autostart-enabled" not in texto_menu
    assert desktop_linux.menu_instalado()
    assert desktop_linux.definir_menu(False)
    assert not menu.exists()


def test_autostart_com_executavel_proprio(monkeypatch, tmp_path):
    config, _dados = _home_temp(monkeypatch, tmp_path)
    pasta = tmp_path / "entrega"           #empacotado: sem main.py, o executável é o caminho
    pasta.mkdir()
    contagem = (tmp_path / "bin" / "Pestinha")
    contagem.parent.mkdir()
    contagem.write_text("#", encoding="utf-8")

    assert desktop_linux.definir_autostart(True, raiz=pasta, executavel=str(contagem))
    texto = (config / "autostart" / "pestinha.desktop").read_text(encoding="utf-8")
    assert f"Exec={contagem} --direto" in texto


def test_icone_e_pasta_pelo_xdg(monkeypatch, tmp_path):
    _config, dados = _home_temp(monkeypatch, tmp_path)
    destino = desktop_linux.caminho_do_icone()
    assert destino == dados / "icons" / "hicolor" / "256x256" / "apps" / "pestinha.png"
    origem = tmp_path / "rosto.png"
    origem.write_bytes(b"png")
    assert desktop_linux.instalar_icone(origem)
    assert destino.exists() and destino.read_bytes() == b"png"
