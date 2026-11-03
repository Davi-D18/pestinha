"""
PRESENTE - a caixinha-surpresa: você dá pelo menu ("Dar um presente"), ele chega e abre.

Física e arraste herdados da bolinha (body/bolinha.py); aqui só muda o desenho e o nome.
Quando ele alcança a caixinha, o app a abre e a surpresa é sorteada: festa, bilhete
engraçado ou cara triste (que também é dela: nem todo presente agrada).
"""

from ..body.bolinha import Ball


class Presente(Ball):
    """Caixinha arrastável: o objetivo é ele abrir; o resultado é sorteio da caixa."""

    def __init__(self, x, y, sprite=None):
        super().__init__(x, y, kind="presente", sprite=sprite)
