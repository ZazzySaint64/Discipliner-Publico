"""Dados do calendário-mapa de calor mensal. O desenho em si é feito direto no
canvas do Kivy (ver heatmap.py) — aqui só monta os números que ele precisa."""
import calendar
from datetime import date, timedelta

import database as db
import i18n


def monthly_heatmap_data(today=None, lang=i18n.DEFAULT_LANGUAGE):
    today = today or date.today()
    conn = db.get_connection()
    rows = conn.execute(
        "SELECT date, SUM(points) as total FROM completions WHERE date LIKE ? GROUP BY date",
        (f"{today.year:04d}-{today.month:02d}-%",),
    ).fetchall()
    conn.close()

    points_by_day = {int(r["date"][-2:]): r["total"] for r in rows}
    # int(): no Python 3.12+ o calendar retorna um enum (calendar.Day), não int puro
    weekday, n_days = calendar.monthrange(today.year, today.month)
    first_weekday, days_in_month = int(weekday), int(n_days)

    return {
        "points_by_day": points_by_day,
        "days_in_month": days_in_month,
        "first_weekday": first_weekday,
        "today_day": today.day,
        "month_label": f"{i18n.MONTHS.get(lang, i18n.MONTHS[i18n.DEFAULT_LANGUAGE])[today.month - 1]}/{today.year}",
        "total_points": sum(points_by_day.values()),
    }


def weekly_summary(today=None, lang=i18n.DEFAULT_LANGUAGE):
    """Recap dos últimos 7 dias (hoje incluso) contra os 7 dias anteriores —
    pontos totais, melhor dia e variação percentual."""
    today = today or date.today()
    conn = db.get_connection()

    def points_by_date(start, end):
        rows = conn.execute(
            "SELECT date, SUM(points) as total FROM completions WHERE date BETWEEN ? AND ? GROUP BY date",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        return {r["date"]: r["total"] for r in rows}

    this_week = points_by_date(today - timedelta(days=6), today)
    last_week = points_by_date(today - timedelta(days=13), today - timedelta(days=7))
    conn.close()

    this_total = sum(this_week.values())
    last_total = sum(last_week.values())
    best_date = max(this_week, key=this_week.get) if this_week else None
    letters = i18n.WEEKDAYS.get(lang, i18n.WEEKDAYS[i18n.DEFAULT_LANGUAGE])
    best_day_label = letters[date.fromisoformat(best_date).weekday()] if best_date else ""

    if last_total > 0:
        change_pct = round((this_total - last_total) / last_total * 100)
    elif this_total > 0:
        change_pct = 100
    else:
        change_pct = 0

    return {
        "total_points": this_total,
        "best_day_label": best_day_label,
        "best_day_points": this_week.get(best_date, 0) if best_date else 0,
        "change_pct": change_pct,
    }


def monthly_summary(today=None, lang=i18n.DEFAULT_LANGUAGE):
    """Igual a weekly_summary, mas janela de 30 dias corridos em vez de 7 —
    dia corrido (não mês de calendário) pra ficar consistente com a mesma
    lógica de comparação, só a janela muda de tamanho."""
    today = today or date.today()
    conn = db.get_connection()

    def points_by_date(start, end):
        rows = conn.execute(
            "SELECT date, SUM(points) as total FROM completions WHERE date BETWEEN ? AND ? GROUP BY date",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        return {r["date"]: r["total"] for r in rows}

    this_month = points_by_date(today - timedelta(days=29), today)
    last_month = points_by_date(today - timedelta(days=59), today - timedelta(days=30))
    conn.close()

    this_total = sum(this_month.values())
    last_total = sum(last_month.values())
    best_date = max(this_month, key=this_month.get) if this_month else None
    best_day_label = date.fromisoformat(best_date).strftime("%d/%m") if best_date else ""

    if last_total > 0:
        change_pct = round((this_total - last_total) / last_total * 100)
    elif this_total > 0:
        change_pct = 100
    else:
        change_pct = 0

    return {
        "total_points": this_total,
        "best_day_label": best_day_label,
        "best_day_points": this_month.get(best_date, 0) if best_date else 0,
        "change_pct": change_pct,
    }


# --- Estatísticas avançadas (Premium — ver README > Monetização) ---

def mission_performance():
    """Conclusões e pontos totais por missão (todo o histórico), da mais
    praticada pra menos — usa mission_name (não mission_id) de propósito,
    igual ao histórico: sobrevive mesmo se a missão for editada/apagada depois."""
    conn = db.get_connection()
    rows = conn.execute(
        "SELECT mission_name, COUNT(*) as completions, SUM(points) as points "
        "FROM completions GROUP BY mission_name ORDER BY completions DESC"
    ).fetchall()
    conn.close()
    return [{"name": r["mission_name"], "completions": r["completions"], "points": r["points"]} for r in rows]


def best_weekday_alltime(lang=i18n.DEFAULT_LANGUAGE):
    """Dia da semana com mais pontos somados em todo o histórico, ou None
    se ainda não há nenhuma conclusão registrada."""
    conn = db.get_connection()
    rows = conn.execute("SELECT date, SUM(points) as total FROM completions GROUP BY date").fetchall()
    conn.close()
    if not rows:
        return None
    totals = [0] * 7
    for r in rows:
        totals[date.fromisoformat(r["date"]).weekday()] += r["total"]
    best = max(range(7), key=lambda i: totals[i])
    letters = i18n.WEEKDAYS.get(lang, i18n.WEEKDAYS[i18n.DEFAULT_LANGUAGE])
    return {"label": letters[best], "points": totals[best]}


def last_months_totals(n=6, today=None, lang=i18n.DEFAULT_LANGUAGE):
    """Pontos totais dos últimos n meses de calendário (mais antigo primeiro)."""
    today = today or date.today()
    months_names = i18n.MONTHS.get(lang, i18n.MONTHS[i18n.DEFAULT_LANGUAGE])
    year, month = today.year, today.month
    targets = []
    for offset in range(n - 1, -1, -1):
        m = month - offset
        y = year
        while m <= 0:
            m += 12
            y -= 1
        targets.append((y, m))

    conn = db.get_connection()
    result = []
    for y, m in targets:
        row = conn.execute(
            "SELECT COALESCE(SUM(points), 0) as total FROM completions WHERE date LIKE ?",
            (f"{y:04d}-{m:02d}-%",),
        ).fetchone()
        result.append({"label": f"{months_names[m - 1][:3]}/{y}", "points": row["total"]})
    conn.close()
    return result
