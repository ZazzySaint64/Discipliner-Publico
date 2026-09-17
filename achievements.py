"""Emblemas/conquistas — derivados dos números que já existem (sequência recorde,
missões concluídas, nível). Não guarda "desbloqueado" à parte: é recalculado a
partir do estado atual toda vez, então nunca fica dessincronizado."""
import missions
import settings

DEFINITIONS = [
    {"id": "first_mission", "check": lambda s: s["total_completions"] >= 1},
    {"id": "streak_3", "check": lambda s: s["best_streak"] >= 3},
    {"id": "streak_7", "check": lambda s: s["best_streak"] >= 7},
    {"id": "streak_14", "check": lambda s: s["best_streak"] >= 14},
    {"id": "streak_30", "check": lambda s: s["best_streak"] >= 30},
    {"id": "streak_100", "check": lambda s: s["best_streak"] >= 100},
    {"id": "streak_semanal_4", "check": lambda s: s["best_streak_semanal"] >= 4},
    {"id": "streak_mensal_3", "check": lambda s: s["best_streak_mensal"] >= 3},
    {"id": "missions_10", "check": lambda s: s["total_completions"] >= 10},
    {"id": "missions_50", "check": lambda s: s["total_completions"] >= 50},
    {"id": "missions_100", "check": lambda s: s["total_completions"] >= 100},
    {"id": "level_5", "check": lambda s: s["level"] >= 5},
    {"id": "level_10", "check": lambda s: s["level"] >= 10},
    {"id": "level_15", "check": lambda s: s["level"] >= 15},
    # não é baseado em progresso, e sim na compra do Premium (ver README > Monetização)
    # — fica por último de propósito, não é a primeira coisa que um usuário novo vê
    {"id": "supporter", "check": lambda s: s["is_premium"]},
    # degraus do multiplicador de pontos por sequência (ver missions.MULTIPLIER_TIERS)
    # — caminho NOVO (além de sequência/nível) pra ganhar moldura/ícone do app,
    # igual às poses acima: emblema desbloqueia, sem precisar de missão marcada
    # nenhuma (ver mascot.FRAMES > requires)
    {"id": "streak_multiplier_125", "check": lambda s: s["best_streak"] >= 5},
    {"id": "streak_multiplier_150", "check": lambda s: s["best_streak"] >= 10},
    {"id": "streak_multiplier_175", "check": lambda s: s["best_streak"] >= 20},
    {"id": "streak_multiplier_200", "check": lambda s: s["best_streak"] >= 30},
]


def status():
    """Lista de {id, unlocked} pra cada emblema definido, na ordem de DEFINITIONS."""
    prefs = settings.get_settings()
    stats = {
        "best_streak": prefs["best_streak"],
        "best_streak_semanal": prefs["best_streak_semanal"],
        "best_streak_mensal": prefs["best_streak_mensal"],
        "total_completions": missions.total_completions(),
        "level": missions.level_info()["level"],
        "is_premium": prefs["is_premium"],
    }
    return [{"id": d["id"], "unlocked": d["check"](stats)} for d in DEFINITIONS]
