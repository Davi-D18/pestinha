"""
INTERAÇÃO - o que você faz com o pet: cutucar, arrastar, arremessar, dispensar travessuras,
os comandos do menu do botão direito e o notebook.

Cada interação vira sinal para a rede (sentidos), homeostase, condicionamento e memória.
Pausado ou desligado, as interações não mexem no estado (ver SessaoMixin._congelado).
Mixin de PestinhaApp: usa os atributos criados em PestinhaApp.__init__.
"""

from ..log import log
import time
from PySide6.QtWidgets import QMenu
from ..store import read_json, write_json
from ..core.emotion import PRIORITY
from ..ui.ui import RecadoDialog
from ..ajustes import (
    INSATISFACAO_NOTEBOOK,
    COOLDOWN_CUTUCADA as POKE_COOLDOWN,
    ESPERA_MEDIDA_CUTUCADA as POKE_PROBE,
    HZ_RESPOSTA_CHEIA as POKE_FULL_HZ,
    RESPOSTA_MINIMA as POKE_MIN_RESPONSE,
    RECOMPENSA_BALANCO,
    RECOMPENSA_BEIJO,
    DURACAO_BEIJO,
    DURACAO_TACINHO,
)
from ..body.bolinha import load_sprite
from ..body.pet import cursor_pos


class InteracaoMixin:
    """Ações do usuário sobre o pet: cutucar, arrastar, arremessar, dispensar travessuras e o menu do botão direito. Vira atributo de PestinhaApp."""
    def on_poke(self):
        """Você cutucou o pet: ele reage e a rede recebe o toque (ignorado na pausa)."""
        if self._congelado():
            return
        now = time.monotonic()
        if now - self.last_poke < POKE_COOLDOWN:
            return
        self.sad.grievance = max(0.0, self.sad.grievance - 0.25)     # cutucar alegra um pouco
        self.last_poke = now
        self.conditioning.outcome(now)
        self.senses.poke()
        self.timeline.note_interaction()
        self.drives.stimulate("poke")
        self.drives.touched("poke")
        self.memory.on_interaction()
        if self.asleep:
            self.sleep.wake(startled=True)
        # a reação NÃO é fixa: mede-se o que a rede fez com a cutucada (ver poke_reflex)
        self.poke_probe = (now + POKE_PROBE, self.brain.motor_activity()["CHEER"])

    def poke_reflex(self, delta_hz):
        """
        Tamanho da reação = aumento real de CHEER causado pela cutucada.
        Com cutucadas repetidas a sinapse de POKE habitua e a resposta encolhe:
        pulo grande, pulo menor, só os olhos, quase nada. Volta depois de minutos.
        """
        self.poke_probe = None
        response = max(0.0, min(1.0, delta_hz / POKE_FULL_HZ))
        if self.protest.stage == 3:
            response *= 0.2                         # em greve: mal responde
        self.last_poke_response = response
        body = self.pet.body
        if response >= POKE_MIN_RESPONSE and body.grounded:
            body.jump(0.0, -(150.0 + 650.0 * response))
        else:
            self.pet_state.blink_until = time.monotonic() + 0.13       # só pisca e olha
            cx, cy = cursor_pos()
            self.behavior.look_at(cx, cy, time.monotonic())
        if self.debugging():
            eff = self.brain.efficacy()["POKE"]
            log(f"[cutucada] resposta da rede {response:.2f} "
                  f"(+{delta_hz:.1f} Hz em CHEER, eficácia POKE {eff:.2f})")

    def on_drag_started(self):
        """Você pegou o pet: ele sente o arraste e a insatisfação baixa um pouco (você está interagindo)."""
        if self._congelado():
            return
        self.sad.grievance = max(0.0, self.sad.grievance - 0.1)
        self.conditioning.outcome(time.monotonic())
        self.senses.set_dragging(True)
        self.timeline.note_interaction()
        self.drives.stimulate("drag")
        self.drives.touched("drag")
        self.memory.on_interaction()
        if self.asleep:
            self.sleep.wake(startled=True)

    def on_thrown(self, speed):
        """Você arremessou o pet: a velocidade vira intensidade do arremesso; ele não aprende com isso na pausa."""
        if self._congelado():
            return
        self.conditioning.outcome(time.monotonic())
        self.senses.thrown(min(1.0, speed / 2000.0))
        self.timeline.note_interaction()
        self.drives.stimulate("throw")
        self.drives.touched("throw")
        self.in_flight = True

    def on_dismissed(self, thing, elapsed):
        """Você dispensou uma travessura: ela some, e o tempo até você fechar vira aprendizado (fechar rápido é pior)."""
        if self._congelado():
            return                                   # o objeto some, mas não vira aprendizado na pausa
        self.mischief_ctl.on_dismissed(thing, elapsed, self.prof, time.monotonic())

    def arrancar_notebook(self, now):
        """Arrancaram o notebook dele: ele levanta e fica bravo ou triste, conforme o pet."""
        self.mesa.levantar_arrancado(now)
        self.senses.dismissed()                    # a dispensa entra na rede como frustração
        alvo = self.sad_ctl if self.reacao_notebook == "triste" else self.protest_ctl
        alvo.provoke(INSATISFACAO_NOTEBOOK)
        if self.debugging():
            log(f"[notebook] arrancado: reação {self.reacao_notebook}")

    def show_pet_menu(self, pos):
        """Mostra o menu do botão direito no pet; cada item fica desativado se não fizer sentido agora."""
        menu = QMenu()
        perms = self.perms

        def item(text, fn, enabled=True):
            """Cria um item do menu; `enabled=False` deixa o item visível mas sem ação."""
            act = menu.addAction(text)
            act.setEnabled(enabled)
            act.triggered.connect(fn)

        item("Cutucar", self.menu_poke, perms["cutucar"])
        item("Dar carinho", self.menu_caress, perms["carinho"])
        menu.addSeparator()
        item("Jogar a bolinha perto dele", self.menu_place_ball, perms["bolinha"])
        item("Guardar a bolinha", self.menu_store_ball, perms["bolinha"] and not self.ball_stored)
        item("Oferecer biscoito", lambda: self.menu_comida("biscoito"), perms["comida"])
        item("Servir o café", lambda: self.menu_comida("cafe"), perms["comida"])
        item("Água fresca", lambda: self.menu_comida("agua"), perms["comida"])
        item("Sair do pênalti" if self.penalti.ativo else "Pênalti com a bolinha",
             self.menu_penalti, perms["bolinha"])
        item("Recolher o presente" if self._presente_na_tela else "Dar um presente",
             self.menu_presente, perms["presente"])
        item("Deixar um recado...", self.menu_recado, perms["bilhetes"])
        quieto = self.pet_state.quieto()
        item("Pode voltar a conversar" if quieto else "Tacinho (fica quietinho 1 h)", self.menu_quieto)
        menu.addSeparator()
        item("Pedir para dormir", self.menu_sleep, not self.asleep)
        item("Pedir para trabalhar", self.menu_pedir_trabalho)
        item("Mostrar o notebook" if self.mesa.escondido else "Esconder o notebook",
             self.menu_alternar_notebook)
        item("Trocar de monitor", self.menu_trocar_monitor, len(self.screen_bounds()) > 1)
        item("Fazer uma travessura agora", self.menu_mischief, perms["travessuras"])
        menu.addSeparator()
        item("Cantinho do castigo", lambda: self.castigo.toggle(self.bounds()))
        item("Painel de protesto", lambda: self.floats.toggle("greve"))
        item("Monitor neural", lambda: self.floats.toggle("neural"))
        item("Configurações...", self.open_settings)
        menu.addSeparator()
        item("Esconder (volta pela bandeja)", self.toggle_hidden)
        item("Fechar", self.menu_close)
        menu.exec(pos)

    def menu_poke(self):
        """Menu: 'Cutucar' (ignora o intervalo mínimo entre cutucadas)."""
        self.last_poke = 0.0
        self.on_poke()

    def menu_caress(self):
        """Menu: 'Fazer carinho' (conta como carinho na rede, se não estiver pausado)."""
        if self._congelado():
            return
        self.pet_state.mark_caress()
        self.drives.touched("caress")
        self.memory.on_interaction()
        self.timeline.note_interaction()

    def menu_place_ball(self):
        """Menu: 'Pôr a bolinha' (coloca a bolinha perto do pet, no chão)."""
        self.ball_stored = False
        self.ball.body.x = self.pet.body.x + 130
        self.ball.body.y = self.bounds()[3] - 40
        self.ball.body.vx = self.ball.body.vy = 0.0
        self.update_visibility()

    def menu_store_ball(self):
        """Menu: 'Guardar a bolinha' (some com a bolinha até você pedir de novo)."""
        self.ball_stored = True
        self.update_visibility()

    def menu_comida(self, tipo="biscoito"):
        """Menu: 'Oferecer biscoito'/'Servir o café'/'Água fresca' — põe a comida perto dele no chão. Clicar de novo com o mesmo tipo recolhe."""
        if self._comida_na_tela and self.comida.tipo == tipo:
            self._comida_na_tela = False
        else:
            self._comida_na_tela = True
            self.comida.tipo = tipo
            sprite = {"biscoito": self.conteudo.biscoito,
                      "cafe": self.conteudo.cafe,
                      "agua": self.conteudo.agua}[tipo]
            self.comida.sprite = load_sprite(sprite)
            self.comida.body.x = self.pet.body.x + 150
            self.comida.body.y = self.bounds()[3] - 40
            self.comida.body.vx = self.comida.body.vy = 0.0
            self.comida.raise_()                 # a comida nasce na frente do pet
            self._comida_elevada_em = time.monotonic()
            log(f"[comida] {tipo} na tela")
        self.update_visibility()

    def menu_presente(self):
        """Menu: 'Dar um presente' (ou 'Recolher o presente'): a caixinha-surpresa perto dele."""
        if self._presente_na_tela:
            self._presente_na_tela = False
        else:
            self._presente_na_tela = True
            self.presente.body.x = self.pet.body.x + 150
            self.presente.body.y = self.bounds()[3] - 40
            self.presente.body.vx = self.presente.body.vy = 0.0
            self.presente.raise_()
            self._presente_elevado_em = time.monotonic()
            log("[presente] caixinha na tela")
        self.update_visibility()

    def menu_recado(self):
        """Menu: 'Deixar um recado...': texto e hora; na hora ele cutuca e cola o bilhete."""
        resultado = RecadoDialog.pedir()
        if resultado and self.lembretes.adicionar(*resultado):
            texto, quando = resultado
            log(f"[lembretes] recado para {time.strftime('%H:%M', time.localtime(quando))}: {texto}")

    def menu_penalti(self):
        """Menu: liga/desliga o pênalti: ele fica de goleiro; a sua bolinha arremessada é o chute."""
        ativo = not self.penalti.ativo
        self.penalti.ativo = ativo
        self.penalti.arremesso = None
        self.pet_state.penalti = ativo
        self.ball.aim_hint = ativo                   # a linha de mira só existe no jogo
        if ativo:
            self.ball_stored = False                 # garante a bolinha na tela
            self.behavior.drop_carried()             # nada de missão com o goleiro parado
            self.menu_place_ball()
            log("[pênalti] começou: arremessa a bolinha nele")
        else:
            log("[pênalti] acabou a partida")
        self.update_visibility()

    def menu_quieto(self):
        """Menu: 'Tacinho' (1 h quietsinho num canto) ou volta ao normal."""
        agora = time.monotonic()
        if self.pet_state.quieto_ate > agora:
            self.pet_state.quieto_ate = 0.0
            log("[tacinho] de volta ao normal")
        else:
            self.pet_state.quieto_ate = agora + DURACAO_TACINHO
            log("[tacinho] vai ficar quietinho por 1 h")
        self.update_visibility()

    def on_shaken(self):
        """Você chacoalhou o pet segurando (3 trocas de lado na janela): ele gargalha e fica alegrinho."""
        if self._congelado():
            return
        agora = time.monotonic()
        self.conditioning.outcome(agora)
        self.drives.stimulate("drag")
        self.drives.touched("drag")
        self.memory.on_interaction()
        self.timeline.note_interaction()
        self._premio_extra += RECOMPENSA_BALANCO
        self.pet_state.feliz_ate = agora + 1.5
        self.pet_state.dizzy_until = max(self.pet_state.dizzy_until, agora + 1.0)
        self.emotion.force("feliz", 1.2, agora, PRIORITY["carinho"])
        if self.pet.body.grounded:
            self.pet.body.jump(0.0, -260.0)
        log("[balanço] gargalhada")

    def on_kiss(self):
        """Você deu um beijo (dois cliques no rosto): coraçãozinho na tela; o primeiro do dia vale recompensa grande."""
        if self._congelado():
            return
        agora = time.monotonic()
        dia = time.strftime("%Y-%m-%d")
        arquivo = self.paths.beijos
        dados = read_json(arquivo, default={})
        primeiro = isinstance(dados, dict) and dados.get("dia") != dia
        self.pet_state.beijo_para = agora + DURACAO_BEIJO
        self.emotion.force("feliz", 1.5, agora, PRIORITY["carinho"])
        self.memory.on_interaction()
        self.timeline.note_interaction()
        if primeiro:
            write_json(arquivo, {"dia": dia})
            self._premio_extra += RECOMPENSA_BEIJO
            log(f"[beijo] beijo do dia ({dia})")
        else:
            log("[beijo] beijo extra (o do dia já valeu)")

    def menu_sleep(self):
        """Menu: 'Dormir' (baixa a energia: ele cochila em vez de ficar acordado)."""
        if self._congelado():
            return
        self.drives.energy = min(self.drives.energy, 0.1)

    def menu_mischief(self):
        """Menu: 'Aprontar' (pede uma travessura agora)."""
        self.mischief_ctl.pedir(time.monotonic())

    def menu_alternar_notebook(self):
        """Menu: mostra ou esconde o notebook; sem o notebook, ele não pode sentar nele."""
        self.mesa.alternar_notebook()
        self.pet_state.at_desk = self.mesa.sentado
        if not self.mesa.sentado:
            self.pet_state.desk_top = None

    def menu_trocar_monitor(self):
        """Menu: leva o pet para a área útil do monitor seguinte; pousa no chão e fica lá."""
        areas = self.screen_bounds()
        if len(areas) < 2:
            return
        corpo = self.pet.body
        atual = next((i for i, area in enumerate(areas)
                      if area[0] <= corpo.x <= area[2] and area[1] <= corpo.y <= area[3]), 0)
        left, _top, right, bottom = areas[(atual + 1) % len(areas)]
        log(f"[tela] troca: do monitor {atual} para o {(atual + 1) % len(areas)} "
            f"(chão y={bottom}) — areas {areas}")
        corpo.x = (left + right) / 2
        corpo.vx = corpo.vy = 0.0
        corpo.angle = 0.0
        corpo.y = bottom - corpo.extents()[1] - 2     # direto no chão: sem queda
        corpo.surface = bottom                        # o "chão memorizado" é o da tela NOVA
        corpo.grounded = True
        corpo.platform = None
        corpo.chao_solido = True                      # pulos não deixam mais cair na emenda

    def menu_pedir_trabalho(self):
        """Menu: 'Pedir para trabalhar' (ele pode aceitar, ou recusar com frustração)."""
        self.mesa.pedir(time.monotonic())
