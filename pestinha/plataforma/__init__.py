"""
PLATAFORMA - a única parte do código que conhece o sistema operacional.

Cada sistema tem um módulo com as mesmas funções (windows.py, macos.py, linux.py). Este arquivo
escolhe o certo na importação. Os retângulos são em pixels físicos (o app divide pelo dpr).

    ocioso_segundos()            segundos desde o último teclado ou mouse
    processo_ativo()             nome (minúsculo) do programa em primeiro plano
    retangulo_ativo(escala)      retângulo da janela em primeiro plano, ou None
    tela_cheia()                 a janela em primeiro plano cobre o monitor inteiro
    janelas_visiveis(excluir, escala)   [(id, (l, t, r, b), maximizada)] de cima para baixo
    sem_foco_nativo(janela_id)   a janela do pet não rouba o foco (quando o sistema permite)
    iniciar_atalho(callback)     Ctrl+Alt+Shift+B; devolve True se registrou
    modo_sessao()                (Linux) 'x11', 'wayland', 'tty' ou 'desconhecido'
    avisos_sessao()              (Linux) limitações da sessão atual, para avisar uma vez
    canal_panic_sinal()          fd de leitura do sinal de pânico (SIGUSR1: pkill -USR1 <nome>)
"""

import sys

from ._comum import canal_panic_sinal      # noqa: F401  (POSIX: None onde não há SIGUSR1)

if sys.platform == "win32":
    from . import windows as _backend
elif sys.platform == "darwin":
    from . import macos as _backend
else:
    from . import linux as _backend

NOME_DO_SISTEMA = {"win32": "Windows", "darwin": "macOS"}.get(sys.platform, "Linux")

ocioso_segundos = _backend.ocioso_segundos
processo_ativo = _backend.processo_ativo
retangulo_ativo = _backend.retangulo_ativo
tela_cheia = _backend.tela_cheia
janelas_visiveis = _backend.janelas_visiveis
sem_foco_nativo = _backend.sem_foco_nativo
iniciar_atalho = _backend.iniciar_atalho

# Extras por sistema (Linux os tem; os outros ficam com uma resposta vazia/padrão):
modo_sessao = getattr(_backend, "modo_sessao", None)
avisos_sessao = getattr(_backend, "avisos_sessao", lambda: [])

__all__ = ["NOME_DO_SISTEMA", "ocioso_segundos", "processo_ativo", "retangulo_ativo", "tela_cheia",
           "janelas_visiveis", "sem_foco_nativo", "iniciar_atalho", "canal_panic_sinal",
           "modo_sessao", "avisos_sessao"]
