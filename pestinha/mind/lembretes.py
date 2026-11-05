"""
LEMBRETES - recados com horário: você deixa, na hora ele cutuca e cola.

Guarda em memory/lembretes.json (apagável junto com os dados do pet). A
lista vive em RAM e grava a cada mudança; o disco é a fonte da verdade na
próxima sessão.
"""

import time

from ..log import log
from ..store import read_json, write_json


class Lembretes:
    """Lista de recados com horário; quantos estão vencidos e o próximo a tocar."""

    def __init__(self, path):
        """Lê o arquivo; lista corrompida volta vazia (o pet esquece em vez de travar)."""
        self.path = path
        data = read_json(path, default=[])
        self.recados = data if isinstance(data, list) else []

    def adicionar(self, texto, quando):
        """Grva um recado; texto vazio ou hora sem sentido não entra."""
        if not (texto and texto.strip()) or quando <= time.time():
            return False
        self.recados.append({"texto": texto.strip(), "quando": round(float(quando), 3)})
        self.recados.sort(key=lambda r: r["quando"])
        self.salvar()
        return True

    def vencer(self):
        """O próximo recado vencido (e o retira da lista), ou None se não há."""
        agora = time.time()
        for item in self.recados:
            if item.get("quando", agora + 1) <= agora and item.get("texto"):
                self.recados.remove(item)
                self.salvar()
                return item["texto"]
        return None

    def salvar(self):
        """Grava o estado; erro só vira log (o pet continua rodando)."""
        try:
            write_json(self.path, self.recados)
        except OSError as error:
            log(f"[lembretes] não salvou o arquivo: {error}")
