"""
SENSES - o computador como mundo sensorial.

Só olha: janela ativa, processo, tempo ocioso, tela cheia, o RETÂNGULO das janelas (para ele pousar)
e se há música tocando (MPRIS no D-Bus da sessão: só o estado do player, nunca conteúdo).
Como o sistema é lido fica em plataforma/; aqui fica só o que isso significa. Nunca lê conteúdo de janela.
"""

import math
import time

from .. import plataforma
from ..mathutil import clamp

# QtDBus pode faltar em instalações enxutas do PySide6: sem ele, MPRIS devolve False sempre.
try:
    from PySide6.QtDBus import QDBusMessage as _QDBusMessage
    MessageType = _QDBusMessage.MessageType
except Exception:                                    # pragma: no cover - só em ambientes sem QtDBus
    _QDBusMessage = None
    MessageType = None

# Nomes sem ".exe" e em minúsculo: vale para Windows, macOS e Linux (ver detect_activity)
ACTIVITY_APPS = {
    "PROGRAMMING": {"code", "visual studio code", "devenv", "pycharm64", "pycharm", "xcode",
                    "claude", "codex"},
    "DESIGNING": {"fusion360", "fusion"},
    "GAMING": {"valorant", "cs2", "csgo"},
    "BROWSING": {"chrome", "google chrome", "chromium", "firefox", "msedge", "microsoft edge", "opera",
                 "brave", "brave browser", "safari"},
    "SOCIAL": {"discord", "teams", "microsoft teams", "whatsapp"},
    "MUSIC": {"spotify", "apple music", "youtube music", "tidal", "deezer"},
}

# Jogadores de áudio: também valem MÚSICA quando o nome contém a palavra (qualquer player).
MUSIC_PALAVRAS = ("spotify", "music", "mpd", "vlc", "rhythmbox", "cmus", "audacious", "deadbeef",
                  "strawberry", "quodlibet", "exaile", "foobar", "winamp", "tidal", "deezer",
                  "podcast", "radio", "gpodder", "mpv")

# Qual canal sensorial cada atividade estimula
ACTIVITY_CHANNEL = {
    "PROGRAMMING": "WORK",
    "DESIGNING": "WORK",
    "GAMING": "PLAY",
    "MUSIC": "SOUND",
    "SOCIAL": "SOCIAL",
    "BROWSING": "WEB",
}





# ============================================================
# LEITURAS (cada uma delega para a plataforma atual)
# ============================================================


def get_idle_seconds():
    """Segundos desde o último teclado ou mouse (leitura da plataforma)."""
    return plataforma.ocioso_segundos()


def get_active_app():
    """Nome do programa em primeiro plano, em minúsculo (leitura da plataforma)."""
    return plataforma.processo_ativo()


def detect_activity(app, idle_seconds, away_after):
    """Classifica o momento: AWAY se ficou ocioso demais; senão, a atividade do programa (ou IDLE)."""
    if idle_seconds >= away_after:
        return "AWAY"
    nome = app.lower()
    if nome.endswith(".exe"):
        nome = nome[:-4]
    for activity, apps in ACTIVITY_APPS.items():
        if nome in apps:
            return activity
    if any(p in nome for p in MUSIC_PALAVRAS):     # player de qualquer família toca música
        return "MUSIC"
    return "IDLE"


def is_fullscreen():
    """Diz se a janela em primeiro plano ocupa a tela inteira (o pet não aparece nesse caso)."""
    return plataforma.tela_cheia()


# ============================================================
# MÚSICA PELO MPRIS (D-Bus da sessão)
# ============================================================
# O desktop público expõe o que está tocando em org.mpris.MediaPlayer2.*:
# rola pelo Chrome (Media Session), Firefox, VLC... Lê-se SÓ o PlaybackStatus
# do player ("Playing" ou não) — nenhum título, nada de conteúdo.


_mpris_nomes = {"nomes": [], "quando": 0.0}


from PySide6.QtDBus import QDBusMessage    # ver abaixo: enum de tipo de mensagem

MessageType = QDBusMessage.MessageType


def _mpris_pergunta(servico, caminho, interface, metodo, argumentos=()):
    """Uma chamada D-Bus de leitura (sem erro se o outro lado sumir)."""
    if _QDBusMessage is None:
        return None
    mensagem = _QDBusMessage.createMethodCall(servico, caminho, interface, metodo)
    if argumentos:
        mensagem.setArguments(list(argumentos))
    return mensagem


def _resposta_ok(mensagem):
    """True quando o D-Bus devolveu uma resposta normal (ReplyMessage), não erro."""
    return (mensagem is not None and MessageType is not None
            and mensagem.type() == MessageType.ReplyMessage)


def _mpris_players(conexao):
    """Serviços MPRIS ativos (org.mpris.MediaPlayer2.*), com lista cacheada por 10 s."""
    if time.monotonic() - _mpris_nomes["quando"] >= 10.0:
        pergunta = _mpris_pergunta("org.freedesktop.DBus", "/org/freedesktop/DBus",
                                   "org.freedesktop.DBus", "ListNames")
        if pergunta is None:
            _mpris_nomes["quando"] = time.monotonic()
            return []
        resposta = conexao.call(pergunta)
        nomes = resposta.arguments()[0] if _resposta_ok(resposta) else []
        _mpris_nomes["nomes"] = [n for n in nomes if str(n).startswith("org.mpris.MediaPlayer2.")]
        _mpris_nomes["quando"] = time.monotonic()
    return _mpris_nomes["nomes"]


def musica_tocando():
    """
    True se algum player MPRIS da sessão está com PlaybackStatus "Playing".
    Sem D-Bus (ou sem PySide6.QtDBus), devolve False e não atrapalha nada.
    """
    try:
        from PySide6.QtDBus import QDBusConnection
        conexao = QDBusConnection.sessionBus()
    except Exception:
        return False
    if conexao is None or not conexao.isConnected():
        return False
    for servico in _mpris_players(conexao):
        pergunta = _mpris_pergunta(str(servico), "/org/mpris/MediaPlayer2",
                                   "org.freedesktop.DBus.Properties", "Get",
                                   ("org.mpris.MediaPlayer2.Player", "PlaybackStatus"))
        resposta = conexao.call(pergunta)
        if _resposta_ok(resposta):
            valor = resposta.arguments()
            if valor:
                # Get devolve o valor embrulhado em QDBusVariant: desembrulhe antes de comparar
                bruto = valor[0]
                if hasattr(bruto, "variant"):
                    bruto = bruto.variant()
                if str(bruto) == "Playing":
                    return True
    return False


def list_windows(exclude, escala=1.0):
    """Janelas visíveis de cima para baixo: [(id, (l, t, r, b), maximizada)], em pixels físicos."""
    return plataforma.janelas_visiveis(exclude, escala)


def foreground_rect(escala=1.0):
    """Retângulo da janela ativa (pixels físicos), para ele olhar para ela."""
    return plataforma.retangulo_ativo(escala)


# ============================================================
# EVENTOS DO COMPUTADOR
# ============================================================


class ActivityTracker:
    """Detecta APP_CHANGED, ACTIVITY_CHANGED, USER_LEFT e USER_RETURNED."""

    def __init__(self):
        """Guarda o programa e a atividade anteriores, para perceber mudanças."""
        self.app = None
        self.activity = "IDLE"
        self.session_start = time.monotonic()

    def observe(self, app, activity):
        """Compara com o momento anterior e devolve os eventos: mudou de programa, de atividade, saiu ou voltou."""
        events = []
        if self.app is not None:
            if activity != self.activity:
                if activity == "AWAY":
                    events.append("USER_LEFT")
                elif self.activity == "AWAY":
                    events.append("USER_RETURNED")
                    self.session_start = time.monotonic()
                else:
                    events.append("ACTIVITY_CHANGED")
            if app != self.app and activity != "AWAY":
                events.append("APP_CHANGED")
        self.app = app
        self.activity = activity
        return events

    @property
    def session_seconds(self):
        """Quantos segundos a sessão atual já dura (desde que você voltou)."""
        return time.monotonic() - self.session_start


# ============================================================
# PONTE PC -> SISTEMA NERVOSO
# ============================================================


class ComputerSenses:
    """
    Traduz computador + interação com o pet em intensidades 0..1 por canal.
    Só descreve o que está acontecendo; não decide NADA sobre o que fazer.
    """

    PULSE_TAU = {"MOTION": 2.0, "NOVELTY": 3.0, "POKE": 1.5, "DISMISS": 6.0, "THROW": 2.0, "IMPACT": 4.0,
                 "TOY_TAKEN": 4.0}

    def __init__(self):
        """Estado dos sentidos: pulsos que decaem, níveis de atividade e se você está arrastando ou fazendo carinho."""
        self.pulse = {name: 0.0 for name in self.PULSE_TAU}
        self.level = {"WORK": 0.0, "PLAY": 0.0, "SOUND": 0.0, "SOCIAL": 0.0, "WEB": 0.0}
        self.typing = 0.0
        self.drag = 0.0
        self.dragging = False
        self.caress = 0.0
        self.last = time.monotonic()

    def kick(self, channel, amount):
        """Dá um pulso num canal sensorial (ele volta ao normal aos poucos)."""
        self.pulse[channel] = min(1.0, self.pulse[channel] + amount)

    def on_events(self, events):
        """Transforma eventos do computador em pulsos: trocar de programa mexe nele; voltar ao teclado é novidade."""
        for e in events:
            if e == "APP_CHANGED":
                self.kick("MOTION", 0.75)
            elif e in ("ACTIVITY_CHANGED", "USER_RETURNED"):
                self.kick("NOVELTY", 1.0)

    def poke(self):
        """Pulso de cutucada."""
        self.kick("POKE", 0.8)

    def set_dragging(self, dragging):
        """Marca se você está arrastando o pet agora."""
        self.dragging = dragging

    def dismissed(self):
        """Pulso de dispensa: você mandou uma travessura embora (vira frustração)."""
        self.kick("DISMISS", 0.7)

    def thrown(self, strength):
        """strength 0..1 (velocidade do arremesso)."""
        self.kick("THROW", 0.4 + 0.5 * strength)

    def impact(self, strength):
        """strength 0..1 (velocidade da batida); a irritação acumula entre batidas."""
        self.kick("IMPACT", 0.5 * strength)

    def update(self, activity, idle_seconds, drives, caressing=False, mouse_moving=False):
        """drives: canais internos da homeostase (BOREDOM, LONELY, FATIGUE)."""
        now = time.monotonic()
        dt = clamp(now - self.last, 0.0, 1.0)
        self.last = now

        for name, tau in self.PULSE_TAU.items():
            self.pulse[name] *= math.exp(-dt / tau)

        active = ACTIVITY_CHANNEL.get(activity)
        for name in self.level:
            target = 1.0 if name == active else 0.0
            self.level[name] += (target - self.level[name]) * (1.0 - math.exp(-dt / 3.0))

        # TYPING é teclado: input recente com o mouse parado (e nunca durante o carinho,
        # que é mexer o mouse). Antes, mexer o mouse contava como digitar.
        typing_now = 1.0 if idle_seconds < 0.3 and not mouse_moving and not caressing else 0.0
        self.typing += (typing_now - self.typing) * (1.0 - math.exp(-dt / 2.0))

        drag_now = 1.0 if self.dragging else 0.0
        self.drag += (drag_now - self.drag) * (1.0 - math.exp(-dt / 0.7))

        caress_now = 1.0 if caressing else 0.0
        self.caress += (caress_now - self.caress) * (1.0 - math.exp(-dt / 0.8))

        intensities = dict(self.level)
        intensities.update(self.pulse)
        intensities["TYPING"] = self.typing
        intensities["DRAG"] = self.drag
        intensities["CARESS"] = self.caress
        intensities["SILENCE"] = clamp((idle_seconds - 5.0) / 60.0)
        intensities.update(drives)
        return intensities
