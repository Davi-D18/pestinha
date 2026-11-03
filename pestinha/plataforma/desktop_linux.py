"""
Linux: integração com o desktop, por arquivos XDG (nada de serviço escondido).

    autostart   ~/.config/autostart/pestinha.desktop      abrir com o sistema
    menu        ~/.local/share/applications + icones      aparecer no menu de aplicativos

O próprio arquivo é o estado: presente = ligado, ausente = desligado. Tudo fica na sua pasta de
usuário, é visível e apagável à mão. `$XDG_CONFIG_HOME` e `$XDG_DATA_HOME` são respeitados.
"""

import os
import shutil
import sys
from pathlib import Path

from .. import config

ID = "pestinha"
ROOT = Path(__file__).resolve().parent.parent          # pasta do programa (main.py ao lado desta pasta)
ICONE_REPO = ROOT / "extras" / f"{ID}-icone.png"


def pasta_config():
    """$XDG_CONFIG_HOME ou ~/.config."""
    return Path(os.environ.get("XDG_CONFIG_HOME") or "~/.config").expanduser()


def pasta_dados():
    """$XDG_DATA_HOME ou ~/.local/share."""
    return Path(os.environ.get("XDG_DATA_HOME") or "~/.local/share").expanduser()


def arquivo_autostart():
    """O arquivo de autostart deste app (~/.config/autostart/pestinha.desktop)."""
    return pasta_config() / "autostart" / f"{ID}.desktop"


def arquivo_menu():
    """O arquivo do menu de aplicativos (~/.local/share/applications/pestinha.desktop)."""
    return pasta_dados() / "applications" / f"{ID}.desktop"


def pasta_icone(tamanho=256):
    """Pasta do ícone no tema hicolor (256x256 por padrão)."""
    return pasta_dados() / "icons" / "hicolor" / f"{tamanho}x{tamanho}" / "apps"


def comando_exec(raiz=ROOT, executavel=None):
    """
    Como abrir o pet a partir do arquivo .desktop: `python main.py --direto` rodando do código,
    ou o executável com `--direto` quando empacotado (PyInstaller, main.py não está ao lado).
    """
    if (raiz / "main.py").exists():
        return [executavel or sys.executable, str(raiz / "main.py"), "--direto"]
    return [str(Path(executavel or sys.executable).resolve()), "--direto"]


def _exec_escapado(comandos):
    """Junta a linha Exec pondo aspas onde precisa (caminho com espaço continua válido)."""
    return " ".join(str(p) if " " not in str(p) else f'"{p}"' for p in comandos)


def texto_desktop(titulo, comandos, autostart=False):
    """Conteúdo de um .desktop válido (padrão XDG): cabeçalho obrigatório e pares CHAVE=valor."""
    linhas = [
        "[Desktop Entry]",
        f"Name={titulo}",
        f"Comment=Pet de tela do {config.APP_NOME}",
        f"Exec={_exec_escapado(comandos)}",
        "Type=Application",
        "Terminal=false",
        "Categories=Utility;",
    ]
    if autostart:
        linhas.append("X-GNOME-Autostart-enabled=true")
    return "\n".join(linhas) + "\n"


def autostart_ativo():
    """Diz se o pet abre junto com o sistema (o arquivo existe)."""
    return arquivo_autostart().exists()


def definir_autostart(on, raiz=ROOT, executavel=None):
    """Escreve ou apaga o arquivo de autostart; devolve o estado final (False em erro de gravação)."""
    caminho = arquivo_autostart()
    if not on:
        try:
            caminho.unlink(missing_ok=True)
        except OSError:
            pass
        return not caminho.exists()
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        conteudo = texto_desktop(config.APP_NOME, comando_exec(raiz, executavel), autostart=True)
        caminho.write_text(conteudo, encoding="utf-8")
    except OSError:
        return False
    return autostart_ativo()


def menu_instalado():
    """Diz se o pet aparece no menu de aplicativos (o arquivo existe)."""
    return arquivo_menu().exists()


def definir_menu(on, raiz=ROOT, executavel=None):
    """Escreve ou apaga o .desktop do menu de aplicativos; devolve o estado final."""
    caminho = arquivo_menu()
    if not on:
        try:
            caminho.unlink(missing_ok=True)
        except OSError:
            pass
        return not caminho.exists()
    try:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        conteudo = texto_desktop(config.APP_NOME, comando_exec(raiz, executavel))
        caminho.write_text(conteudo, encoding="utf-8")
    except OSError:
        return False
    return menu_instalado()


def caminho_do_icone(tamanho=256):
    """Onde o ícone do tema hicolor tem de ficar para os menus acharem."""
    return pasta_icone(tamanho) / f"{ID}.png"


def icone_instalado(tamanho=256):
    """Diz se o ícone já está no tema hicolor (ou existe no repo para copiar)."""
    return caminho_do_icone(tamanho).exists() or ICONE_REPO.exists()


def instalar_icone(caminho_png, tamanho=256):
    """Copia o png para os ícones hicolor do usuário; o .desktop aponta só pelo nome, sem caminho."""
    try:
        destino = caminho_do_icone(tamanho)
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(caminho_png), str(destino))
    except OSError:
        return False
    return destino.exists()
