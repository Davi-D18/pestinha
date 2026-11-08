"""
JOGO - o modo companhia: você abre um jogo e ele pega o controle para assistir.

Só o timing mora aqui. Detecção vem do app (o jogo em primeiro plano está na lista
de jogos das configurações) e a execução também (pulinho, cara, desenho do controle).
Ele NÃO vê o jogo (nunca lê conteúdo de janela): o que "acontece no jogo" chega como
o SEU input — teclas e cliques rápidos são o pico de ação, e o silêncio longo é a
hora do cochilo.
"""

import random

from ..ajustes import (
    JOGO_AFK_COCHILO,
    JOGO_CHANCE_REACAO,
    JOGO_CONTROLE_EM,
    JOGO_PAUSA_REACAO,
    JOGO_PICO_FRACAO,
    JOGO_PICO_JANELA,
    JOGO_RECOLHER,
)


class JogoController:
    """Estado do modo companhia de jogo: quando entra, reage ao seu input, cochila e recolhe."""

    def __init__(self, debug):
        """Começa de fora do jogo, sem controle e sem cochilo."""
        self.debug = debug
        self.modo = False            # acompanha um jogo em andamento
        self.controle = False        # o controle já está na pata
        self.cochilando = False      # você sumiu por muitos minutos: bocejo e cochilo
        self._festa = None           # quando a festa da entrada deixou ficar de vez
        self._recolher_em = None     # quando o jogo ficar ausente de vez
        self._entradas = []          # (instante, ativo) do seu input (janela do pico)
        self._proxima_reacao = 0.0   # respiro entre reações de pico

    def tick(self, agora, jogando, input_ativo, afk_segundos, livre):
        """Um passo do modo (o app chama a cada 100 ms); devolve os eventos para o pet.

        jogando: um jogo da lista está em primeiro plano agora.
        input_ativo: você mexeu em teclado ou mouse neste instante.
        afk_segundos: medidos pela plataforma; 0.0 quando não dá para medir.
        livre: nada vem na frente (dormindo, cantinho, Tacinho, missão, no ar) — o modo
        não se recolhe nesse caso: fica esperando, porque o jogo continua lá.
        """
        eventos = []
        self._entradas.append((agora, input_ativo))
        limite = agora - JOGO_PICO_JANELA
        self._entradas = [item for item in self._entradas if item[0] >= limite]

        if not jogando:
            self._festa = None
            self._entradas = []
            if self.modo and self._recolher_em is None:
                self._recolher_em = agora + JOGO_RECOLHER
            elif self.modo and self._recolher_em is not None and agora >= self._recolher_em:
                self._recolher("acabou a partida")
                eventos.append("soltou")
            return eventos

        self._recolher_em = None
        if self.cochilando:
            if input_ativo:
                self.cochilando = False
                self.controle = True             # pega o controle de volta
                eventos.append("acordou")        # você voltou
            return eventos
        if not livre:
            if self.modo:
                self._recolher("algo na frente do modo")
                eventos.append("soltou")
            return eventos

        if not self.modo:
            if self._festa is None:
                self._festa = agora
                eventos.append("festejar")       # o jogo entrou: pulinho de "vamos jogar!"
            elif agora - self._festa >= JOGO_CONTROLE_EM:
                self.modo = True
                self.controle = True
                eventos.append("pegou_controle")
            return eventos

        # ----- no jogo: pico de ação (o seu input passa da fração na janela) -----
        ativos = sum(1 for _t, ativo in self._entradas if ativo)
        cheio = len(self._entradas) >= 10 and ativos / len(self._entradas) >= JOGO_PICO_FRACAO
        if cheio and agora >= self._proxima_reacao and random.random() < JOGO_CHANCE_REACAO:
            self._proxima_reacao = agora + JOGO_PAUSA_REACAO
            eventos.append("pico")
        elif not input_ativo and afk_segundos >= JOGO_AFK_COCHILO:
            self.cochilando = True
            self.controle = False                # o controle fica no colo
            eventos.append("cochilar")
        return eventos

    def _recolher(self, motivo):
        """Recolhe tudo de uma vez (o modo, o controle e o cochilo)."""
        self.modo = False
        self.controle = False
        self.cochilando = False
        self._festa = None
        self._recolher_em = None
        if self.debug():
            from ..log import log
            log(f"[jogo] recolheu ({motivo})")
