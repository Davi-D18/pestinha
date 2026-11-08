"""
REBATE - a brincadeira de tocar a bolinha de canto em canto.

No rali, ele corre atrás da bolinha, PEGA (carrega no pé), leva até um canto e
chuta de volta para o outro lado — com um pulinho de chute. Você rebate com o
estilingue: clica na bolinha, arrasta na direção que quer e solta (a força e a
direção do arraste são o chute de volta; com mais precisão do que passar o
ponteiro por cima). Ela repousa em alguma banda, ele corre atrás de novo e o
rali segue até você desligar pelo menu. De vez em quando (nada frequente), ele
levanta uma placa com mensagem: as placas de sempre (SignThing), que saem
sozinhas depois de um instante ou no clique.

Dentro do rali o ponteiro NÃO empurra a bolinha — o chute de vocês agora é o
arraste, que não merece ser derrubado por um toque casual do cursor.

As frases da placa vêm do cartazes.txt do pet (seção [brincadeira]); sem a
seção, valem as frases neutras. O chutão dele é calculado pela física da
bolinha (não é um número fixo): a velocidade que faz ela andar REBATE_ALCANCE
do caminho até a parede oposta, valendo o voo (o arco) e o rolar depois de pousar.
"""

import random

from ..ajustes import (
    ATRITO_CHAO,
    GRAVIDADE,
    RAIO_BOLINHA,
    REBATE_ALCANCE,
    REBATE_ARCO,
    REBATE_PLACA_CHANCE,
    REBATE_PLACA_PAUSE,
)
from ..core.protesto import load_signs
from ..log import log

CANTO_MARGEM = 130.0        # px da parede: onde ele fica no canto
PESCAR = 52.0               # px: distância dele à bolinha na hora de pescar
CHEGOU = 60.0               # px: distância que conta "ele está no canto"
DECEL_BOLA = 400.0          # px/s: a bolinha quase parada vale pegar

FRASES_PADRAO = ["VAI!", "BOA!", "MANDA MAIS!", "TOCA DE NOVO!", "QUASE!"]


def forca_do_toco(alcance):
    """Velocidade do toco para a bolinha andar `alcance` px de caminho.

    O caminho valendo é o voo (o arco, com a gravidade de sempre) mais o rolar
    no chão (o atrito come a velocidade: ela anda ~v/atrito até parar)."""
    no_ar = 2.0 * abs(REBATE_ARCO) / GRAVIDADE
    no_rolar = 1.0 / ATRITO_CHAO
    return alcance / max(1e-3, no_ar + no_rolar)


class RebateController:
    """Estado do rali: correr atrás, pescar, levar ao canto, chutar e a placa ocasional."""

    def __init__(self, debug, signs_path):
        """Fora do modo: esperando, sem canto e sem placa."""
        self.debug = debug
        self.signs_path = signs_path
        self.ativo = False
        self.fase = "espera"     # espera (você joga) -> correr -> levar -> (chute) -> espera
        self.lado = 0            # -1 = canto esquerdo, 1 = canto direito (a vez atual)
        self.canto_x = 0.0       # o x do canto de onde ele chuta
        self._ultimo_release = -1e9   # o soltar da sua jogada (o estilingue)
        self._procura_placa = 0.0     # quando a próxima placa pode sair

    def comecar(self, agora):
        """Liga o modo: o canto DELE é sorteado uma vez e fica fixo até o fim do rali."""
        self.ativo = True
        self.fase = "correr"
        self.lado = random.choice((-1, 1))                 # o lado fixo do rali inteiro
        self._procura_placa = agora + REBATE_PLACA_PAUSE
        if self.debug():
            log(f"[rebate] começou: ele fica no canto {'esquerdo' if self.lado < 0 else 'direito'}")

    def encerrar(self):
        """Desliga o modo (a bolinha deixa de ser carregada; o app recolhe a placa)."""
        self.ativo = False
        self.fase = "espera"
        self.lado = 0
        self.canto_x = 0.0

    def frase(self):
        """Uma mensagem de placa: da seção [brincadeira] do cartazes.txt (ou as neutras)."""
        frases = load_signs(self.signs_path).get("brincadeira") or FRASES_PADRAO
        return random.choice(frases)

    def tick(self, agora, corpo, bola, chao, esquerda, direita, livre):
        """Um passo do rali (16 ms).

        Devolve (alvo_x, eventos): `alvo_x` é para onde o pet deve deslizar (None
        parado no canto) e `eventos` traz ("tocou",) e ("placa", texto) para o app
        aplicar. `livre` falso (dormindo, no ar, segurado, de castigo...) deixa a
        bolinha no chão: o rali recomeça na sua próxima jogada."""
        eventos = []
        if not self.ativo or not livre:
            bola.carried = False                  # desiste do colo: a bolinha vai pro chão
            self.fase = "espera"
            if not self.ativo:
                return None, eventos
            return None, eventos
        if bola.dragging:                         # você pegou a bolinha: o estilingue está na mão
            bola.carried = False
            self.fase = "espera"
            self._ultimo_release = bola.last_release
            return None, eventos

        alvo = None
        soltou = bola.last_release != self._ultimo_release    # um novo soltar é uma jogada sua
        self._ultimo_release = bola.last_release
        if soltou:
            self.fase = "correr"                             # correu atrás da sua devolução
        elif self.fase == "espera":
            perto = (bola.body.grounded and abs(corpo.x - bola.body.x) < PESCAR
                     and abs(bola.body.vx) < DECEL_BOLA)     # ela veio até ele: pega do mesmo jeito
            if perto:
                self.fase = "correr"

        if self.fase == "correr":
            alvo = bola.body.x                               # atrás da bolinha
            pegavel = (bola.body.grounded and abs(corpo.x - bola.body.x) < PESCAR
                       and abs(bola.body.vx) < DECEL_BOLA)   # ela quase parou: pesca
            if corpo.grounded and pegavel:
                bola.carried = True
                bola.body.vx = bola.body.vy = 0.0
                self.canto_x = (esquerda + CANTO_MARGEM if self.lado < 0
                                else direita - CANTO_MARGEM)  # SEMPRE o canto fixo dele
                self.fase = "levar"
                if self.debug():
                    log("[rebate] pegou a bolinha")
        if self.fase == "levar":
            alvo = self.canto_x                              # o colo desliza até o canto
            direcao_caminho = 1 if self.canto_x > corpo.x else -1
            ex, _ey = corpo.extents()
            bola.body.x = corpo.x + direcao_caminho * (ex + RAIO_BOLINHA + 3.0)
            bola.body.y = chao - RAIO_BOLINHA
            bola.body.vx = bola.body.vy = 0.0
            if abs(corpo.x - self.canto_x) < CHEGOU and corpo.grounded:
                meio = (esquerda + direita) / 2.0
                lado_do_toco = -1 if self.canto_x > meio else 1     # para o canto OPOSTO (do lado do canto dele)
                alcance = abs((direita - CANTO_MARGEM - 60.0) - (esquerda + CANTO_MARGEM + 60.0))
                bola.body.x = corpo.x + lado_do_toco * (ex + RAIO_BOLINHA + 6.0)
                bola.body.y = chao - RAIO_BOLINHA
                bola.kick(lado_do_toco * forca_do_toco(alcance * REBATE_ALCANCE), REBATE_ARCO)
                eventos.append("tocou")                      # o app faz o pulinho de chute
                if agora >= self._procura_placa and random.random() < REBATE_PLACA_CHANCE:
                    self._procura_placa = agora + REBATE_PLACA_PAUSE
                    eventos.append(("placa", self.frase()))
                self.fase = "espera"                         # e espera a sua devolução
                if self.debug():
                    log("[rebate] chutou de volta")
        return alvo, eventos
