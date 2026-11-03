"""Partes que os três sistemas compartilham: rodar comandos do sistema e o atalho global via pynput."""

import os
import signal
import subprocess
import time

import psutil

from ..log import log


def rodar(comando, tempo=1.0):
    """Saída do comando (texto) ou None se ele não existe, falhou ou demorou demais."""
    try:
        resultado = subprocess.run(comando, capture_output=True, text=True, timeout=tempo, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return resultado.stdout if resultado.returncode == 0 else None


_primeira_carga = [True]
_ultima_carga = [0.0, 0.0]      # (quando, percentual)


def carga_sistema():
    """
    0..1: quão pesada está a máquina agora (CPU daqui, nada do usuário nem de janelas).
    A primeira chamada só prepara a leitura do psutil; a partir daí são leituras de ~1 s.
    """
    if _primeira_carga[0]:
        _primeira_carga[0] = False
        try:
            psutil.cpu_percent(interval=None)
        except Exception:
            return 0.0
        return 0.0
    quando, _percento = _ultima_carga
    if time.monotonic() - quando < 0.9:      # leitura tem ~1 s de janela; reaproveita
        return clamp_carga(_percento)
    try:
        percentual = psutil.cpu_percent(interval=None)
    except Exception:
        return 0.0
    _ultima_carga[0] = time.monotonic()
    _ultima_carga[1] = percentual
    return clamp_carga(percentual)


def clamp_carga(percentual):
    """Percentual de CPU vira 0..1: pesada a partir de 70%."""
    if not isinstance(percentual, (int, float)) or percentual != percentual:
        return 0.0
    return max(0.0, min(1.0, (percentual - 70.0) / 25.0))


def atalho_pynput(callback):
    """Ctrl + Alt + Shift + B em qualquer lugar do sistema. Precisa de pynput instalado."""
    try:
        from pynput import keyboard
    except Exception:
        log("[pânico] pynput não está instalado: o atalho global fica desligado (o menu da bandeja funciona)")
        return False
    try:
        listener = keyboard.GlobalHotKeys({"<ctrl>+<alt>+<shift>+b": callback})
        listener.daemon = True
        listener.start()
    except Exception as error:
        log(f"[pânico] não deu para registrar o atalho: {error}")
        return False
    return True


def canal_panic_sinal(sinal=signal.SIGUSR1, _pipe=None):
    """
    POSIX: um canal para o atalho de pânico que não depende de ler o teclado (funciona em Wayland).
    O atalho do ambiente do usuário roda `pkill -USR1 <nome do programa>`; o sistema entrega o sinal,
    este handler escreve um byte num pipe e o app (QSocketNotifier, na thread do Qt) faz o pânico.
    Devolve o descritor de leitura, ou None se o sistema não tem SIGUSR1.
    """
    if not hasattr(signal, "SIGUSR1"):
        return None
    leitura, escrita = _pipe if _pipe else os.pipe()
    os.set_blocking(leitura, False)
    os.set_blocking(escrita, False)

    def _pelo_sinal(_sinal, _quadro):
        try:
            os.write(escrita, b"1")
        except OSError:
            pass                # o pipe cheio significa só que há mais de um pânico na fila

    try:
        signal.signal(sinal, _pelo_sinal)
    except (OSError, ValueError):
        return None
    return leitura
