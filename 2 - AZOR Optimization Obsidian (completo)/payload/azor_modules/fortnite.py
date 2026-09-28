from __future__ import annotations

MODULE = {
    "id": "fortnite",
    "label": "Fortnite",
    "description": "Configurações do jogo ficam em ações dedicadas com backup e releitura; o one-click não força preset gráfico.",
    "automatic": False,
}


def tasks():
    # Deliberately manual. Resolution/rendering preferences vary by player and
    # hardware; forcing them in one-click can be a regression.
    return []
