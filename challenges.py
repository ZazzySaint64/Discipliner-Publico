"""Desafios: pacotes temáticos de missões pra adicionar todas de uma vez, com
1 toque. Reaproveita mission_suggestions.py pra periodicidade/dificuldade de
cada missão do pacote — aqui só existe o agrupamento (não duplica dado).

ponytail: isto NÃO é um desafio com prazo (sem "30 dias e expira sozinho") —
seria um sistema à parte com estado próprio (data de início, progresso do
desafio, o que acontece ao terminar). O que existe hoje é o jeito rápido de
começar um conjunto de missões relacionadas; upgrade pra prazo real quando
o usuário pedir, guardando started_at por desafio numa tabela nova."""

CHALLENGES = [
    {"id": "fitness", "mission_ids": ["exercise", "water", "sleep"]},
    {"id": "focus", "mission_ids": ["meditate", "journal", "review_week"]},
    {"id": "home", "mission_ids": ["clean", "groceries", "declutter"]},
    {"id": "finance", "mission_ids": ["budget", "goals", "review_week"]},
    {"id": "mind", "mission_ids": ["read", "journal", "meditate"]},
    {"id": "connections", "mission_ids": ["call_family", "review_week"]},
    {"id": "reset", "mission_ids": ["sleep", "declutter", "journal"]},
]


def get(challenge_id):
    return next((c for c in CHALLENGES if c["id"] == challenge_id), None)
