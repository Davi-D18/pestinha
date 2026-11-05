"""
SONHO - ao acordar, ele costura o que viveu num "sonho" e vai contar.

O enredo vem da memória episódica de verdade: atividade, emoção e como
cada episódio terminou, mais um tempero de valência (média acima de 0 é
contente, bem abaixo é magoado). Sem episódios guardados, não conta nada:
sonho vazio não fica bom.
"""

import random

from ..ajustes import SONHO_CHANCE

ATIVIDADES = {"PROGRAMMING": "programando", "DESIGNING": "desenhando", "GAMING": "jogando",
              "BROWSING": "vendo páginas", "MUSIC": "com música tocando", "IDLE": "vagando pela tela",
              "AWAY": "distante"}
ACOES = {"meme": "soltei um meme na sua cara", "foto": "mostrei uma fotinha sua",
         "bilhete": "colei um bilhete enorme", "atravessar": "atravessei a tela voando",
         "nada": "só andei por aí"}
ABERTURAS = ("Sonhei que ", "No sonho, ", "Tive um sonho que ")
FELIZ = ("Acordei contente.", "Acordei com o peito quentinho.")
MAGOADO = ("Acordei meio magoado.", "Acordei resmungando comigo mesmo.")


def _atividade_frase(atividade):
    """Nome legível da atividade do contexto ('PROGRAMMING' -> 'programando')."""
    return ATIVIDADES.get(atividade, "vagando pela tela")


def _acao_frase(ep):
    """O que ele fez no episódio, contado no mesmo tom do resto do sonho."""
    acao = (ep.get("acao") or "").split("_")[0]
    return ACOES.get(acao, "andei uns arrastões pela tela")


def _resultado_frase(ep):
    """Como o episódio acabou, virado frase curta; sem resultado claro, nada a acrescentar."""
    resultado = ep.get("resultado") or ""
    if "dispensado" in resultado:
        return " — mas você me dispensou sem ler"
    if "castigo" in resultado:
        return " — e no sonho o castigo veio igual"
    if "atenção" in resultado or "carinho" in resultado:
        return " — e você me consolou logo depois"
    return ""


def _media_valencia(episodios):
    """Humor do sonho pela valência média; sem valências definidas, neutro."""
    valores = [ep.get("valencia", 0.0) for ep in episodios]
    if not valores:
        return 0.0
    return sum(valores) / len(valores)


def contar(memory, chance=None):
    """Monta o texto do sonho a partir da memória episódica; texto vazio = não contar.

    None usa o ajuste SONHO_CHANCE; testes passam um valor certo.
    """
    chance = SONHO_CHANCE if chance is None else chance
    episodios = [ep for ep in memory.recent if ep.get("contexto") and ep.get("acao")]
    if len(episodios) < 2 or random.random() >= chance:
        return ""
    escolhidos = random.sample(episodios, min(3, len(episodios)))
    frases = []
    for ep in escolhidos:
        atividade, _ = (ep.get("contexto") or "|").split("|", 1)
        frases.append(random.choice(ABERTURAS)
                      + f"você estava {_atividade_frase(atividade)} "
                      f"e eu {_acao_frase(ep)}{_resultado_frase(ep)}.")
    humor = FELIZ if _media_valencia(escolhidos) > 0.2 else MAGOADO
    return " ".join(frases) + " " + random.choice(humor)
