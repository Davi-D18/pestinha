"""
PENALTI - arremessa a bolinha nele: goleiro desconfiado, gol em festa, defesa em cartaz.

Você liga o pênalti pelo menu; ele fica de goleiro parado no chão. Ao soltar a
bolinha com força, ele escolhe o pulinho pelo histórico de miras: se você sempre
arremessa para o mesmo lado, ele desconfia e antecipa. A bolinha batendo nele é
defesa (cartaz); passando por trás dele, no chão, é gol (fogos de artifício).
"""

import math
import random

from ..ajustes import PENALTI_FORCA_ARREMESSO
from ..store import read_json, write_json

DESVIO_PADRAO = {"esquerda": 0, "direita": 0}
DEFESAS_CARTAZ = ("NÃO PASSA!", "DEFENDEU!", "NA TRAVE!")


class PenaltiController:
    """Estado da partida: se está ativo, o arremesso em andamento e o histórico de miras."""

    def __init__(self, path):
        """Lê o histórico de miras; arquivo ruim volta zerado (a desconfiança recomeça)."""
        self.path = path
        data = read_json(path, default=DESVIO_PADRAO)
        padrão = dict(DESVIO_PADRAO)
        if isinstance(data, dict):
            for chave in ("esquerda", "direita"):
                valor = data.get(chave, 0)
                if type(valor) is int and valor >= 0:
                    padrão[chave] = valor
        self.miras = padrão
        self.ativo = False
        self.arremesso = None        # {"lado", "resolvido", "mergulhou", "mergulho_em", "t0"}
        self._ultimo_release = -1e9

    def salvar(self):
        """Grava o histórico de miras; erro só vira log."""
        try:
            write_json(self.path, self.miras)
        except OSError:
            pass

    def lado_da_desconfianca(self, lado_visto):
        """O lado do pulinho do goleiro, pelo histórico: 1 = direita, -1 = esquerda.

        Sem histórico é sorte; com marca de sempre em um lado (>= 60%), ele
        desconfia e antecipa esse lado ('você sempre mira aqui')."""
        total = self.miras["esquerda"] + self.miras["direita"]
        if total < 2:
            return random.choice((-1, 1))
        favor = 1 if self.miras["direita"] >= self.miras["esquerda"] else -1
        if max(self.miras["esquerda"], self.miras["direita"]) / total >= 0.6:
            return favor
        return random.choice((-1, 1)) if random.random() < 0.6 else -favor

    def registrar_arremesso(self, agora, vx, distancia):
        """Você soltou a bolinha com força: arma o momento do pulinho do goleiro.

        Devolve True se virou arremesso válido (mira contada e goleiro avisado)."""
        if abs(vx) < PENALTI_FORCA_ARREMESSO:
            return False
        self.miras["esquerda" if vx < 0 else "direita"] += 1
        self.salvar()
        tempo = distancia / max(240.0, abs(vx))
        self.arremesso = {"lado_visto": 1 if vx > 0 else -1, "mergulhou": False,
                          "mergulho_em": agora + tempo * 0.5 + 0.06, "resolvido": False,
                          "t0": agora}
        return True

    def tick(self, agora, bola, corpo, chao, alcance_gol, altura_gol, colisao, vida):
        """Um passo do jogo: devolve ('dive', lado), ('defesa',), ('gol',) ou None."""
        lancou = bola.last_release != self._ultimo_release
        self._ultimo_release = bola.last_release
        if lancou and self.ativo and not bola.dragging:
            self.registrar_arremesso(agora, bola.body.vx, abs(corpo.x - bola.body.x))
        if not self.ativo:
            return None
        r = self.arremesso
        if r is None:
            return None
        if bola.dragging:
            self.arremesso = None                       # você pegou a bolinha denovo: bola no pano
            return None
        if not r["resolvido"] and agora - r["t0"] > vida:
            self.arremesso = None
            return None
        if not r["mergulhou"] and agora >= r["mergulho_em"]:
            r["mergulhou"] = True
            return ("dive", self.lado_da_desconfianca(r["lado_visto"]))
        if r["resolvido"]:
            return None
        perto = math.hypot(bola.body.x - corpo.x, bola.body.y - corpo.y) < colisao
        if perto:
            self.arremesso = None                       # defendeu: fim da jogada
            return ("defesa",)
        passou_de_lado_and_chao = (abs(bola.body.x - corpo.x) > alcance_gol
                                   and bola.body.y > chao - altura_gol
                                   and (bola.body.x - corpo.x) * r["lado_visto"] > 0)
        if passou_de_lado_and_chao:
            self.arremesso = None
            return ("gol",)
        return None

    def encerrar(self):
        """Desliga o modo e limpa a jogada em andamento."""
        self.ativo = False
        self.arremesso = None
