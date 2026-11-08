"""
PET - a telinha com olhinhos: janela transparente, desenho e mouse.

A janela é um quadrado transparente maior que o corpo, para caber o corpo
girado. Pixels transparentes deixam o clique passar para o que está embaixo.
A janela nunca pega o foco (o teclado continua no seu programa).
"""

import math
import random
import time
from pathlib import Path

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from ..config import EMOTION_NAMES
from ..core.emotion import EYE_SHAPES
from ..core.physics import Body
from .. import plataforma
from ..ajustes import (
    LADO_JANELA_PET as WIN,
    TEMPO_MAX_CUTUCADA_MS as POKE_MAX_MS,
    DISTANCIA_INICIO_ARRASTE as DRAG_START_PX,
    VELOCIDADE_ARREMESSO as THROW_MIN_SPEED,
    JANELA_CARINHO as RUB_WINDOW,
    TROCAS_CARINHO as RUB_REVERSALS,
    DESLOCAMENTO_CARINHO as RUB_MIN_TRAVEL,
    JANELA_BALANCO as SHAKE_WINDOW,
    REVERSOS_BALANCO as SHAKE_REVERSALS,
    PASSO_BALANCO as SHAKE_MIN_STEP,
    DURACAO_BEIJO as KISS_SECONDS,
)

from .desenho_rosto import BODY_H, BODY_W, PADRAO, draw_face, draw_zzz, lerp_shape

CX, CY = WIN / 2, WIN / 2 - 6   # centro do corpo dentro da janela



# carinho = passar o mouse para lá e para cá em cima dele, sem clicar


def set_no_activate(widget):
    """Garante que clicar/mostrar a janela não rouba o foco do programa atual (onde o sistema permite)."""
    try:
        plataforma.sem_foco_nativo(int(widget.winId()))
    except Exception:
        pass    # sem janela nativa (ex.: teste offscreen)


def overlay_flags():
    """Janela sem moldura, sempre por cima, que não aparece na barra de tarefas nem recebe foco ao aparecer."""
    return (
        Qt.FramelessWindowHint
        | Qt.Tool
        | Qt.WindowStaysOnTopHint
        | Qt.WindowDoesNotAcceptFocus
    )


class PetWindow(QWidget):
    """Janela do pet: desenha o PetState e traduz o mouse em gestos (sinais)."""

    poked = Signal()
    drag_started = Signal()
    drag_ended = Signal()
    thrown = Signal(float)          # velocidade do arremesso (px/s)
    menu_requested = Signal(object) # botão direito: posição global do clique
    shaken = Signal()               # você chacoalhou o pet segurando (gargalhada)
    kissed = Signal()               # dois cliques rápidos no rosto: beijo

    def __init__(self, x, y, state):
        """Janela transparente do pet: o rosto é desenhado aqui e o mouse vira gestos (cutucar, arrastar, arremessar)."""
        super().__init__(None, overlay_flags())
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(WIN, WIN)

        self.body = Body(x, y, BODY_W / 2, BODY_H / 2)
        self.state = state
        self.aparencia = PADRAO      # cores e acessórios do pet (pets/<pet>.json)
        self.next_blink = time.monotonic() + random.uniform(2.0, 5.0)

        self._press = None          # (pos global, tempo)
        self._grab = (0.0, 0.0)
        self._dragging = False
        self._samples = []          # (t, x, y) para a velocidade do arremesso
        self._held_angle = 0.0
        self._rub = []              # (t, x) do mouse passando sem clicar
        self._balanco = []          # (t, x) do mouse enquanto você chacoalha o pet segurando
        self._balanco_para = -1e9   # gargalhada em andamento: não conta de novo na sequência
        self._sonho_img = None      # QPixmap do meme que ele está sonhando (cache)
        self._sonho_key = None
        self.setMouseTracking(True)

    def _track_rub(self, x):
        """Detecta carinho: o mouse passando de um lado para o outro várias vezes, sem clicar, em cima do pet."""
        now = time.monotonic()
        self._rub.append((now, x))
        self._rub = [r for r in self._rub if now - r[0] < RUB_WINDOW]
        reversals, travel, last_dir = 0, 0.0, 0
        for (_, x0), (_, x1) in zip(self._rub, self._rub[1:]):
            step = x1 - x0
            if abs(step) < 2:
                continue
            direction = 1 if step > 0 else -1
            if last_dir and direction != last_dir:
                reversals += 1
            last_dir = direction
            travel += abs(step)
        if reversals >= RUB_REVERSALS and travel >= RUB_MIN_TRAVEL:
            self.state.mark_caress(now)

    @staticmethod
    def _conta_reversos(amostas):
        """Trocas de lado e curso total dentro de uma janela de amostras (t, x)."""
        reversals, travel, last_dir = 0, 0.0, 0
        for (_, x0), (_, x1) in zip(amostas, amostas[1:]):
            passo = x1 - x0
            if abs(passo) < 2:
                continue
            direction = 1 if passo > 0 else -1
            if last_dir and direction != last_dir:
                reversals += 1
            last_dir = direction
            travel += abs(passo)
        return reversals, travel

    def _track_balanco(self, x):
        """Detecta chacoalho: você segura o pet e o arrasta de lado a lado várias vezes."""
        now = time.monotonic()
        if now - self._balanco_para < 4.0:
            return                              # gargalhou agora: deixa o riso terminar
        self._balanco.append((now, x))
        self._balanco = [r for r in self._balanco if now - r[0] < SHAKE_WINDOW]
        reversals, travel = self._conta_reversos(self._balanco)
        if reversals >= SHAKE_REVERSALS and travel >= 3.0 * SHAKE_MIN_STEP:
            self._balanco_para = now
            self._balanco = []
            self.shaken.emit()

    def showEvent(self, event):
        """Ao aparecer, a janela já é marcada para não roubar o foco do programa que você está usando."""
        super().showEvent(event)
        set_no_activate(self)
        self._ultimo_subir = time.monotonic()

    # ---------------- sonho ----------------

    def _desenha_sonho(self, p, st):
        """+Balãozinho de sonho: o meme que ele está sonhando, com fade de entrada e de saída."""
        if not st.dream_path:
            return
        now = time.monotonic()
        duracao = max(st.dream_ate - st.dream_de, 0.1)
        idade = now - st.dream_de
        if st.dream_de <= 0 or idade < 0 or idade > duracao:
            return
        alpha = max(0.0, min(1.0, min(idade, st.dream_ate - now) / 1.2))
        if self._sonho_key != st.dream_path or self._sonho_img is None:
            img = QPixmap(str(Path(st.dream_path)))
            if img.isNull():
                return
            self._sonho_img = img.scaled(84, 62, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self._sonho_key = st.dream_path
        p.save()
        p.setOpacity(alpha)
        lado = self.width() * 0.72          # bolha à direita da cabecinha
        topo = self.height() * 0.16
        caixa = QRectF(lado, topo, self._sonho_img.width() + 18, self._sonho_img.height() + 14)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(self.aparencia.olho, 1.4))
        p.setBrush(QColor(232, 247, 236, 230))
        p.drawRoundedRect(caixa, 10, 10)
        # bolhinhas que ligam o sonho à cabecinha
        c = QPointF(CX, CY - 46)
        for raio in (3.2, 2.0):
            p.drawEllipse(QPointF(c.x() + 16, c.y() + 14), raio, raio)
        p.drawPixmap(QPointF(caixa.left() + 9, caixa.top() + 7), self._sonho_img)
        p.restore()

    # ---------------- música ----------------

    def _desenha_fone(self, p):
        """Fone de ouvido em coordenadas LOCAIS do corpo (gira junto): arcada grossa, conchas e almofada.

        Chamado dentro do painter já transladado ao centro do corpo e girado: tudo aqui usa o
        (0, 0) do corpo — usar CX/CY aqui desenharia o fone no lugar errado, fora da cabeça.
        """
        cor = QColor(self.aparencia.olho)
        largura = BODY_W + 18
        p.setPen(QPen(cor.darker(130), 5.0))
        p.setBrush(Qt.NoBrush)
        p.drawArc(QRectF(-largura / 2, -BODY_H / 2 - 14, largura, BODY_H + 10), 0, 180 * 16)
        p.setPen(QPen(cor, 2.0))
        for lado in (-1, 1):
            x = lado * (largura / 2 - 3)
            p.drawLine(QPointF(x, -BODY_H * 0.34), QPointF(x, -12))
        p.setPen(QPen(cor.darker(150), 2.0))
        p.setBrush(QColor("#232323"))
        for lado in (-1, 1):
            x = lado * (largura / 2 - 3)
            p.drawRoundedRect(QRectF(x - 8, -26, 16, 30), 7, 7)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#3d3d3d"))
        for lado in (-1, 1):
            x = lado * (largura / 2 - 3)
            p.drawRoundedRect(QRectF(x - 4, -21, 8, 20), 4, 4)

    def _desenha_controle(self, p):
        """Controle nas patinhas (modo jogo), no plano do corpo, com o pulinho de mola.

        Sobe de baixo na hora em que ele pega (a entrada), e treme na pata a cada
        pico de ação seus (os "botões" acendem juntos). Como o fone: usa o (0, 0)
        do corpo já transladado e girado."""
        st, agora = self.state, time.monotonic()
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        y = BODY_H / 2 - 12
        corpo = QColor("#33383f")
        detalhe = QColor("#c9d2dc")
        if st.controle_pulse > agora:
            restante, curto = st.controle_pulse - agora, 0.45
            if restante > curto:                                # a entrada: desliza de baixo
                fracao = 0.0 if restante - curto >= 1.0 else 1.0 - (restante - curto) / 0.55
                p.translate(0, (1.0 - fracao) * 16.0)
            else:                                               # um pico: o controle treme na pata
                p.translate(0, -math.sin((curto - restante) / curto * math.pi) * 4.5)
                detalhe = detalhe.lighter(130)
        p.setPen(QPen(corpo.darker(150), 1.6))
        p.setBrush(corpo)
        p.drawRoundedRect(QRectF(-23, y - 9, 46, 14), 6, 6)     # a mesa do controle
        p.setBrush(corpo.darker(120))
        for lado in (-1, 1):                                    # os grips caem nas patinhas
            p.drawEllipse(QRectF(lado * 21 - 5, y + 2, 10, 10))
        p.setPen(QPen(detalhe, 2.2, Qt.SolidLine, Qt.RoundCap)) # o cruz direcional, à esquerda
        p.drawLine(QPointF(-15, y - 2), QPointF(-15, y + 2.4))
        p.drawLine(QPointF(-17.4, y + 0.2), QPointF(-12.6, y + 0.2))
        p.setPen(Qt.NoPen)
        p.setBrush(detalhe)
        p.drawEllipse(QRectF(-4.5, y - 1, 9, 9))                # um analógico central
        p.setBrush(detalhe.darker(110))
        p.drawEllipse(QRectF(-2.4, y - 1.4, 4.6, 4.6))
        p.setBrush(paralela := QColor("#e0474c"))
        p.drawEllipse(QRectF(12, y - 2.6, 5, 5))                # os quatro botões, à direita
        p.setBrush(QColor("#5a7de0"))
        p.drawEllipse(QRectF(13.6, y - 6.0, 5, 5))
        p.setBrush(QColor("#46b45e"))
        p.drawEllipse(QRectF(16.4, y - 2.0, 5, 5))
        p.setBrush(paralela.darker(110))
        p.drawEllipse(QRectF(14.8, y + 1.4, 5, 5))
        p.setBrush(detalhe)
        p.drawEllipse(QRectF(-20.5, y - 7.2, 4, 3))             # os gatilhos de trás
        p.drawEllipse(QRectF(16.5, y - 7.2, 4, 3))
        p.setPen(QPen(corpo, 1.4))                              # o fio até a base dele
        trilha = QPainterPath(QPointF(-23, y + 4))
        trilha.cubicTo(QPointF(-34, y + 6), QPointF(-34, y + 14), QPointF(-26, y + 14))
        p.drawPath(trilha)
        p.restore()

    def _desenha_notas(self, p, st):
        """Notas ♪♫ que sobem do topo da cabeça, alternando de lado, com fade e deriva leve."""
        agora = time.monotonic()
        cor = QColor(self.aparencia.olho)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(QFont("DejaVu Sans", 15, QFont.Bold))
        for guia in range(2):
            fase = (agora * 0.55 + guia * 0.5) % 1.0
            lado = (-1, 1)[(guia + int(agora * 0.55)) % 2]
            alpha = max(0.0, min(1.0, fase * 4.0)) * max(0.0, min(1.0, (1.0 - fase) * 4.0))
            x = CX + lado * (BODY_W / 2 + 24 + guia * 10) + math.sin(agora * 2.2 + guia) * 5
            y = CY - BODY_H / 2 - 24 - fase * 40
            p.setPen(QPen(cor, 1.5))
            p.setOpacity(alpha * min(1.0, st.groove))
            p.drawText(QPointF(x, y), "♫" if guia == 0 else "♪")
        p.restore()

    def _desenha_mordida(self, p, st):
        """A mordida: migalhas de comida saindo da boca e caindo (0,8 s), no plano do corpo."""
        agora = time.monotonic()
        vida = 0.8
        t = 1.0 - max(0.0, (st.comer_para - agora) / vida)      # 0 no começo da mordida → 1 no fim
        if t >= 1.0:
            return
        p.save()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#e8b45a"))
        for parcela in ((-1, 1.9), (1, 2.2), (-2.0, 2.8), (2.0, 3.2), (0, 2.5), (-1.4, 3.6)):
            dx, altura = parcela
            x = dx * 20.0 * t
            y = +12.0 * t + 480.0 * t * t * (0.55 + 0.2 * abs(dx))
            p.setOpacity(max(0.0, 1.0 - t))
            tamanho = max(1.0, 5.0 - 4.0 * t)
            p.drawEllipse(QPointF(x, y), tamanho, tamanho)
        p.restore()

    def _desenha_digita(self, p):
        """
        O tandem de digitação, à vista: um mini teclado sob o corpo, teclas que afundam na
        batida, patinhas com almofada e risquinhos de velocidade a cada pancada (5 batidas/s).
        """
        agora = time.monotonic()
        cor = QColor(self.aparencia.olho)
        teclado_topo = BODY_H / 2 + 3.0
        batidas, alturas = 5.0, 7.0
        p.save()
        # tábua do teclado, no estilo do fone (casca escura com contorno da cor do pet)
        p.setPen(QPen(cor.darker(150), 2.0))
        p.setBrush(QColor("#2b2b2b"))
        p.drawRoundedRect(QRectF(-BODY_W * 0.62, teclado_topo, BODY_W * 1.24, 13.0), 4, 4)
        # teclas: a tecla da pancada "afunda" (mais escura e mais baixa)
        p.setPen(QPen(cor.darker(170), 1.0))
        for k in range(5):
            lado_da_tecla = -1 if k < 2 else 1       # teclas 0..1: pata esquerda; 3..4: direita
            fase = (agora * batidas + (0.0 if lado_da_tecla < 0 else 0.5)) % 1.0
            afundada = fase < 0.35 and k in (1, 3)   # só a tecla sob cada pata afunda
            tecla_y = teclado_topo + 2.0 + (1.5 if afundada else 0.0)
            p.setBrush(QColor("#3d3d3d") if afundada else QColor("#4a4a4a"))
            p.drawRoundedRect(QRectF(-BODY_W * 0.50 + k * BODY_W * 0.22, tecla_y,
                                     BODY_W * 0.18, 5.0), 2, 2)
        # patinhas: almofada de coração... de patinha, subindo e descendo na batida
        for lado in (-1, 1):
            fase = (agora * batidas + (0.0 if lado < 0 else 0.5)) % 1.0
            x = lado * (BODY_W * 0.30)
            y = teclado_topo - 3.0 - abs(math.sin(fase * math.pi)) * alturas
            p.setPen(QPen(cor.darker(150), 1.2))
            p.setBrush(cor)
            p.drawEllipse(QPointF(x, y), 5.0, 3.5)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#f1ecd9"))
            for dx in (-2.0, 0.0, 2.0):              # dedinhos de cima
                p.drawEllipse(QPointF(x + dx, y - 2.6), 1.4, 1.4)
            # risquinhos de velocidade na descida (a pata batendo rápido)
            if 0.25 <= fase < 0.6:
                p.setPen(QPen(cor, 1.4))
                p.setOpacity(1.0 - (fase - 0.25) / 0.35)
                for dx in (-8.0, -11.0) if lado > 0 else (8.0, 11.0):
                    p.drawLine(QPointF(x + dx, y - 2.0), QPointF(x + dx * 1.6, y - 2.0))
                p.setOpacity(1.0)
        p.restore()

    def _desenha_beijo(self, p, st):
        """O coração do beijo: sobe do topo da cabeça e some (via fora do corpo, como as notas)."""
        agora = time.monotonic()
        if agora >= st.beijo_para:
            return
        vida = KISS_SECONDS
        t = 1.0 - (st.beijo_para - agora) / vida                 # 0 no começo → 1 no fim
        alpha = max(0.0, min(1.0, min(t, 1.0 - t) * 6.0))        # entra e sai rápido
        x = CX + math.sin(agora * 3.0) * 4.0
        y = CY - BODY_H / 2 - 30.0 - t * 34.0
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(QFont("DejaVu Sans", 17, QFont.Bold))
        p.setPen(QPen(QColor("#e0474c"), 1.0))
        p.setOpacity(alpha)
        p.drawText(QPointF(x, y), "❤")
        p.restore()

    # ---------------- animação ----------------

    def ajusta_frente(self, now):
        """
        Sobe a janela de vez em quando (a cada ~2 s) sem ativá-la: com várias janelas de outros
        programas na tela, o pet continua por cima de todas. O no-activate é quem impede que
        isso roube o foco; no Wayland o compositor não deixa, e o pet acaba coberto normalmente.
        """
        if now - getattr(self, "_ultimo_subir", now) >= 2.0:
            self.raise_()
            self._ultimo_subir = now

    def animate(self, now):
        """Um quadro da animação: suaviza a forma dos olhos, pisca de tempos em tempos e reposiciona a janela."""
        st = self.state
        target = dict(EYE_SHAPES.get(st.emotion, EYE_SHAPES["observando"]))
        if st.emotion != "dormindo":
            droop = st.tone.lid_droop()             # DROWSE pesa as pálpebras, em qualquer emoção
            target["inner"] = min(0.8, target["inner"] + droop)
            target["outer"] = min(0.8, target["outer"] + droop)
        st.shape = lerp_shape(st.shape, target, 0.22)
        if now >= self.next_blink:
            st.blink_until = now + 0.13
            self.next_blink = now + random.uniform(2.5, 6.0)

        if self.body.held:
            vx = self._velocity()[0]
            sway = max(-35.0, min(35.0, -vx * 0.03))
            self.body.angle += (self._held_angle + sway - self.body.angle) * 0.25

        self.move(int(self.body.x - CX), int(self.body.y - CY))
        self.ajusta_frente(now)
        self.update()

    def paintEvent(self, _event):
        """Desenha o pet: corpo, olhos, acessórios e balanço; some atrás da tampa do notebook quando está sentado."""
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        st = self.state
        if st.desk_top is not None:
            # sentado: o corpo some atrás da tampa do notebook (corta no nível dela, não depende da ordem das janelas)
            corte = int(st.desk_top - self.y())
            p.setClipRect(QRect(0, 0, self.width(), max(0, min(self.height(), corte))))
        shake = st.shake
        jitter_x = random.uniform(-shake, shake) if shake else 0.0
        jitter_y = random.uniform(-shake, shake) if shake else 0.0

        # SETTLE: balança devagarinho, de boa; a amplitude é a atividade da população
        sway = 0.0
        if self.body.grounded and st.emotion != "dormindo":
            sway = st.tone.sway() * math.sin(time.monotonic() * 2.2)
        if st.emotion == "dormindo":
            jitter_y += 1.5 * math.sin(time.monotonic() * 1.6)     # respirando devagar

        p.save()
        p.translate(CX + jitter_x, CY + jitter_y)
        p.rotate(self.body.angle + sway)
        blink = 0.08 if time.monotonic() < st.blink_until else 1.0
        draw_face(p, st.shape, st.gaze, blink, st.emotion, carinho=st.feliz_fechado(), aparencia=self.aparencia)
        if st.groove > 0.55:
            self._desenha_fone(p)                # no plano do corpo: o fone gira com ele
        if st.controle:
            self._desenha_controle(p)            # modo jogo: o controle nas patinhas, idem
        if time.monotonic() < st.comer_para:
            self._desenha_mordida(p, st)         # migalhas da mordida, no plano do corpo
        if st.digitando():
            self._desenha_digita(p)              # patinhas digitando junto, no plano do corpo
        p.restore()

        if st.emotion == "dormindo":
            draw_zzz(p, CX + jitter_x, CY + jitter_y, time.monotonic(), self.aparencia.olho)
            self._desenha_sonho(p, st)
        if st.groove > 0.55:
            self._desenha_notas(p, st)
        self._desenha_beijo(p, st)               # coração do beijo, se valer (o método corta sozinho)

        if st.show_label:
            p.setPen(self.aparencia.olho)
            p.setFont(QFont("Consolas", 9, QFont.Bold))
            p.drawText(QRectF(0, WIN - 22, WIN, 20), Qt.AlignCenter, EMOTION_NAMES.get(st.emotion, st.emotion))
        p.end()

    # ---------------- mouse ----------------

    def mousePressEvent(self, event):
        """Início de um gesto: guarda onde o botão foi apertado (clique esquerdo)."""
        if event.button() != Qt.LeftButton:
            return
        pos = event.globalPosition()
        self.state.pressing = math.hypot(pos.x() - self.body.x, pos.y() - self.body.y) < 90
        self._press = (pos, time.monotonic())
        self._grab = (pos.x() - self.body.x, pos.y() - self.body.y)
        self._samples = [(time.monotonic(), pos.x(), pos.y())]

    def mouseMoveEvent(self, event):
        """Enquanto o botão está apertado, arrasta o pet; sem botão, só registra o carinho do mouse."""
        pos = event.globalPosition()
        if self._press is None:
            self._track_rub(pos.x())
            return
        if not self.state.allow_drag:
            return
        start = self._press[0]
        if not self._dragging:
            if math.hypot(pos.x() - start.x(), pos.y() - start.y()) < DRAG_START_PX:
                return
            self._dragging = True
            self._held_angle = self.body.angle
            self.body.held = True
            self.body.grounded = False
            self.body.platform = None
            self.drag_started.emit()

        self.body.x = pos.x() - self._grab[0]
        self.body.y = pos.y() - self._grab[1]
        now = time.monotonic()
        self._samples.append((now, pos.x(), pos.y()))
        self._samples = [s for s in self._samples if now - s[0] < 0.12]
        self._track_balanco(pos.x())            # chacoalhou segurando? o app gargalha por ele

    def mouseDoubleClickEvent(self, event):
        """Dois cliques rápidos bem no rosto: beijo (o coração e a recompensa ficam no app)."""
        if event.button() != Qt.LeftButton:
            return
        local = event.position()
        if math.hypot(local.x() - CX, local.y() - CY) < 48:
            self.kissed.emit()

    def cancel_interaction(self):
        """Cancela um toque ou arraste em andamento (pânico, esconder): o corpo volta a cair."""
        self._press = None
        self._samples = []
        self.state.pressing = False
        if self._dragging:
            self._dragging = False
            self.body.held = False
            self.body.vx = self.body.vy = 0.0
            self.body.grounded = False
            self.body.platform = None

    def mouseReleaseEvent(self, event):
        """Fim do gesto: se foi um clique, é cutucada; se foi um arremesso, a velocidade vira força do lance."""
        if event.button() != Qt.LeftButton or self._press is None:
            return
        self.state.pressing = False
        held_ms = (time.monotonic() - self._press[1]) * 1000.0
        if self._dragging:
            vx, vy = self._velocity()
            self.body.held = False
            self.body.vx = max(-2500.0, min(2500.0, vx))
            self.body.vy = max(-2500.0, min(2500.0, vy))
            self.body.omega += self.body.vx * 0.35
            self.drag_ended.emit()
            speed = math.hypot(self.body.vx, self.body.vy)
            if speed >= THROW_MIN_SPEED:
                self.thrown.emit(speed)
        elif held_ms <= POKE_MAX_MS and self.state.allow_poke:
            self.poked.emit()
        self._press = None
        self._dragging = False
        self._balanco = []

    def contextMenuEvent(self, event):
        """Botão direito: pede ao app para abrir o menu do pet."""
        self.menu_requested.emit(event.globalPos())

    def wheelEvent(self, event):
        """Rodinha do mouse gira o pet (segurando ou no ar)."""
        if not self.state.allow_drag:
            return
        step = event.angleDelta().y() / 120.0 * 20.0
        if self.body.held:
            self._held_angle += step
        else:
            self.body.omega += step * 12.0
            if self.body.grounded:
                self.body.jump(0.0, -250.0)

    def _velocity(self):
        """Velocidade média do mouse nas últimas amostras (para o arremesso e o balanço)."""
        if len(self._samples) < 2:
            return 0.0, 0.0
        t0, x0, y0 = self._samples[0]
        t1, x1, y1 = self._samples[-1]
        dt = max(t1 - t0, 1e-3)
        return (x1 - x0) / dt, (y1 - y0) / dt

    @property
    def dragging(self):
        """Verdadeiro enquanto você está arrastando o pet."""
        return self._dragging


def cursor_pos():
    """Posição atual do cursor em pixels (x, y)."""
    p = QCursor.pos()
    return p.x(), p.y()
