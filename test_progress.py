"""Self-check: python test_progress.py (não precisa do Kivy)."""
import tempfile
from datetime import date, timedelta
from pathlib import Path

import database as db


def run():
    with tempfile.TemporaryDirectory() as tmp:
        db.DB_PATH = Path(tmp) / "test.db"
        db.init_db()
        import progress

        today = date(2026, 8, 20)  # quinta-feira — data fixa, não depende de "hoje" de verdade

        # sem nenhuma conclusão: tudo zerado, sem dividir por zero
        summary = progress.weekly_summary(today=today)
        assert summary["total_points"] == 0
        assert summary["change_pct"] == 0
        assert summary["best_day_label"] == ""

        conn = db.get_connection()
        # semana atual (últimos 7 dias, hoje incluso): 10 pontos, melhor dia = hoje
        conn.execute(
            "INSERT INTO completions (mission_id, mission_name, date, points, obs) VALUES (1, 'A', ?, ?, '')",
            (today.isoformat(), 10),
        )
        # bem antes disso (fora das duas janelas de 7 dias) — não deveria contar em nada
        conn.execute(
            "INSERT INTO completions (mission_id, mission_name, date, points, obs) VALUES (1, 'A', ?, ?, '')",
            ((today - timedelta(days=20)).isoformat(), 999),
        )
        conn.commit()
        conn.close()

        summary = progress.weekly_summary(today=today)
        assert summary["total_points"] == 10, "só deveria contar dentro da janela de 7 dias"
        assert summary["best_day_label"] == "Q", "hoje (quinta) é o melhor dia — 'Q' na tabela pt"
        assert summary["change_pct"] == 100, "sem pontos na semana anterior, ganho vira +100%"

        # --- Estatísticas avançadas (Premium — ver README > Monetização) ---
        conn = db.get_connection()
        conn.execute(
            "INSERT INTO completions (mission_id, mission_name, date, points, obs) VALUES (2, 'B', ?, ?, '')",
            (today.isoformat(), 5),
        )
        conn.commit()
        conn.close()

        perf = progress.mission_performance()
        by_name = {p["name"]: p for p in perf}
        assert by_name["A"]["completions"] == 2 and by_name["A"]["points"] == 10 + 999, by_name
        assert by_name["B"]["completions"] == 1 and by_name["B"]["points"] == 5

        best = progress.best_weekday_alltime()
        assert best is not None
        assert best["points"] >= 999, "o dia com os 999 pontos avulsos deveria dominar o total"

        months = progress.last_months_totals(n=3, today=today)
        assert len(months) == 3
        assert months[-1]["points"] == 15, "mês atual (today): 10 (A) + 5 (B) = 15"
        assert months[0]["points"] == 0, "2 meses atrás não tem nenhuma conclusão"

        print("OK — todos os checks passaram")


if __name__ == "__main__":
    run()
