"""
COMIDA - biscoito, café ou água: você oferece pelo menu ("Oferecer biscoito", "Servir o café",
"Água fresca"), e ele sente, chega e toma.

Física e arraste herdados da bolinha (body/bolinha.py); aqui só muda os nomes e o tipo.
Cada tipo tem reação própria do app (biscoito: energia; café: energia + nervosinho;
água: assenta). Quando ele alcança a comida, o app a recolhe e vira o efeito na homeostase.
"""

from ..body.bolinha import Ball


class Comida(Ball):
    """Comida/bebida arrastável: chute e arraste valem, mas o objetivo é ele tomar."""

    def __init__(self, x, y, tipo="biscoito", sprite=None):
        """Cria a comida em (x, y); `tipo` é "biscoito", "cafe" ou "agua"."""
        self.tipo = tipo
        super().__init__(x, y, kind="comida", sprite=sprite)
