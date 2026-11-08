"""
APP - a composição: liga os sentidos, o cérebro, o corpo e os controladores.

Relógios (todos na thread do Qt):
    16 ms   física, comportamento, travessuras e desenho
    100 ms  homeostase, cérebro, emoção, protesto, sono e aprendizado
    250 ms  janelas onde ele pode pousar
    500 ms  sensores do sistema (janela ativa, ocioso, tela cheia)
    30 s    salva cérebro, homeostase, memória e protesto

Este arquivo cria tudo e roda os três ciclos. O resto mora em mixins:
    controle/sessao.py      permissões, visibilidade, pausa, pânico, salvar, sair, apagar dados
    controle/interacao.py   cutucar, arrastar, arremessar, menus e notebook

Quem faz o quê:
    sense / think / frame   leitura, decisão e desenho, nessa ordem
    SleepController         dormir e acordar
    ProtestController       estágios e cartazes
    MischiefController      quando e como apronta; o que a dispensa causa
    FloatManager            painéis de teste
    SettingsStore           permissões e pânico
    PetState                o que ele sente e mostra (lido pela janela e pelo comportamento)
"""

import math
import os
import random
import time
from collections import deque

from PySide6.QtCore import QObject, QSocketNotifier, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QSystemTrayIcon

from . import config
from . import log as log_module
from . import migracao
from . import plataforma
from .ajustes import (
    ALCANCE_COMIDA as FOOD_REACH,
    ATIVIDADE_MINIMA_VOO as REFLEX_MIN_HZ,
    BATIDA_FORTE as HARD_IMPACT,
    BATIDA_TONTA as DIZZY_IMPACT,
    DURACAO_TONTURA as DIZZY_SECONDS,
    ENERGIA_COMIDA as FOOD_FILL,
    GASTO_TREINO as TREINO_BURNT,
    INTERVALO_BATIDA as IMPACT_COOLDOWN,
    LIMIAR_CANTO_HZ,
    PERTO_COMIDA as FOOD_NEAR,
    PUNICAO_DISPENSA as DISMISS_PENALTY,
    RECOMPENSA_CARINHO as CARESS_REWARD,
    RECOMPENSA_COMIDA as FOOD_REWARD,
    RECOMPENSA_PRESENTE,
    SILENCIO_MOUSE as MOUSE_QUIET,
    ENERGIA_CAFE,
    DURACAO_CAFEINA,
    ENERGIA_AGUA,
    DURACAO_ATENDE_AGUA,
    DIGITACAO_ATRASO,
    INTERVALO_BILHETE_DIGITANDO,
    JOGO_MEME_VIDA as VIDA_MEME_DE_JOGO,
    PENALTI_ALCANCE_GOL as GOL_ALCANCE,
    PENALTI_ALTURA_GOL as GOL_ALTURA,
    PENALTI_ALTURA_PULO as PULO_GOLEIRO,
    PENALTI_COLISAO as COLISAO_GOL,
    PENALTI_EMPURRAO as EMPURRAO_GOLEIRO,
    PENALTI_VIDA_JOGADA as VIDA_JOGADA,
)
from .body.behavior import Behavior
from .body.bolinha import Ball, load_sprite
from .body.brincadeira import Play
from .body.desenho_rosto import aparencia_de
from .body.pet import PetWindow, cursor_pos
from .body.pet_state import PetState
from .body.toy import ToyTracker, bounce_off, push_from_cursor
from .controle.interacao import InteracaoMixin
from .controle.sessao import SessaoMixin
from .core.conditioning import Conditioning
from .core.emotion import PRIORITY, EmotionState
from .core.episodic import EpisodicMemory
from .core.homeostasis import Drives
from .core.nervous_system import LIFBrain
from .core.protesto import Protesto
from .log import log
from .mind.castigo_ctl import CastigoController
from .mind.festa import FestaController
from .mind.jogo import JogoController
from .mind.lembretes import Lembretes
from .mind.mesa import MesaController, pull
from .mind.mischief_ctl import MischiefController
from .mind.protest_ctl import ProtestController
from .mind.revolucao import RevolucaoController
from .mind.sleep import SleepController
from .mind import sonho
from .mind.penalti import DEFESAS_CARTAZ, PenaltiController
from .paths import Paths
from .sense import senses
from .sense.timeline import TimelineRecorder
from .ui.float_manager import FloatManager
from .ui.ui import PanicHotkey, Tray
from .world.cartazes import SignThing
from .world.comida import Comida
from .world.mischief import MischiefEngine
from .world.presente import Presente

# Tandem de digitação só existe no clima tranquilo, fazendo companhia ao trabalho:
# bravo/triste/assustado/dramatico/dormindo (e o resto) nunca "digitam junto".
TANDEM_EMOCOES = ("feliz", "contente", "curioso", "observando")
TANDEM_ATIVIDADES = ("PROGRAMMING", "DESIGNING")

MAX_DT = 2.0          # s: um atraso maior que isso (suspensão) não vira tempo de rede

SAVE_EVERY_MS = 30_000


class PestinhaApp(SessaoMixin, InteracaoMixin, QObject):
    """Aplicativo do pet: junta a rede neural, os sentidos, o corpo, as travessuras e a interface. Um único objeto, criado em main.py."""
    def __init__(self, store, paths=None):
        """Monta tudo na ordem certa: primeiro a memória e o conteúdo do pet, depois a rede, os sentidos, o corpo, a bandeja e os relógios."""
        super().__init__()
        self.store = store
        self.perms = store.perms
        self.paths = paths or Paths()
        log_module.setup(self.paths.log)
        self.prof = config.profile(self.perms)
        self.debugging = lambda: self.perms["modo_teste"]

        # ----- qual pet, e onde fica a memória dele -----
        pet_id = config.escolher_pet(self.paths, self.perms["pet"])     # só um pets/<id>.json vira personagem
        migracao_feita = migracao.migrar(self.paths, pet_id)
        if migracao_feita.pet_ok(pet_id):
            self.pet_paths = self.paths.pet(pet_id)
            self.aviso_migracao = None
        else:
            # pendência na migração: usa os arquivos antigos, como antes, e avisa (nada é perdido)
            self.pet_paths = self.paths.pet_legado(pet_id)
            self.aviso_migracao = ("A memória ainda está no formato antigo (migração pendente: "
                                   f"{migracao_feita.resumo()}). Nada foi apagado; veja memory/logs.")
            log(f"[migração] {pet_id} em modo compatível: {migracao_feita.resumo()}")

        # ----- cérebro e estado interno -----
        pet_def = config.load_pet(self.paths, pet_id)
        self.conteudo = self.paths.conteudo(pet_id)   # frases, cartazes e imagens deste pet
        self.nome = pet_def["nome"]                   # quem fala nos textos; o programa é config.APP_NOME
        self.reacao_notebook = pet_def["reacao_notebook"]     # "bravo" ou "triste": depende do pet
        self.brain = LIFBrain(seed=pet_def["seed"], temperament=pet_def.get("temperamento"))
        self.state_file = self.pet_paths.nervous
        self.brain.load(str(self.state_file))
        self.intensities = {}       # última entrada da rede (para o monitor)
        self.pulso_recusa = 0.0     # 1 quando ele recusou um pedido (vira RECUSA na rede)
        self.drives = Drives()
        self.drives.load(self.pet_paths.drives, self.prof)
        self.memory = EpisodicMemory(self.pet_paths.episodes, self.pet_paths.preferences)
        self.memory.load()
        self.emotion = EmotionState()
        self.pet_state = PetState()
        self.conditioning = Conditioning(self.pet_paths.conditioning, self.prof["cond_rate"])
        self.conditioning.load()
        self.prev_pet_dist = None
        self.protest = Protesto(self.conteudo.signs, self.pet_paths.protest)
        self.protest.load(self.prof)

        # ----- sentidos -----
        self.senses = senses.ComputerSenses()
        self.tracker = senses.ActivityTracker()
        self.activity = "IDLE"
        self.idle_seconds = 0.0
        self.fullscreen = False
        self.platforms = []
        self.keyboard_active = False
        self.last_cursor = (0, 0)
        self.mouse_moved_at = 0.0
        self.timeline = TimelineRecorder(self.paths.timeline, lambda: self.perms["rotina"])
        self.carga = 0.0                                  # 0..1: quão pesada está a máquina (HEAT)
        self._trocas_janelas = deque(maxlen=16)           # APP_CHANGED dos últimos segundos (tempestade)
        self._tempestade_ate = 0.0
        self._proximo_sonho = time.monotonic() + random.uniform(180.0, 420.0)

        # ----- corpo e travessuras -----
        left, top, right, _bottom = self.bounds()
        self.pet = PetWindow(right - 220, top + 120, self.pet_state)
        for pantalla, screen in enumerate(QGuiApplication.screens()):
            g = screen.availableGeometry()
            log(f"[tela] monitor {pantalla}: ({g.x()}, {g.y()}) a ({g.x() + g.width()}, "
                f"{g.y() + g.height()}) — dpr {screen.devicePixelRatio()}")
        self.pet.aparencia = aparencia_de(pet_def.get("aparencia"))
        self.pet.poked.connect(self.on_poke)
        self.pet.drag_started.connect(self.on_drag_started)
        self.pet.drag_ended.connect(lambda: self.senses.set_dragging(False))
        self.pet.thrown.connect(self.on_thrown)
        self.pet.menu_requested.connect(self.show_pet_menu)
        self.pet.shaken.connect(self.on_shaken)
        self.pet.kissed.connect(self.on_kiss)
        self.ball_stored = False    # você guardou a bolinha pelo menu
        self._comida_na_tela = False
        self._premio_comida = 0.0   # recompensa pendente: ele acabou de comer (vai no learn do think)
        self._premio_extra = 0.0    # recompensa pendente de beijo/balanço/presente (vai no learn)
        self._comida_elevada_em = 0.0
        self.comida = Comida(left + 560, self.bounds()[3] - 40, sprite=load_sprite(self.conteudo.biscoito))
        self._presente_na_tela = False
        self._presente_elevado_em = 0.0
        self.presente = Presente(left + 560, self.bounds()[3] - 40,
                                 sprite=load_sprite(self.conteudo.presente))
        self._digita_desde = None   # você digitando desde quando (tandem de digitação)
        self._digita_bilhete_em = 0.0
        self.mischief = MischiefEngine(self.conteudo)
        self.mischief.dismissed.connect(self.on_dismissed)
        self.behavior = Behavior(self.pet.body, self.pet_state, self.mischief)

        # ----- controladores -----
        self.sleep = SleepController(self.emotion, self.drives, self.memory, self.debugging,
                                     self._sonho_ao_acordar)
        self.protest_ctl = ProtestController(self.protest, self.pet.body, self.behavior,
                                             self.senses, self.drives, self.pet_state, self.debugging)
        self.sad = Protesto(self.conteudo.signs, self.pet_paths.sad_protest, kind="tristeza")
        self.sad.load(self.prof)
        self.sad_ctl = ProtestController(self.sad, self.pet.body, self.behavior,
                                         self.senses, self.drives, self.pet_state, self.debugging)
        self.ball = Ball(left + 400, self.bounds()[3] - 40, sprite=load_sprite(self.conteudo.bolinha_tenis))
        self.play_weights = pet_def.get("brincadeira", None)
        self.behavior.ball = self.ball
        self.behavior.play = Play(self.play_weights)
        self.toy_tracker = ToyTracker()
        self.cursor_vel = (0.0, 0.0)
        self._prev_cursor = None
        self._prev_cursor_t = 0.0
        self.last_cursor_push = -1e9
        self.mischief_ctl = MischiefController(self.mischief, self.memory, self.drives, self.senses,
                                               self.behavior, self.emotion, self.debugging)
        self.floats = FloatManager(self)
        self.mischief_ctl.postit_weight = Play(self.play_weights).weight("postit")
        self.festa = FestaController(self.debugging)
        self.mesa = MesaController(self.debugging, self)
        self.lembretes = Lembretes(self.paths.lembretes)
        self._lembrete_alerta = None
        self.penalti = PenaltiController(self.paths.penalti)
        self.jogo = JogoController(self.debugging)
        self.castigo = CastigoController(self, self.debugging)
        paper = load_sprite(self.conteudo.bolinha_papel)
        self.revolucao = RevolucaoController(self.behavior.play, self.debugging, sprite=paper)

        # ----- reflexos e medições -----
        self.in_flight = False      # voando depois de um arremesso
        self.last_impact = 0.0
        self.last_poke = 0.0
        self.poke_probe = None      # (quando medir, CHEER antes da cutucada)
        self.last_poke_response = None

        # ----- interface -----
        self.settings = None
        self.tray = Tray(self.nome)
        self.tray.open_settings.connect(self.open_settings)
        self.tray.open_monitor.connect(lambda: self.floats.open("neural"))
        self.tray.open_panel.connect(lambda: self.floats.open("greve"))
        self.tray.toggle_floating.connect(self.toggle_floating)
        self.tray.toggle_pause.connect(self.toggle_pause)
        self.tray.toggle_hidden.connect(self.toggle_hidden)
        self.tray.clear_things.connect(self.clear_things)
        self.tray.panic.connect(self.panic)
        self.tray.quit.connect(self.quit)
        self.hotkey = PanicHotkey()
        self.hotkey.pressed.connect(self.panic)
        self._ligar_panic_sinal()
        self.wiping = False         # True depois de "apagar tudo": não grava mais nada ao sair
        self.paused = False
        self._pausado_em = None         # quando a pausa começou (para descontar do tempo dos episódios)
        self._ultimo_think = None       # quando a rede foi integrada pela última vez
        self.hidden = False

        # ----- relógios -----
        self.last_frame = time.monotonic()
        self._timer(16, self.frame)
        self._timer(100, self.think)
        self._timer(250, self.scan_windows)
        self._timer(500, self.sense)
        self._timer(SAVE_EVERY_MS, self.save)

        self._apply_settings()
        self.sense()
        self.scan_windows()
        problems = config.check_assets(self.conteudo)
        for text in problems:
            log(f"[assets] {text}")
        if self.aviso_migracao:
            problems.append(self.aviso_migracao)
        if not self.hotkey.ok:
            problems.append(f"atalho de pânico {config.PANIC_HOTKEY_TEXT} já está em uso por outro programa")
        avisos = plataforma.avisos_sessao()
        for aviso in avisos:
            log(f"[sessão] {aviso}")
        problems.extend(avisos)
        log(f"[sessão] plataforma do Qt: {QGuiApplication.platformName()} "
            f"(sistema: {plataforma.NOME_DO_SISTEMA})")
        if problems:
            self.tray.icon.showMessage(config.APP_NOME,"\n".join(problems), QSystemTrayIcon.Warning, 6000)
        if self.perms["ativo"]:
            self.tray.icon.showMessage(
                self.nome, f"Estou aqui. Pânico: {config.PANIC_HOTKEY_TEXT}",
                QSystemTrayIcon.Information, 3000,
            )

    def _timer(self, ms, slot):
        """Cria um relógio que chama `slot` a cada `ms` milissegundos."""
        timer = QTimer(self)
        timer.timeout.connect(slot)
        timer.start(ms)
        return timer

    def _ligar_panic_sinal(self):
        """
        Segunda via do atalho de pânico: um sinal no processo (POSIX, funciona até em Wayland).
        O canal do sistema devolve um fd; o QSocketNotifier vigia o fd na thread do Qt e cada byte
        lido vira um pânico.
        """
        fd = plataforma.canal_panic_sinal()
        if fd is None:
            return
        notify = QSocketNotifier(fd, QSocketNotifier.Type.Read, self)
        notify.activated.connect(self._panic_pelo_sinal)
        self._panic_sinal_fd = fd

    def _panic_pelo_sinal(self):
        """Um byte chegou pelo canal do sinal: drena o pipe e faz o pânico."""
        try:
            while os.read(self._panic_sinal_fd, 4096):
                pass
        except OSError:
            pass
        self.panic()

    @property
    def asleep(self):
        """Diz se o pet está dormindo."""
        return self.sleep.asleep

    # ---------------- geometria ----------------

    def screen_bounds(self):
        """Áreas úteis de todos os monitores, em coordenadas lógicas globais do Qt."""
        return [(g.x(), g.y(), g.x() + g.width(), g.y() + g.height())
                for g in (screen.availableGeometry() for screen in QGuiApplication.screens())]

    def screen_geometries(self):
        """Geometria física das telas, na mesma ordem de screen_bounds()."""
        return [(g.x(), g.y(), g.x() + g.width(), g.y() + g.height())
                for g in (screen.geometry() for screen in QGuiApplication.screens())]

    def _bounds_at(self, areas, x, y):
        """Área útil do monitor que contém o ponto, inclusive sobre barras reservadas pelo sistema."""
        if x is not None:
            encontrada = next((a for a in areas if a[0] <= x < a[2] and a[1] <= y < a[3]), None)
            if encontrada is not None:
                return encontrada
            for area, geometria in zip(areas, self.screen_geometries()):
                if geometria[0] <= x < geometria[2] and geometria[1] <= y < geometria[3]:
                    return area
        g = QGuiApplication.primaryScreen().availableGeometry()
        return g.x(), g.y(), g.x() + g.width(), g.y() + g.height()

    def bounds(self):
        """Área útil do monitor onde está o pet; usa a tela principal antes de ele ser criado."""
        if hasattr(self, "pet"):
            return self._bounds_at(self.screen_bounds(), self.pet.body.x, self.pet.body.y)
        g = QGuiApplication.primaryScreen().availableGeometry()
        return g.x(), g.y(), g.x() + g.width(), g.y() + g.height()

    def scan_windows(self):
        """Barras de título onde ele pode pousar, em coordenadas lógicas do Qt."""
        if not self.perms["pousar_janelas"] or not self.pet.isVisible():
            self.platforms = []
            return
        screen = QGuiApplication.primaryScreen()
        dpr = screen.devicePixelRatio()
        g = screen.geometry()
        exclude = {int(self.pet.winId())} | {int(t.winId()) for t in self.mischief.things}
        exclude |= self.floats.visible_handles()
        exclude |= {int(w.winId()) for w in self.revolucao.janelas()}
        exclude |= {int(w.winId()) for w in self.protest_ctl.sign_windows()}
        exclude |= {int(w.winId()) for w in self.sad_ctl.sign_windows()}
        if self.ball.isVisible():
            exclude.add(int(self.ball.winId()))
        above = []
        platforms = []
        for hwnd, (l, t, r, b), maximized in senses.list_windows(exclude, dpr):
            l, t, r, b = l / dpr, t / dpr, r / dpr, b / dpr
            mid = (l + r) / 2
            covered = any(al <= mid <= ar and at <= t + 2 <= ab for al, at, ar, ab in above)
            above.append((l, t, r, b))
            if maximized or covered:
                continue
            if not (g.left() <= mid <= g.right() and g.top() + 40 <= t <= g.bottom() - 100):
                continue
            platforms.append((hwnd, l + 10, r - 10, t))
        self.platforms = platforms

    # ---------------- relógios ----------------

    def sense(self):
        """Leitura de 500 em 500 ms: programa em primeiro plano, ocioso, janelas e tela cheia."""
        if self._congelado():
            return
        self.idle_seconds = senses.get_idle_seconds()
        app = senses.get_active_app()
        self.carga = plataforma.carga_sistema()
        self.toca_musica = senses.musica_tocando()        # MPRIS da sessão: vale qualquer player
        if self.toca_musica != getattr(self, "_tocava_musica", self.toca_musica):
            self._tocava_musica = self.toca_musica
            log(f"[música] MPRIS: {'tocando' if self.toca_musica else 'parou'}")
        self.activity = senses.detect_activity(app, self.idle_seconds, self.prof["away_after"],
                                               jogos=self.perms.get("jogos"))
        if self.activity != "GAMING" and self.activity != "AWAY" \
                and senses.jogo_rodando(self.perms.get("jogos")):
            self.activity = "GAMING"        # Wayland: a janela não se lê, mas o jogo está rodando
        events = self.tracker.observe(app, self.activity)
        self.senses.on_events(events)
        self._tempestade(events)
        for event in events:
            if event == "APP_CHANGED":
                self.drives.stimulate("app")
            elif event in ("ACTIVITY_CHANGED", "USER_RETURNED"):
                self.drives.stimulate("novelty")
        if self.perms["rotina"]:
            self.timeline.observe(
                self.activity, self.idle_seconds, events, self.tracker.session_seconds, self.keyboard_active
            )
        if "APP_CHANGED" in events:
            dpr = QGuiApplication.primaryScreen().devicePixelRatio()
            rect = senses.foreground_rect(dpr)
            if rect:
                self.behavior.look_at((rect[0] + rect[2]) / 2 / dpr, (rect[1] + rect[3]) / 2 / dpr,
                                      time.monotonic())
        fullscreen = senses.is_fullscreen()
        if fullscreen != self.fullscreen:
            ficou_cheia = fullscreen and not self.fullscreen
            self.fullscreen = fullscreen
            if ficou_cheia and not self.asleep and not self.castigo.dentro:
                # susto do cinema: algo ocupou a tela de pegar a tela (o pulo vem da emoção assustado)
                self.emotion.force("assustado", 1.2, time.monotonic(), PRIORITY["assustado"])
            self.update_visibility()

    def _tempestade(self, events):
        """
        Trocas frenéticas de janela (Alt+Tab storm): muitas trocas em pouco tempo viram
        uma crise curta - fica dramático e meio tonto. Guarda ~3 minutos de silêncio entre crises.
        """
        if "APP_CHANGED" not in events:
            return
        agora = time.monotonic()
        self._trocas_janelas.append(agora)
        trocas = [t for t in self._trocas_janelas if agora - t < 45.0]
        self._trocas_janelas.clear()
        self._trocas_janelas.extend(trocas)
        if len(trocas) < 8 or agora < self._tempestade_ate:
            return
        self._tempestade_ate = agora + 180.0
        self.senses.kick("MOTION", 1.0)
        self.senses.kick("NOVELTY", 1.0)
        self.pet_state.dizzy_until = max(self.pet_state.dizzy_until, agora + 1.2)
        if self.emotion.force("dramatico", 2.5, agora, PRIORITY["dramatico"]):
            self.drives.stimulate("app")

    def think(self):
        """Passo da rede (100 ms): recebe os sentidos, decide o motor vencedor e aplica no comportamento."""
        if self._congelado():
            return
        now = time.monotonic()
        dt = min(MAX_DT, max(0.0, now - self._ultimo_think)) if self._ultimo_think is not None else 0.1
        self._ultimo_think = now
        st = self.pet_state
        body = self.pet.body
        caressing = self.perms["carinho"] and self.pet.isVisible() and st.caressing(now)

        # teclado x mouse: o sistema só dá "último input"; separamos olhando se o cursor andou
        idle = senses.get_idle_seconds()
        idle_ok = senses.idle_confiavel()
        cursor = cursor_pos()
        if abs(cursor[0] - self.last_cursor[0]) + abs(cursor[1] - self.last_cursor[1]) > 2:
            self.mouse_moved_at = now
        self.last_cursor = cursor
        mouse_moving = now - self.mouse_moved_at < MOUSE_QUIET
        self.keyboard_active = idle < 0.3 and not mouse_moving and not caressing

        moving = min(1.0, abs(body.vx) / 200.0 + (0.0 if body.grounded else 1.0))
        self.drives.update(dt, self.prof, self.asleep, moving, self.emotion.arousal,
                           self.activity == "AWAY", engaged=self.activity in ("PROGRAMMING", "DESIGNING"),
                           preso=self.castigo.dentro, visitado=self.castigo.visita > 0.5)
        if self.behavior.treino is not None:      # malhação: os pulinhos gastam energia
            self.drives.energy = max(0.0, self.drives.energy - dt * TREINO_BURNT)
        self.castigo.tick_lento(dt)
        if caressing:
            self.drives.stimulate("caress", dt)
            self.drives.touched("caress", dt)
            self.memory.on_interaction()

        intensities = self.senses.update(self.activity, idle, self.drives.channels(), caressing,
                                         mouse_moving, idle_confiavel=idle_ok)
        # condicionamento: o cursor vindo rápido para ele, ou o botão apertado em cima, antecipam
        dist = math.hypot(cursor[0] - body.x, cursor[1] - body.y)
        approaching = (self.prev_pet_dist is not None and dist < 220
                       and dt > 0 and (self.prev_pet_dist - dist) / dt > 500)
        self.prev_pet_dist = dist
        self.conditioning.set_cue("PRESS", st.pressing, now)
        self.conditioning.set_cue("APPROACH", approaching, now)
        self.conditioning.set_cue("PLACA", self.castigo.perto_da_placa(body), now)
        self.conditioning.tick(now)
        intensities["ANTICIPATE"] = self.conditioning.strength()                     # cutucada, arraste
        intensities["ANTECIPA_PLACA"] = self.conditioning.strength(cues=("PLACA",))  # ir para o canto
        # bolinha: perto dele brinca; se você levou para longe, ele sente
        ball_xy = (self.ball.body.x, self.ball.body.y)
        taken, near = self.toy_tracker.update(ball_xy, (body.x, body.y), self.ball.handled_by_user(now))
        if taken and self.perms["bolinha"] and not self.ball_stored:
            self.senses.kick("TOY_TAKEN", 0.9)
        intensities["TOY_NEAR"] = near if self.perms["bolinha"] and not self.ball_stored else 0.0
        # comida: o biscoito por perto entra na rede como FOOD (ele chega, come, enche energia).
        # Vale na mão, valendo de janela/placa/sono: encostar o biscoito na boca dele é a mordida.
        if self._comida_na_tela and self.perms["comida"]:
            distancia = math.hypot(self.comida.body.x - body.x, self.comida.body.y - body.y)
            intensities["FOOD"] = max(0.0, min(1.0, 1.0 - distancia / FOOD_NEAR))
            na_mao = self.comida.dragging
            solto_ha_pouco = not self.comida.handled_by_user(now)
            if distancia < FOOD_REACH and (na_mao or solto_ha_pouco):
                self._comer(self.comida.tipo, now)
        else:
            intensities["FOOD"] = 0.0
        self.behavior.comida = ((self.comida.body.x, self.comida.body.y)
                                if self._comida_na_tela and self.perms["comida"] else None)
        # presente: a caixinha-surpresa perto dele abre (o resultado é sorteado)
        if self._presente_na_tela and self.perms["presente"]:
            distancia_p = math.hypot(self.presente.body.x - body.x, self.presente.body.y - body.y)
            na_mao_p = self.presente.dragging
            if distancia_p < FOOD_REACH and (na_mao_p or not self.presente.handled_by_user(now)):
                self._abrir_presente(now)
        self.behavior.presente = ((self.presente.body.x, self.presente.body.y)
                                  if self._presente_na_tela and self.perms["presente"] else None)
        # sinais de estado: o pedido seu, o cantinho, a memória de fugas e a recusa
        intensities["PEDIDO"] = self.mesa.intensidade_pedido(now)
        intensities.update(self.castigo.sinais(body))  # preso, memória de fuga, placa, visita, receio, rancor
        intensities["RECUSA"] = self.pulso_recusa
        self.pulso_recusa = 0.0
        intensities["HEAT"] = self.carga          # 0..1 de acordo com a carga da máquina
        # música: o que toca (nome do app) OU o MPRIS da sessão entra como SOUND na rede.
        # O estímulo vem ANTES da integração, então a influência passa pelo cérebro de verdade.
        if self.toca_musica:
            intensities["SOUND"] = max(intensities.get("SOUND", 0.0), 0.85)
            self.senses.level["SOUND"] = max(self.senses.level["SOUND"], 0.85)
        self._atualiza_tandem(now, intensities["TYPING"])   # digitação em tandem
        total_ms = max(1, round(dt * 1000))
        while total_ms > 0:
            chunk = min(100, total_ms)
            self.brain.stimulate(intensities)
            self.brain.step(chunk)
            total_ms -= chunk
        self.intensities = intensities
        self.behavior.groove = 0.0 if self.asleep else self.senses.level["SOUND"]   # música: vira dança
        self.pet_state.groove = self.behavior.groove                       # o rosto desenha notas e fone
        self.behavior.energy = self.drives.energy
        motor = self.brain.motor_activity()
        st.tone.update(motor, dt)

        change = self.protest_ctl.tick(dt, st.tone, self.prof, caressing, now)
        if change:
            self.protest_ctl.on_stage(*change)
        sad_change = self.sad_ctl.tick(dt, st.tone, self.prof, caressing, now,
                                       self.drives.channels()["LONELY"])
        if sad_change:
            self.sad_ctl.on_stage(*sad_change)
        if self.asleep:
            st.protest_stage = 0
        elif self.protest.stage:
            st.protest_stage = self.protest.stage
        else:
            st.protest_stage = 3 if self.sad.stage >= 2 else 0     # abandonado: fica sentado, quieto
        if self.poke_probe and now >= self.poke_probe[0]:
            self.poke_reflex(motor["CHEER"] - self.poke_probe[1])

        reward = 0.0
        if self.perms["carinho"] and not self.protest.stage:     # em protesto, carinho acalma mas não ensina
            if caressing:
                reward += CARESS_REWARD
            if self.mischief_ctl.penalty_active(now):
                reward += DISMISS_PENALTY
        reward += self.castigo.punicao(now)          # ser preso é recompensa negativa: o castigo ensina
        reward += self._premio_comida                # a comida devolve recompensa (aprende a querer)
        reward += self._premio_extra                 # beijo do dia, gargalhada e festinha do presente
        self._premio_comida = 0.0
        self._premio_extra = 0.0
        self.brain.learn(reward, dt, self.prof["learn_rate"])

        if self.in_flight:
            if body.grounded:
                self.in_flight = False
            else:
                # reflexo no ar: o que estiver mais ativo na rede agora decide a cara
                rates = self.brain.pool_rates()
                reflex, hz = max(
                    (("feliz", rates["PLAYFUL"]), ("assustado", rates["ALERT"]), ("bravo", rates["FRUSTRATION"])),
                    key=lambda item: item[1],
                )
                if hz < REFLEX_MIN_HZ:
                    reflex = "feliz"        # rede ainda quieta: voar é divertido
                self.emotion.force(reflex, 0.3, now, PRIORITY["voo"])
        if caressing:
            self.emotion.force("contente", 0.5, now, PRIORITY["carinho"])     # fecha os olhinhos na hora
            self.timeline.note_interaction(dt)

        self.sleep.tick(now, body, self.in_flight, self.protest.stage, self.behavior.mission)
        self._sonhos(now)
        self._lembrete_tick(now)
        self._tick_do_jogo(now)

        emotion = self.emotion.update(motor, dt, self.prof)
        if self.protest.stage >= 2 and not self.asleep:
            self.emotion.force("bravo", 0.3, now, PRIORITY["protesto"])     # cara de raiva na manifestação
            emotion = self.emotion.update(motor, 0.0, self.prof)
        elif self.sad.stage >= 2 and not self.asleep:
            self.emotion.force("triste", 0.3, now, PRIORITY["protesto"])    # abandonado: cara triste
            emotion = self.emotion.update(motor, 0.0, self.prof)
        self.timeline.note_emotion(emotion, dt)
        self.festa.tick(now, motor, emotion, self.pet.body, self._pode_soltar_fogo(), dt)
        self._atualizar_mesa(now)
        self.memory.tick(now, self.prof["episode_ok"], self.prof["episode_window"])
        st.emotion = emotion
        self.behavior.on_emotion(emotion, time.monotonic())

    def _comer(self, tipo, agora):
        """Ele alcançou a comida: some com ela, aplica o efeito do tipo, acorda se estava dormindo e aprende."""
        self._comida_na_tela = False
        self.update_visibility()                     # a comida some AGORA (nada fica pendurado)
        self._premio_comida = FOOD_REWARD
        self.pet_state.comer_para = agora + 0.8      # migalhas de mordida visíveis
        if self.asleep:
            self.sleep.wake(startled=False)
        self.memory.on_interaction()
        if tipo == "cafe":
            self.drives.energy = min(1.0, self.drives.energy + ENERGIA_CAFE)
            self.pet_state.cafeina_ate = agora + DURACAO_CAFEINA
            log(f"[comida] café({tipo}): energia {self.drives.energy:.2f} "
                f"(cafeína por {DURACAO_CAFEINA:.0f} s)")
        elif tipo == "agua":
            self.drives.energy = min(1.0, self.drives.energy + ENERGIA_AGUA)
            self.pet_state.dizzy_until = 0.0         # a água assenta: tira a tontura
            self.emotion.force("contente", DURACAO_ATENDE_AGUA, agora, PRIORITY["carinho"])
            log(f"[comida] água({tipo}): assentado, energia {self.drives.energy:.2f}")
        else:
            self.drives.energy = min(1.0, self.drives.energy + FOOD_FILL)
            self.pet_state.feliz_ate = agora + 2.5
            self.emotion.force("feliz", 2.0, agora, PRIORITY["carinho"])
            if self.pet.body.grounded:
                self.pet.body.jump(0.0, -350.0)      # pulinho de alegria
            log(f"[comida] biscoito({tipo}): energia {self.drives.energy:.2f}")

    def _abrir_presente(self, agora):
        """Ele abriu o presente: a surpresa é sorteada — festa, bilhete engraçado ou cara triste."""
        if self.asleep:
            self.sleep.wake(startled=False)
        self._presente_na_tela = False
        self.update_visibility()                     # a caixinha some AGORA
        self.memory.on_interaction()
        self.pet_state.comer_para = agora + 0.8      # o mesmo efeito de migalhas: o "papel picado"
        tiro = random.random()
        if tiro < 0.35:                              # festa: pulinho, energia e recompensa
            self._premio_extra += RECOMPENSA_PRESENTE
            self.pet_state.feliz_ate = agora + 3.0
            self.emotion.force("feliz", 2.0, agora, PRIORITY["carinho"])
            if self.pet.body.grounded:
                self.pet.body.jump(0.0, -400.0)
            log("[presente] abriu: era uma festa")
        elif tiro < 0.7:                             # bilhete: um recadinho engraçado
            if self._soltar_bilhete():
                log("[presente] abriu: veio um bilhete")
        else:                                        # pedra dentro da caixa: cara triste por um pouco
            self.emotion.force("triste", 2.5, agora, PRIORITY["protesto"])
            log("[presente] abriu: era uma pedra (cara triste)")

    def _atualiza_tandem(self, agora, digitando):
        """Você digitando há um tempo seguido: ele fica "digitando junto" e, de vez em quando, cola um bilhete engraçado."""
        st = self.pet_state
        # o tandem é uma mímica de você digitando — só existe quando você de fato
        # está digitando num app de trabalho, com medição real de idle, e ele está num
        # estado em que imitar faz sentido (não dormindo, bravo, de castigo ou escondido)
        if (digitando < 0.55 or self.pet.body.held
                or not senses.idle_confiavel()
                or self.activity not in TANDEM_ATIVIDADES
                or self.behavior.emotion not in TANDEM_EMOCOES
                or self.asleep or st.protest_stage or st.castigo or st.quieto(agora)):
            self._digita_desde = None
            return
        if self._digita_desde is None:
            self._digita_desde = agora
            return
        if agora - self._digita_desde >= DIGITACAO_ATRASO:
            st.digitar_para = agora + 1.0            # a janela refresca enquanto você digita
            if agora - self._digita_bilhete_em >= INTERVALO_BILHETE_DIGITANDO and self._soltar_bilhete():
                self._digita_bilhete_em = agora      # só conta quando a entrega partiu de fato
                log("[digitação] bilhete engraçado do tandem")

    def _sonhos(self, now):
        """Dormindo, ele sonha de vez em quando: um mini meme num balãozinho acima da cabecinha."""
        st = self.pet_state
        if st.dream_path and now > st.dream_ate:
            st.dream_path = None
            st.dream_ate = 0.0
            st.dream_de = 0.0
        if not self.asleep or now < self._proximo_sonho:
            return
        self._proximo_sonho = now + random.uniform(150.0, 420.0)
        path = config.meme_for(self.conteudo.memes, random.choice(config.EMOTIONS))
        if path:
            st.dream_path = str(path)
            st.dream_de = now
            st.dream_ate = now + 8.0

    def _soltar_bilhete(self):
        """Bilhete (recadinho) no padrão das travessuras: ele pega, carrega pela tela e cola.

        Falso quando o recado não pode sair (permissão, sem conteúdo) ou quando o corpo
        não consegue pegar agora (no ar, ocupado, em missão) — aí nada é gasto.
        """
        if not (self.perms["travessuras"] and self.perms["bilhetes"]):
            return False
        body = self.pet.body
        if body.held or not body.grounded or self.behavior.mission is not None:
            return False
        plan = self.mischief.plan("bilhete", self.pet_state.emotion)
        if plan is None:
            return False
        self.behavior.start_mission(plan, self.bounds(), cursor_pos(), time.monotonic())
        return True

    def _entregar_recado(self, texto):
        """Recado escrito por nós (sonho, lembrete): o pet pega, carrega e cola.

        Falso se o texto é vazio ou o corpo não consegue pegar agora (no ar,
        ocupado, em missão) — aí nada é entregue e nada é gasto.
        """
        if self.pet.body.held or not self.pet.body.grounded or self.behavior.mission is not None:
            return False
        plan = self.mischief.plan_texto(texto)
        if plan is None:
            return False
        self.behavior.start_mission(plan, self.bounds(), cursor_pos(), time.monotonic())
        return True

    def _sonho_ao_acordar(self, startled=False):
        """Ao acordar descansado, conta um sonho costurado com o que aconteceu de verdade.

        Susto não é hora de conversar; sem episódios de memória, o sonho fica vazio
        e o pet fica quieto. A chance vem do ajuste (SONHO_CHANCE).
        """
        if startled:
            return
        texto = sonho.contar(self.memory)
        if texto and self._entregar_recado(texto):
            log("[sonho] contou o sonho ao acordar")

    def _lembrete_tick(self, agora):
        """Recado venceu: cutuca três vezes (espaçadas) e cola o bilhete pelo padrão."""
        if self._lembrete_alerta is None:
            vencido = self.lembretes.vencer()
            if vencido is None:
                return
            self._lembrete_alerta = [agora, 0, vencido]     # [próximo passo, cutucadas feitas, texto]
            return
        inicio, feitas, texto = self._lembrete_alerta
        if agora - inicio < 0.55:
            return
        self._lembrete_alerta[0] = agora
        feitas += 1
        self._lembrete_alerta[1] = feitas
        if feitas <= 3:
            self.menu_poke()                                # cutucada pedindo atenção
            return
        self._lembrete_alerta = None
        if self._entregar_recado(texto):
            log("[lembretes] entregou o recado na hora")

    def _tick_do_jogo(self, agora):
        """Modo jogo: um jogo da lista em primeiro plano e ele pega o controle para acompanhar."""
        mouse_moving = agora - self.mouse_moved_at < MOUSE_QUIET
        input_ativo = mouse_moving or (senses.idle_confiavel() and self.idle_seconds < 0.5)
        eventos = self.jogo.tick(
            agora,
            jogando=self.activity == "GAMING",
            input_ativo=input_ativo,
            afk_segundos=self.idle_seconds if senses.idle_confiavel() else 0.0,
            livre=not (self.asleep or self.pet.body.held or self.behavior.mission is not None
                       or self.in_flight or self.castigo.dentro or self.pet_state.quieto(agora)
                       or self.hidden),
        )
        if eventos:
            self._aplicar_jogo(eventos, agora)

    def _aplicar_jogo(self, eventos, agora):
        """Os eventos do modo jogo viram cara e corpo: festa, controle, reação, cochilo e recolher."""
        st = self.pet_state
        body = self.pet.body
        for evento in eventos:
            if evento == "festejar":
                st.modo_jogo = True
                st.feliz_ate = agora + 2.5
                self.emotion.force("feliz", 2.0, agora, PRIORITY["carinho"])
                if body.grounded and not body.held:
                    body.jump(0.0, -380.0)            # pulinho de "vamos jogar!"
                log("[jogo] você entrou no jogo: festa!")
            elif evento == "pegou_controle":
                st.controle = True
                st.controle_pulse = agora + 1.0             # a mola: o controle sobe de baixo
                log("[jogo] pegou o controle")
            elif evento == "pico":
                gatilho = random.choice(("sobressalto", "alegre"))
                st.controle_pulse = max(st.controle_pulse, agora + 0.45)   # o controle treme com você
                if gatilho == "sobressalto":
                    self.emotion.force("assustado", 0.9, agora, PRIORITY["assustado"])
                    if body.grounded and not body.held:
                        body.jump(0.0, -300.0)        # leva um susto e levanta da cadeirinha
                else:
                    st.feliz_ate = agora + 1.5
                    self.emotion.force("feliz", 1.2, agora, PRIORITY["carinho"])
                log(f"[jogo] pico de ação: {gatilho}")
            elif evento == "cochilar":
                st.controle = False                   # o controle fica no colo: bocejo e cochilo
                self.emotion.force("dormindo", 240.0, agora, PRIORITY["dormindo"])
                log("[jogo] cochilo no meio do jogo")
            elif evento == "acordou":
                st.controle = True
                self.emotion.force("contente", 1.0, agora, PRIORITY["carinho"])
                log("[jogo] acordou e voltou ao jogo")
            elif evento == "soltou":
                st.modo_jogo = False
                st.controle = False
                log("[jogo] acabou a partida: recolheu")
        self.update_visibility()

    def _penalti_frame(self, agora, corpo, bola):
        """Um passo do pênalti: goleiro desconfiado, defesa em cartaz, gol em fogos."""
        acao = self.penalti.tick(agora, bola, corpo, self.bounds()[3],
                                 GOL_ALCANCE, GOL_ALTURA, COLISAO_GOL, VIDA_JOGADA)
        if acao is None:
            return
        tipo, *resto = acao
        if tipo == "dive":
            lado = resto[0] if resto else 1
            corpo.jump(lado * EMPURRAO_GOLEIRO, PULO_GOLEIRO)   # o pulinho do goleiro
        elif tipo == "defesa":
            self.emotion.force("contente", 1.8, agora, PRIORITY["carinho"])
            self._cartaz_da_defesa(corpo)
            log("[pênalti] defendeu!")
        elif tipo == "gol":
            self.festa.fogos.launch(corpo.x, corpo.y - 60.0)    # passou da trave: festa
            log("[pênalti] gol — fogos!")

    def _cartaz_da_defesa(self, corpo):
        """Cartaz rápido de defesa ('Na barra!', 'NÃO PASSA!'): apoiado no pet, cai como objeto."""
        ex, ey = corpo.extents()
        cartaz = SignThing(random.choice(DEFESAS_CARTAZ), "small")
        cartaz.place(corpo.x, corpo.y - ey - cartaz.height() / 2 + 10.0)
        self.mischief.things.append(cartaz)
        cartaz.show()

    def frame(self):
        """Um quadro da tela: move o corpo pela física e atualiza a animação do pet."""
        now = time.monotonic()
        dt = min(0.05, max(0.0, now - self.last_frame))
        self.last_frame = now
        if not self.pet.isVisible() or self.paused or self.wiping:
            return

        areas = self.screen_bounds()
        monitores = self.screen_geometries()
        bounds = self.bounds()
        cursor = cursor_pos()
        body = self.pet.body
        body.step(dt, bounds, self.platforms, areas, monitores)
        self.behavior.screen_areas = areas
        if not body.held and self.mesa.pin(body, now) == "arrancado":
            self.arrancar_notebook(now)
        speed = max(body.pop_impacts(), default=0.0)
        if speed >= HARD_IMPACT and now - self.last_impact >= IMPACT_COOLDOWN:
            self.last_impact = now
            self.senses.impact(min(1.0, 0.3 + (speed - HARD_IMPACT) / 1500.0))
            if self.asleep:
                self.sleep.wake(startled=True)
            if speed >= DIZZY_IMPACT:
                self.pet_state.dizzy_until = now + DIZZY_SECONDS
        motores = self.brain.motor_activity()
        self.behavior.canto = motores["CANTO"] >= LIMIAR_CANTO_HZ
        self.behavior.tick(dt, now, cursor, bounds, self.prof, self.platforms)
        self.castigo.act(now, body, bounds, cursor, self.pet_state, motores, asleep=self.asleep)
        preso = self.castigo.dentro                  # no cantinho, nada de greve
        if self.protest.stage == 0:
            self.sad_ctl.carry(now, self.asleep or preso)
        else:
            self.sad_ctl.drop_sign()
        self.protest_ctl.carry(now, self.asleep or preso)
        ball_bounds = self._bounds_at(areas, self.ball.body.x, self.ball.body.y)
        self.ball.step(dt, ball_bounds, areas, monitores)
        self._penalti_frame(now, body, self.ball)
        if self.comida.isVisible():
            comida_bounds = self._bounds_at(areas, self.comida.body.x, self.comida.body.y)
            self.comida.step(dt, comida_bounds, areas, monitores)
        if self.presente.isVisible():
            presente_bounds = self._bounds_at(areas, self.presente.body.x, self.presente.body.y)
            self.presente.step(dt, presente_bounds, areas, monitores)
        self.revolucao.tick(
            now, dt, bounds, cursor, self.cursor_vel, self.pet.body, self.pet.isVisible(),
            revoltado=self.protest.stage == 4 and not self.asleep and not preso and self.pet.isVisible(),
            papel_hz=motores["PAPEL"],
            obstaculos=self._obstaculos_da_mesa(),
        )
        # o cursor também bate na bolinha
        if self._prev_cursor is not None and now > self._prev_cursor_t:
            k = now - self._prev_cursor_t
            self.cursor_vel = ((cursor[0] - self._prev_cursor[0]) / k, (cursor[1] - self._prev_cursor[1]) / k)
        self._prev_cursor, self._prev_cursor_t = cursor, now
        self.last_cursor_push = push_from_cursor(self.ball, cursor, self.cursor_vel, now, self.last_cursor_push)
        bounce_off(self.ball, [(g.x(), g.y(), g.width(), g.height())
                               for g in (t.geometry() for t in self.mischief.things if not t.carried)])
        self.behavior.toy = (self.ball.body.x, self.ball.body.y) if self.ball.isVisible() else None
        self.mischief.tick(dt, bounds[3])
        self.pet.animate(now)
        if self.comida.isVisible() and now - self._comida_elevada_em > 2.0:
            self.comida.raise_()                 # o pet sobe por cima a cada 2 s; o biscoito sobe junto
            self._comida_elevada_em = now
        if self.presente.isVisible() and now - self._presente_elevado_em > 2.0:
            self.presente.raise_()               # idem a caixinha (continua clicável)
            self._presente_elevado_em = now
        self.maybe_mischief(now, dt, bounds, cursor, motores)
        if self.pet_state.modo_jogo:
            self.mischief.recolher_antigos(VIDA_MEME_DE_JOGO)   # faxina: a sua tela de jogo, limpa

    def _atualizar_mesa(self, now):
        """O neurônio SENTAR decide se ele senta no notebook. Aqui só entram as condições do corpo."""
        rates = self.brain.pool_rates()
        motores = self.brain.motor_activity()
        pode_sentar = (not self.asleep and self.pet.body.grounded and not self.pet.body.held
                       and not self.behavior.mission and not self.in_flight
                       and not self.pet_state.modo_jogo                     # no jogo, não senta
                       and not self.castigo.dentro and self.castigo.fuga is None)   # preso ou fugindo não senta
        self.mesa.tick(now, rates, motores["SENTAR"], pode_sentar, self.behavior.play)
        self.pet_state.at_desk = self.mesa.sentado
        self.pet_state.desk_top = self.mesa.caderno.y() if self.mesa.sentado else None
        self.behavior.play_pull = pull(rates)
        if self.mesa.pop_recusa():                 # pediram para trabalhar e ele não quis
            self.pulso_recusa = min(1.0, 0.4 + 0.2 * self.mesa.pedidos_recentes())
            if self.debugging():
                log(f"[notebook] recusou o pedido (pedidos recentes: {self.mesa.pedidos_recentes()})")

    def _pode_soltar_fogo(self):
        """Diz se pode soltar fogos de artifício agora (permitido, acordado e pet visível)."""
        return self.perms["fogos"] and not self.asleep and self.pet.isVisible()

    def _obstaculos_da_mesa(self):
        """Retângulos dos post-its e objetos, onde a bolinha de papel bate."""
        return [(g.x(), g.y(), g.width(), g.height())
                for g in (t.geometry() for t in self.mischief.things if not t.carried)]

    def maybe_mischief(self, now, dt, bounds, cursor, motores):
        """Decide se vai aprontar uma travessura agora (não aprontar de castigo, dormindo ou no Tacinho)."""
        if self.castigo.dentro or self.pet_state.quieto(now):   # preso ou quietsinho: nada de travessura
            return
        self.mischief_ctl.maybe_act(
            now, dt, bounds, cursor, self.pet.body, motores=motores,
            activity=self.activity, emotion=self.pet_state.emotion, perms=self.perms, prof=self.prof,
            fullscreen=self.fullscreen, asleep=self.asleep, protest_stage=self.protest.stage,
            working=self.activity in ("PROGRAMMING", "DESIGNING") and not self.mesa.sentado,
            modo_jogo=self.pet_state.modo_jogo,
        )

    # ---------------- interação ----------------

    # ---------------- controles ----------------

    # ---------------- menu do botão direito ----------------

