"""Lógica das missões: CRUD + cálculo de progresso por período."""
import time
from collections import Counter, defaultdict
from datetime import date, timedelta

import database as db
import settings

# Cache curtíssimo de list_missions(): um único refresh da tela de Missões
# chama isso ~10x (current_streak nas 3 periodicidades, progresso, pendências,
# cada card) — sem cache era uma conexão SQLite nova por chamada. Mutações
# locais furam na hora (_invalidate_missions_cache); o TTL só cobre a rajada
# de um mesmo refresh, nada persiste "velho" entre ações do usuário.
_missions_cache = None
_missions_cache_ts = 0.0
_MISSIONS_CACHE_TTL = 1.0


def _invalidate_missions_cache():
    global _missions_cache
    _missions_cache = None


FREE_FREEZE_CAP = 1
PREMIUM_FREEZE_CAP = 3  # congelamentos de sequência diária por mês (ver README > Monetização)
COMPLETION_THRESHOLD = 0.65  # sequência só conta um dia/semana/mês com pelo menos 65% das missões concluídas

# Pontos fixos por periodicidade x dificuldade — não editável pelo usuário.
POINTS = {
    "diaria":  {"facil": 1, "media": 2, "dificil": 3},
    "semanal": {"facil": 5, "media": 7, "dificil": 10},
    "mensal":  {"facil": 10, "media": 15, "dificil": 25},
}

def points_for(periodicity, difficulty):
    """.get com default: o label de pontos no popup avalia isso antes dos Spinners
    assumirem o valor padrão (fica '' por uma fração de segundo) — não pode explodir."""
    return POINTS.get(periodicity, {}).get(difficulty, 0)


def add_mission(name, periodicity, difficulty, custom_days="", instructions="", reminder_time="",
                 challenge_id="", suggestion_id="", follow_cycle=False):
    """custom_days: string tipo "0,2,4" (0=segunda) — só tem efeito em missões
    diárias, pra restringir a quais dias da semana ela vale. "" = todo dia.
    instructions: texto livre, opcional (ex.: os exercícios do treino).
    reminder_time: "HH:MM" ou "" — lembrete individual, recurso Premium.
    challenge_id: id de challenges.CHALLENGES, ou "" se não veio de um Desafio
    — grava pra sempre nessa missão (ver complete_mission > CHALLENGE_MULTIPLIER).
    suggestion_id: id de mission_suggestions.SUGGESTIONS, ou "" se não veio de
    lá — só existe pra saber quais sugestões/desafios já foram adicionados
    (ver added_suggestion_ids/added_challenge_ids, usado pro botão "+" virar
    "X" nos popups).
    follow_cycle: True = agendada "nos meus dias de folga" (ciclo pessoal
    configurado em Ajustes, ver _cycle_off_today) em vez de custom_days."""
    name = name[:1].upper() + name[1:]  # começa com maiúscula, sem mexer no resto (evita estragar siglas)
    points = points_for(periodicity, difficulty)
    conn = db.get_connection()
    cur = conn.execute(
        "INSERT INTO missions (name, periodicity, difficulty, points, custom_days, instructions, "
        "reminder_time, challenge_id, suggestion_id, follow_cycle) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, periodicity, difficulty, points, custom_days, instructions, reminder_time,
         challenge_id, suggestion_id, int(follow_cycle)),
    )
    conn.commit()
    novo_id = cur.lastrowid   # quem agenda o alarme dessa missão precisa do id
    conn.close()
    _invalidate_missions_cache()
    return novo_id


def added_suggestion_ids():
    """Ids de mission_suggestions já adicionados (pelo menos 1x) — usado pro
    popup de sugestões mostrar "X" em vez de "+" nelas."""
    conn = db.get_connection()
    rows = conn.execute("SELECT DISTINCT suggestion_id FROM missions WHERE suggestion_id != ''").fetchall()
    conn.close()
    return {r["suggestion_id"] for r in rows}


def added_challenge_ids():
    """Mesma ideia de added_suggestion_ids, pros Desafios."""
    conn = db.get_connection()
    rows = conn.execute("SELECT DISTINCT challenge_id FROM missions WHERE challenge_id != ''").fetchall()
    conn.close()
    return {r["challenge_id"] for r in rows}


def update_mission(mission_id, name, periodicity, difficulty, custom_days="", instructions="", reminder_time="",
                    follow_cycle=False):
    name = name[:1].upper() + name[1:]
    points = points_for(periodicity, difficulty)
    conn = db.get_connection()
    conn.execute(
        "UPDATE missions SET name = ?, periodicity = ?, difficulty = ?, points = ?, custom_days = ?, "
        "instructions = ?, reminder_time = ?, follow_cycle = ? WHERE id = ?",
        (name, periodicity, difficulty, points, custom_days, instructions, reminder_time,
         int(follow_cycle), mission_id),
    )
    conn.commit()
    conn.close()
    _invalidate_missions_cache()


def remove_mission(mission_id):
    conn = db.get_connection()
    conn.execute("DELETE FROM missions WHERE id = ?", (mission_id,))
    conn.commit()
    conn.close()
    _invalidate_missions_cache()


FREE_MISSION_CAP = 7
PREMIUM_MISSION_CAP = 15
FREE_MISSION_PER_LEVEL = 1
PREMIUM_MISSION_PER_LEVEL = 2


def mission_limit(is_premium):
    """Quantas missões ativas cabem: 7 grátis / 15 Premium (ver README >
    Monetização) no nível 1, +1 (grátis) ou +2 (Premium) por nível já
    desbloqueado além do 1º — level_info() já soma TODOS os pontos de
    sempre, então o limite só cresce."""
    base = PREMIUM_MISSION_CAP if is_premium else FREE_MISSION_CAP
    per_level = PREMIUM_MISSION_PER_LEVEL if is_premium else FREE_MISSION_PER_LEVEL
    return base + per_level * (level_info()["level"] - 1)


def list_missions():
    global _missions_cache, _missions_cache_ts
    now = time.monotonic()
    if _missions_cache is not None and now - _missions_cache_ts < _MISSIONS_CACHE_TTL:
        return _missions_cache
    conn = db.get_connection()
    _missions_cache = conn.execute("SELECT * FROM missions ORDER BY id").fetchall()
    conn.close()
    _missions_cache_ts = now
    return _missions_cache


def _period_start(periodicity, today):
    if periodicity == "diaria":
        return today
    if periodicity == "semanal":
        return today - timedelta(days=today.weekday())  # segunda-feira
    if periodicity == "mensal":
        return today.replace(day=1)
    raise ValueError(f"periodicidade inválida: {periodicity}")


def _cycle_off_today(today=None):
    """True se hoje é dia de folga do ciclo pessoal (ver Ajustes > Meu ciclo
    de trabalho — escalas rotativas tipo 12x36/24x48, onde o dia de folga
    NÃO é sempre o mesmo dia da semana). Sem ciclo ativo/configurado, False
    — quem trata "ciclo desligado" como "todo dia" é is_scheduled_today,
    não esta função (chamar direto com o ciclo desligado devolve False,
    não "todo dia")."""
    prefs = settings.get_settings()
    if not prefs["cycle_enabled"] or prefs["cycle_length"] <= 0 or not prefs["cycle_anchor_date"]:
        return False
    today = today or date.today()
    anchor = date.fromisoformat(prefs["cycle_anchor_date"])
    cycle_day = (today - anchor).days % prefs["cycle_length"]
    off_days = {int(d) for d in prefs["cycle_off_days"].split(",") if d}
    return cycle_day in off_days


def is_scheduled_today(mission_row, today=None):
    """False só quando é diária com dias específicos (semana OU ciclo
    pessoal) e hoje não é um deles. Todo o resto (semanal, mensal, diária
    sem restrição) vale todo dia."""
    if mission_row["periodicity"] != "diaria":
        return True
    if mission_row["follow_cycle"]:
        if not settings.get_settings()["cycle_enabled"]:
            return True  # ciclo desligado -> "todo dia", nunca esconde a missão sozinho
        return _cycle_off_today(today)
    days = mission_row["custom_days"] or ""
    if not days:
        return True
    today = today or date.today()
    return str(today.weekday()) in days.split(",")


def is_done_this_period(mission_row, today=None):
    today = today or date.today()
    last = mission_row["last_completed_date"]
    if not last:
        return False
    return date.fromisoformat(last) >= _period_start(mission_row["periodicity"], today)


MULTIPLIER_TIERS = {
    # (sequência mínima, multiplicador) — checado do maior pro menor, na
    # unidade de cada tipo: diária em dias; semanal sobe a cada 2 semanas;
    # mensal a cada mês (5 semanas/meses pro 1º degrau demorava demais)
    "diaria": [(30, 2.0), (20, 1.75), (10, 1.5), (5, 1.25)],
    "semanal": [(8, 2.0), (6, 1.75), (4, 1.5), (2, 1.25)],
    "mensal": [(4, 2.0), (3, 1.75), (2, 1.5), (1, 1.25)],
}


def streak_multiplier(streak, periodicity="diaria"):
    """Ex.: 5 dias, 2 semanas ou 1 mês de sequência garantem 1.25x pontos —
    `streak` é a sequência daquele tipo (dias/semanas/meses)."""
    for threshold, mult in MULTIPLIER_TIERS[periodicity]:
        if streak >= threshold:
            return mult
    return 1.0


def streak_next_tier(streak, periodicity="diaria"):
    """(quanto falta, multiplicador daquele degrau) pro próximo bônus, ou None
    se já está no degrau máximo — pra UI mostrar "faltam N pro próximo bônus"."""
    for threshold, mult in sorted(MULTIPLIER_TIERS[periodicity]):
        if streak < threshold:
            return threshold - streak, mult
    return None


# incentivo fixo pra quem pega um Desafio (aba Desafios) seguir fazendo
# aquelas missões — combina (multiplica) com o bônus de sequência acima
CHALLENGE_MULTIPLIER = 1.5

# bônus PERMANENTE por marco batido — ao contrário de streak_multiplier (que
# reseta se a sequência quebrar), este NUNCA some: uma vez batido o recorde,
# fica pra sempre. Ancorado nos mesmos limiares dos emblemas "grau máximo" de
# cada trilha (ver achievements.DEFINITIONS: missions_100/streak_100/level_15)
# — de propósito não importa achievements.py aqui (ela já importa este módulo;
# um import de volta criaria ciclo), os mesmos números só ficam duplicados.
# (chave, limiar, bônus) — soma os que já foram batidos, sem teto explícito
# (3 marcos hoje, +15% no máximo — dá pra somar mais linhas à vontade)
PERMANENT_BONUS_THRESHOLDS = [
    ("best_streak", 100, 0.05),
    ("total_completions", 100, 0.05),
    ("level", 15, 0.05),
]


def permanent_bonus():
    """Soma dos bônus permanentes já conquistados (0.05 = +5%), ou 0.0 se
    nenhum marco foi batido ainda. Não depende da sequência ATUAL — best_streak
    é recorde histórico, nunca diminui — então isto também nunca diminui."""
    prefs = settings.get_settings()
    stats = {
        "best_streak": prefs["best_streak"],
        "total_completions": total_completions(),
        "level": level_info()["level"],
    }
    return sum(bonus for key, threshold, bonus in PERMANENT_BONUS_THRESHOLDS
               if stats[key] >= threshold)


def complete_mission(mission_id, obs="", max_freezes_per_month=FREE_FREEZE_CAP):
    """Marca concluída para o período atual e registra no histórico (com obs
    dessa conclusão). Idempotente. Os pontos gravados já saem multiplicados
    pela sequência daquela periodicidade (recalculada incluindo esta conclusão).

    max_freezes_per_month: teto de congelamentos do usuário (None = ilimitado,
    Modo Sem Penalidade) — precisa ser o mesmo que a tela de stats usa, senão
    o multiplicador aplicado aqui fica abaixo do degrau da sequência exibida
    (ver main.CompleteMissionPopup / _freeze_cap)."""
    conn = db.get_connection()
    mission = conn.execute("SELECT * FROM missions WHERE id = ?", (mission_id,)).fetchone()
    if mission is None or is_done_this_period(mission) or not is_scheduled_today(mission):
        conn.close()
        return
    today_str = date.today().isoformat()
    conn.execute("UPDATE missions SET last_completed_date = ? WHERE id = ?", (today_str, mission_id))
    conn.execute(
        "INSERT INTO completions (mission_id, mission_name, date, points, obs, periodicity) VALUES (?, ?, ?, ?, ?, ?)",
        (mission_id, mission["name"], today_str, mission["points"], obs, mission["periodicity"]),
    )
    conn.commit()
    conn.close()
    _invalidate_missions_cache()  # mexeu em missions.last_completed_date

    streak = current_streak(periodicity=mission["periodicity"],
                            max_freezes_per_month=max_freezes_per_month)
    # permanent_bonus() já inclui ESTA conclusão pros marcos de
    # total_completions/level (leem o banco, e a linha de completions acima já
    # foi commitada) — quem bate missions_100/level_15 na hora H já ganha o
    # bônus nesta própria conclusão. Exceção: o marco de sequência (best_streak)
    # só atualiza depois, em main._refresh_stats — bater o recorde de 100 hoje
    # só conta o bônus a partir da PRÓXIMA conclusão (defasagem de uma missão,
    # inofensiva: ponytail, sem valer a pena inverter a ordem só por isso).
    multiplier = streak_multiplier(streak, mission["periodicity"]) * (1 + permanent_bonus())
    if mission["challenge_id"]:
        multiplier *= CHALLENGE_MULTIPLIER
    if multiplier != 1.0:
        final_points = round(mission["points"] * multiplier)
        conn = db.get_connection()
        conn.execute(
            "UPDATE completions SET points = ? WHERE mission_id = ? AND date = ? AND periodicity = ?",
            (final_points, mission_id, today_str, mission["periodicity"]),
        )
        conn.commit()
        conn.close()


def uncomplete_mission(mission_id):
    """Desfaz a conclusão de hoje (para permitir desmarcar o checkbox por engano)."""
    today_str = date.today().isoformat()
    conn = db.get_connection()
    conn.execute("DELETE FROM completions WHERE mission_id = ? AND date = ?", (mission_id, today_str))
    conn.execute(
        "UPDATE missions SET last_completed_date = NULL WHERE id = ? AND last_completed_date = ?",
        (mission_id, today_str),
    )
    conn.commit()
    conn.close()
    _invalidate_missions_cache()  # mexeu em missions.last_completed_date


def progress_today(periodicity=None):
    """progresso = missões concluídas no período / total de missões agendadas
    pra hoje (uma diária de dia específico não conta contra o dia errado).
    `periodicity` restringe a um tipo só — cada aba (diárias / semanais /
    mensais) mostra o progresso dela, não o geral."""
    rows = [m for m in list_missions() if is_scheduled_today(m)
            and (periodicity is None or m["periodicity"] == periodicity)]
    if not rows:
        return 0.0
    done = sum(1 for m in rows if is_done_this_period(m))
    return done / len(rows)


def pending_today():
    """Nomes das missões agendadas pra hoje que ainda faltam — usado pelo
    lembrete inteligente pra saber se vale a pena avisar (e o quê)."""
    return [m["name"] for m in list_missions() if is_scheduled_today(m) and not is_done_this_period(m)]


def _period_key(periodicity, d):
    """Agrupa uma data no período dela (o próprio dia / a segunda-feira daquela
    semana / o dia 1 daquele mês) — assim dá pra andar a sequência período a
    período em vez de sempre dia a dia."""
    if periodicity == "diaria":
        return d
    if periodicity == "semanal":
        return d - timedelta(days=d.weekday())
    if periodicity == "mensal":
        return d.replace(day=1)
    raise ValueError(f"periodicidade inválida: {periodicity}")


def _step_back(periodicity, key):
    if periodicity == "diaria":
        return key - timedelta(days=1)
    if periodicity == "semanal":
        return key - timedelta(weeks=1)
    if periodicity == "mensal":
        return (key - timedelta(days=1)).replace(day=1)  # dia 1 do mês anterior
    raise ValueError(f"periodicidade inválida: {periodicity}")


def _period_ok(done_count, total):
    """total=0 (nenhuma missão daquela periodicidade — ou nenhuma diária
    agendada naquele dia específico) não bloqueia nada: não tinha o que
    cumprir, então não conta contra a sequência."""
    return total == 0 or done_count / total >= COMPLETION_THRESHOLD


def current_streak(today=None, periodicity="diaria", max_freezes_per_month=FREE_FREEZE_CAP):
    """Períodos consecutivos (dias/semanas/meses, conforme periodicity) em que
    pelo menos COMPLETION_THRESHOLD (65%) das missões DAQUELA periodicidade
    foram concluídas — não basta mais 1 conclusão qualquer entre várias. Se o
    período atual ainda não bateu o percentual, a sequência não quebra até
    ele acabar — só olha a partir do período anterior (ainda dá tempo).

    Congelamento (buracos perdoados por mês-calendário, até max_freezes_per_month
    — None = sem limite, usado pelo Modo Sem Penalidade premium) só existe pra
    diária — não faz sentido perdoar 1 semana ou 1 mês inteiro do mesmo jeito.

    ponytail: o "total" de missões de cada período usa a lista ATUAL de
    missões (list_missions()), não um retrato histórico de quais existiam
    naquele dia/semana/mês — uma missão criada ou apagada depois muda
    retroativamente o percentual de períodos antigos também. Rastrear isso
    direito exigiria guardar quando cada missão existiu (created_at/deleted_at),
    upgrade pra se alguém sentir falta; por ora é a mesma simplificação que
    progress_today() já usa pro dia de hoje."""
    today = today or date.today()
    conn = db.get_connection()
    rows = conn.execute(
        "SELECT date, mission_id FROM completions WHERE periodicity = ?", (periodicity,)
    ).fetchall()
    completed_by_period = defaultdict(set)
    for r in rows:
        key = _period_key(periodicity, date.fromisoformat(r["date"]))
        completed_by_period[key].add(r["mission_id"])
    any_activity = set(completed_by_period)  # só pra achar a 1ª conclusão de sempre, não usa o %

    if periodicity != "diaria":
        conn.close()
        total = sum(1 for m in list_missions() if m["periodicity"] == periodicity)
        # piso igual ao da diária (ver comentário mais abaixo): sem ele, total=0
        # (nenhuma missão ativa dessa periodicidade) faz _period_ok sempre
        # devolver True e o laço nunca para, estourando o ano mínimo do date()
        earliest_done = min(any_activity) if any_activity else None

        def satisfied(key):
            if earliest_done is None or key < earliest_done:
                return False
            return _period_ok(len(completed_by_period.get(key, ())), total)

        current_key = _period_key(periodicity, today)
        key = current_key if satisfied(current_key) else _step_back(periodicity, current_key)
        streak = 0
        while satisfied(key):
            streak += 1
            key = _step_back(periodicity, key)
        return streak

    # diária: mesma lógica de sempre, com congelamento (ver docstring)
    freezes = conn.execute("SELECT month, frozen_date FROM streak_freezes").fetchall()
    freezes_used_by_month = Counter(r["month"] for r in freezes)
    frozen_dates = {date.fromisoformat(r["frozen_date"]) for r in freezes if r["frozen_date"]}
    all_diaria = [m for m in list_missions() if m["periodicity"] == "diaria"]

    def day_ok(d):
        if d in frozen_dates:
            return True  # dia já congelado conta como feito daqui pra frente
        scheduled = sum(1 for m in all_diaria if is_scheduled_today(m, today=d))
        return _period_ok(len(completed_by_period.get(d, ())), scheduled)

    # piso pro Modo Sem Penalidade (max_freezes_per_month=None): sem isso, sem
    # teto nenhum pra parar, o laço perdoaria dia atrás de dia até estourar o
    # ano mínimo do date() — não tem sentido perdoar antes da 1ª conclusão real.
    # O piso é "day < earliest_done" (não "earliest_done - 1"): um "- 1" ali
    # perdoava também o dia ANTERIOR à 1ª conclusão de todas — quem completa
    # a missão pela 1ª vez hoje via a sequência começar em 2, não 1, porque o
    # congelamento "perdoava" ontem mesmo sem nada pra perdoar (a missão nem
    # existia ainda).
    earliest_done = min(any_activity) if any_activity else None

    day = today if day_ok(today) else today - timedelta(days=1)
    streak = 0
    new_freezes = []
    while True:
        # piso checado ANTES de day_ok, não só no ramo "dia não bateu": com
        # todas as missões diárias apagadas, scheduled=0 todo dia e day_ok
        # fica sempre True (ver _period_ok) — sem checar o piso aqui também,
        # o "continue" do ramo de baixo nunca deixava o laço chegar nele, e
        # ele decrementava day pra sempre até estourar o ano mínimo do date()
        # (OverflowError, reproduzido apagando as missões e olhando a sequência).
        if earliest_done is None or day < earliest_done:
            break
        if day_ok(day):
            streak += 1
            day -= timedelta(days=1)
            continue
        month_key = day.strftime("%Y-%m")
        has_room = max_freezes_per_month is None or freezes_used_by_month[month_key] < max_freezes_per_month
        if has_room:
            # sem "só 1 por chamada": se o teto do mês permite (ou é ilimitado,
            # Modo Sem Penalidade), perdoa quantos buracos seguidos precisar —
            # senão quem só abre o app de vez em quando nunca usaria o resto
            # dos congelamentos do mês, mesmo tendo sobrado
            new_freezes.append((month_key, day.isoformat()))
            freezes_used_by_month[month_key] += 1
            streak += 1
            day -= timedelta(days=1)
            continue
        break

    if new_freezes:
        conn.executemany("INSERT OR IGNORE INTO streak_freezes (month, frozen_date) VALUES (?, ?)", new_freezes)
        conn.commit()
    conn.close()
    return streak


def streak_freeze_available(today=None, max_freezes_per_month=FREE_FREEZE_CAP):
    """True se ainda sobra congelamento pra usar este mês (None = sem limite)."""
    if max_freezes_per_month is None:
        return True
    today = today or date.today()
    month_key = today.strftime("%Y-%m")
    conn = db.get_connection()
    used = conn.execute("SELECT COUNT(*) FROM streak_freezes WHERE month = ?", (month_key,)).fetchone()[0]
    conn.close()
    return used < max_freezes_per_month


def streak_freezes_remaining(today=None, max_freezes_per_month=FREE_FREEZE_CAP):
    """Quantos congelamentos ainda sobram este mês — None = sem limite (Modo
    Sem Penalidade). Nunca negativo (usados > teto não deveria rolar, mas o
    teto pode cair no meio do mês se o Premium for desativado)."""
    if max_freezes_per_month is None:
        return None
    today = today or date.today()
    month_key = today.strftime("%Y-%m")
    conn = db.get_connection()
    used = conn.execute("SELECT COUNT(*) FROM streak_freezes WHERE month = ?", (month_key,)).fetchone()[0]
    conn.close()
    return max(0, max_freezes_per_month - used)


def total_completions():
    conn = db.get_connection()
    total = conn.execute("SELECT COUNT(*) FROM completions").fetchone()[0]
    conn.close()
    return total


LEVEL_XP_STEP = 25     # passo linear: nível N soma STEP × N
LEVEL_XP_GROWTH = 0.25  # + 25% do que o nível anterior pediu — fica mais difícil aos poucos, sem disparar
LEVEL_XP_BASE = LEVEL_XP_STEP  # nível 1 (sem nível anterior pra somar bônus) — só usado como valor
                                # inicial de exibição antes do primeiro refresh (ver main.py > xp_for_next)


def _xp_needed_for_level(level):
    """XP pra COMPLETAR esse nível (não cumulativo). Nível 1: só o passo base
    (25). Do nível 2 em diante: passo linear (25×nível) + 25% do que o nível
    anterior pediu — cresce mais rápido que uma reta pura, mas o extra nunca
    passa de 1/4 do nível anterior, então nunca dispara."""
    needed = LEVEL_XP_STEP
    for n in range(2, level + 1):
        needed = LEVEL_XP_STEP * n + LEVEL_XP_GROWTH * needed
    return round(needed)


def level_info():
    """Nível deriva da soma de TODOS os pontos já ganhos (histórico completo, não
    só o mês). Cada nível pede mais XP que o anterior (ver _xp_needed_for_level)
    — os limiares são cumulativos: nível 2 começa em 25 XP, nível 3 em 25+56=81,
    nível 4 em 81+89=170..."""
    conn = db.get_connection()
    total = conn.execute("SELECT COALESCE(SUM(points), 0) as total FROM completions").fetchone()[0]
    conn.close()
    level = 1
    xp_in_level = total
    xp_needed = _xp_needed_for_level(level)
    while xp_in_level >= xp_needed:
        xp_in_level -= xp_needed
        level += 1
        xp_needed = _xp_needed_for_level(level)
    return {
        "total_xp": total,
        "level": level,
        "xp_in_level": xp_in_level,
        "xp_for_next": xp_needed,
        "progress": xp_in_level / xp_needed,
    }
