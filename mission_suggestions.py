"""Biblioteca de missões sugeridas, pra não começar com a lista vazia. Só o
"esqueleto" (periodicidade/dificuldade) mora aqui — o nome traduzido de cada
uma vive em i18n.py na chave "sugg_<id>_name" (são textos de menu, não dado
digitado pelo usuário, então fazem parte da tradução normal da interface)."""

SUGGESTIONS = [
    {"id": "water", "periodicity": "diaria", "difficulty": "facil"},
    {"id": "read", "periodicity": "diaria", "difficulty": "facil"},
    {"id": "exercise", "periodicity": "diaria", "difficulty": "media"},
    {"id": "meditate", "periodicity": "diaria", "difficulty": "facil"},
    {"id": "sleep", "periodicity": "diaria", "difficulty": "facil"},
    {"id": "journal", "periodicity": "diaria", "difficulty": "facil"},
    {"id": "clean", "periodicity": "semanal", "difficulty": "media"},
    {"id": "groceries", "periodicity": "semanal", "difficulty": "facil"},
    {"id": "review_week", "periodicity": "semanal", "difficulty": "facil"},
    {"id": "call_family", "periodicity": "semanal", "difficulty": "facil"},
    {"id": "budget", "periodicity": "mensal", "difficulty": "media"},
    {"id": "declutter", "periodicity": "mensal", "difficulty": "media"},
    {"id": "goals", "periodicity": "mensal", "difficulty": "media"},
]


def get(sugg_id):
    return next((s for s in SUGGESTIONS if s["id"] == sugg_id), None)
