"""
BOLINHA - a janela da bolinha: desenho e mouse. A física está em core/physics.py
e as regras de colisão e de "levaram" estão em toy.py.
"""

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QWidget

from ..ajustes import MEMORIA_SOLTURA as RELEASE_MEMORY, RAIO_BOLINHA as RADIUS
from ..core.physics import Body
from .pet import overlay_flags, set_no_activate


def load_sprite(path):
    """Carrega a foto de uma bolinha já no tamanho do desenho. None se o arquivo não existir."""
    if not path.exists():
        return None
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        return None
    return pixmap.scaled(RADIUS * 2, RADIUS * 2, Qt.KeepAspectRatio, Qt.SmoothTransformation)


class Ball(QWidget):
    """Bolinha que você pode chutar, arremessar e pegar (a bolinha de tênis ou a bolinha de papel da revolução)."""
    def __init__(self, x, y, kind="bola", sprite=None):
        """Cria a bolinha em (x, y); `kind` diz se é o brinquedo ou o papel; `sprite` é a imagem (ou o desenho de reserva)."""
        self.kind = kind            # "bola" (brinquedo) ou "papel" (bolinha de papel da revolução)
        self.sprite = sprite        # foto da bolinha (load_sprite); None usa o desenho de reserva
        super().__init__(None, overlay_flags())
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(RADIUS * 2 + 8, RADIUS * 2 + 8)
        self.body = Body(x, y, RADIUS, RADIUS)
        self.angle = 0.0
        self.dragging = False
        self._button = None         # botão que começou o arraste
        self.last_release = -1e9
        self._grab = (0.0, 0.0)
        self._samples = []
        self.aim_hint = False       # linha de mira no arraste (modo pênalti)

    def showEvent(self, event):
        """Ao aparecer, a bolinha não rouba o foco do programa que você está usando."""
        super().showEvent(event)
        set_no_activate(self)

    def place(self):
        """Reposiciona a janela da bolinha no lugar da física."""
        self.move(int(self.body.x - self.width() / 2), int(self.body.y - self.height() / 2))

    def handled_by_user(self, now):
        """Diz se você está com a bolinha agora ou a soltou há pouco (ela não deve ser chutada nesse meio tempo)."""
        return self.dragging or now - self.last_release < RELEASE_MEMORY

    # ---------------- física e desenho ----------------

    def kick(self, vx, vy):
        """Dá um impulso: a bolinha sai do chão e voa."""
        self.body.vx = vx
        self.body.vy = vy
        self.body.grounded = False
        self.body.platform = None

    def step(self, dt, bounds, areas=None, monitors=None):
        """Um passo de física: a bolinha rola conforme o pet anda e para aos poucos."""
        if not self.dragging:
            self.angle += self.body.vx * dt * 0.8        # rola conforme anda
            self.body.step(dt, bounds, [], areas, monitors)
        self.place()
        self.update()

    def paintEvent(self, _event):
        """Desenha a bolinha (imagem ou desenho de reserva) girando com o ângulo atual."""
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        if self.sprite is not None:
            p.translate(c)
            p.rotate(math.degrees(self.angle))      # a foto gira junto com a bolinha
            p.drawPixmap(QRectF(-RADIUS, -RADIUS, RADIUS * 2, RADIUS * 2), self.sprite, QRectF(self.sprite.rect()))
            p.resetTransform()
            self._pinta_mira(p, c)
            p.end()
            return
        if self.kind == "papel":
            p.setPen(QPen(QColor("#6b6657"), 1.2))
            p.setBrush(QColor("#f1ecd9"))
            p.drawEllipse(c, RADIUS, RADIUS)
            p.setPen(QPen(QColor("#9c967f"), 1))
            for k in range(4):                      # vincos de papel amassado
                a = self.angle + k * 1.2
                p.drawLine(c + QPointF(math.cos(a) * 3, math.sin(a) * 3),
                           c + QPointF(math.cos(a + 0.9) * RADIUS * 0.8, math.sin(a + 0.9) * RADIUS * 0.8))
            p.end()
            return
        if self.kind == "comida":
            # reservas (sem assets/comum/<tipo>.png)
            if getattr(self, "tipo", "biscoito") == "cafe":
                # caneca de café: corpo marrom, bebo escuro por dentro e fumaça em cima
                p.setPen(QPen(QColor("#4a3018"), 1.6))
                p.setBrush(QColor("#8a5a2a"))
                p.drawRoundedRect(QRectF(c.x() - RADIUS + 3, c.y() - 6, RADIUS * 2 - 6, RADIUS * 1.5)
                                  , 6, 6)
                p.setPen(QPen(QColor("#2a1a08"), 1.2))
                p.setBrush(QColor("#3c2510"))
                p.drawEllipse(c + QPointF(0, RADIUS * 0.2), RADIUS * 0.62, 4.5)
                p.setPen(QPen(QColor("#b7a08a"), 1.5))
                p.setBrush(Qt.NoBrush)
                p.drawArc(QRectF(c.x() - RADIUS + 4, c.y() - 22, 10, 14), -40 * 16, 80 * 16)
                p.drawArc(QRectF(c.x() + RADIUS - 14, c.y() - 24, 10, 14), -40 * 16, 80 * 16)
                p.end()
                return
            if self.tipo == "agua":
                # copo de água: vidro claro com a água azul e um brilho na lateral
                p.setPen(QPen(QColor("#7fbcd4"), 1.6))
                p.setBrush(QColor("#d7ecf5"))
                p.drawRoundedRect(QRectF(c.x() - RADIUS + 4, c.y() - RADIUS + 2,
                                         RADIUS * 2 - 8, RADIUS * 2 - 6), 5, 5)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#63b8e0"))
                p.drawRoundedRect(QRectF(c.x() - RADIUS + 6, c.y() - 4,
                                         RADIUS * 2 - 12, RADIUS - 6), 3, 3)
                p.setPen(QPen(QColor("#ffffff"), 2.0))
                p.setBrush(Qt.NoBrush)
                p.drawLine(c + QPointF(-RADIUS + 9, -RADIUS + 10), c + QPointF(-RADIUS + 9, 2))
                p.end()
                return
            # biscoito de reserva: massa amarela e gotas
            p.setPen(QPen(QColor("#8a5a1e"), 1.6))
            p.setBrush(QColor("#e8b45a"))
            p.drawEllipse(c, RADIUS, RADIUS)
            p.setPen(QPen(QColor("#5d3a12"), 1))
            p.setBrush(QColor("#5d3a12"))
            for xis, yis in ((-4, -3), (3, -1), (-1, 4), (5, 4)):
                p.drawEllipse(c + QPointF(xis, yis), 2.2, 2.2)
            p.end()
            return
        if self.kind == "presente":
            # caixinha de reserva: corpo roxo e fita amarela cruzada com um laço
            p.setPen(QPen(QColor("#4a2a8a"), 1.6))
            p.setBrush(QColor("#7b4bd0"))
            p.drawRoundedRect(QRectF(c.x() - RADIUS + 4, c.y() - RADIUS + 10,
                                     RADIUS * 2 - 8, RADIUS * 2 - 14), 5, 5)
            p.setPen(QPen(QColor("#c79a1e"), 1.2))
            p.setBrush(QColor("#ffd24a"))
            p.drawRect(QRectF(c.x() - 4, c.y() - RADIUS + 10, 8, RADIUS * 2 - 14))
            p.drawRect(QRectF(c.x() - RADIUS + 4, c.y() - 6, RADIUS * 2 - 8, 8))
            for lado in (-1, 1):                       # as duas orelhas do laço
                p.drawEllipse(c + QPointF(lado * 8.0, -RADIUS + 6.0), 6.0, 3.6)
            p.end()
            return
        grad = QRadialGradient(c.x() - 5, c.y() - 6, RADIUS * 1.4)
        grad.setColorAt(0.0, QColor("#f4fff6"))
        grad.setColorAt(0.5, QColor("#63e56f"))
        grad.setColorAt(1.0, QColor("#1f7a36"))
        p.setPen(QPen(QColor("#14401f"), 1.5))
        p.setBrush(grad)
        p.drawEllipse(c, RADIUS, RADIUS)
        # listra que gira: dá para ver que ela rola
        p.save()
        p.translate(c)
        p.rotate(math.degrees(self.angle))
        p.setPen(QPen(QColor("#14401f"), 2))
        p.drawLine(QPointF(-RADIUS * 0.8, 0), QPointF(RADIUS * 0.8, 0))
        p.restore()
        self._pinta_mira(p, c)
        p.end()

    def _pinta_mira(self, p, c):
        """Linha de mira no arraste (modo pênalti): sai da bolinha para onde o seu arraste aponta."""
        if not (self.aim_hint and self.dragging and len(self._samples) >= 2):
            return
        (_t0, x0, y0), (_t1, x1, y1) = self._samples[-2], self._samples[-1]
        dx, dy = x1 - x0, y1 - y0
        tamanho = math.hypot(dx, dy)
        if tamanho <= 2.0:
            return
        dx, dy = dx / tamanho, dy / tamanho
        p.setPen(QPen(QColor("#ffd84d"), 2, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        original = QPointF(c.x() + dx * (RADIUS + 4), c.y() + dy * (RADIUS + 4))
        ponta = QPointF(c.x() + dx * (RADIUS + 180.0), c.y() + dy * (RADIUS + 180.0))
        p.drawLine(original, ponta)
        lateral = QPointF(-dy * 6.0, dx * 6.0)      # a pontinha da flecha
        p.setBrush(QColor("#ffd84d"))
        for fim in (ponta + lateral, ponta - lateral):
            p.drawLine(QPointF(ponta), QPointF(fim))

    # ---------------- mouse ----------------

    def cancel_drag(self):
        """Some da tela (guardada, desligada, o pet escondido): larga a bolinha."""
        self.dragging = False
        self._button = None

    def _inside(self, pos):
        """Diz se o ponto está sobre a bolinha (com uma pequena margem para o dedo)."""
        return math.hypot(pos.x() - self.body.x, pos.y() - self.body.y) <= RADIUS + 4

    def mousePressEvent(self, event):
        """Começa a pegar a bolinha, se o clique foi sobre ela."""
        if event.button() != Qt.LeftButton:
            return
        pos = event.globalPosition()
        if self._inside(pos):
            self._button = event.button()
            self.dragging = True
            self._grab = (pos.x() - self.body.x, pos.y() - self.body.y)
            self._samples = [(time.monotonic(), pos.x(), pos.y())]
            self.body.vx = self.body.vy = 0.0
            self.body.grounded = False          # no ar: ao soltar, a gravidade volta a agir
            self.body.platform = None

    def mouseMoveEvent(self, event):
        """Enquanto você segura, a bolinha segue o mouse."""
        if not self.dragging:
            return
        pos = event.globalPosition()
        self.body.x = pos.x() - self._grab[0]
        self.body.y = pos.y() - self._grab[1]
        now = time.monotonic()
        self._samples = [s for s in self._samples + [(now, pos.x(), pos.y())] if now - s[0] < 0.12]
        self.place()

    def mouseReleaseEvent(self, event):
        """Solta a bolinha; a velocidade do mouse vira a força com que ela sai."""
        if not self.dragging or event.button() != self._button:
            return
        self.dragging = False
        self.last_release = time.monotonic()
        if len(self._samples) >= 2:
            t0, x0, y0 = self._samples[0]
            t1, x1, y1 = self._samples[-1]
            dt = max(t1 - t0, 1e-3)
            self.body.vx = max(-2000.0, min(2000.0, (x1 - x0) / dt))
            self.body.vy = max(-2000.0, min(2000.0, (y1 - y0) / dt))
