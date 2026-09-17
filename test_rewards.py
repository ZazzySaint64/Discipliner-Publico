"""Self-check: python test_rewards.py (não precisa do Kivy, só sqlite)."""
import tempfile
from pathlib import Path

import database as db


def run():
    with tempfile.TemporaryDirectory() as tmp:
        db.DB_PATH = Path(tmp) / "test.db"
        db.init_db()
        import rewards

        assert rewards.available_points() == 0, "sem nenhuma missão concluída, 0 pontos disponíveis"

        rewards.add_reward("assistir um filme", 20)
        r = rewards.list_rewards()[0]
        assert r["name"] == "Assistir um filme", "add_reward também deveria capitalizar a primeira letra"
        assert r["cost"] == 20

        # sem pontos suficientes, redeem recusa
        try:
            rewards.redeem(r["id"])
            assert False, "não deveria conseguir resgatar sem pontos"
        except rewards.NotEnoughPointsError:
            pass
        assert rewards.redemption_history() == [], "resgate recusado não deveria aparecer no histórico"

        # ganha pontos (via missions, do jeito real) e resgata
        import missions
        missions.add_mission("Treino", "diaria", "dificil")  # 3 pontos
        m = missions.list_missions()[0]
        for _ in range(7):  # 7 * 3 = 21 pontos >= 20
            missions.complete_mission(m["id"])
            missions.uncomplete_mission(m["id"])
            conn = db.get_connection()
            conn.execute(
                "INSERT INTO completions (mission_id, mission_name, date, points, obs, periodicity) "
                "VALUES (?, ?, ?, ?, ?, 'diaria')",
                (m["id"], "Treino", "2020-01-01", 3, ""),
            )
            conn.commit()
            conn.close()
        assert rewards.available_points() == 21, rewards.available_points()

        rewards.redeem(r["id"])
        assert rewards.available_points() == 1, "21 - 20 (custo) = 1 ponto sobrando"
        hist = rewards.redemption_history()
        assert len(hist) == 1 and hist[0]["reward_name"] == "Assistir um filme" and hist[0]["cost"] == 20

        # editar/apagar a recompensa não afeta o histórico já gravado (snapshot)
        rewards.update_reward(r["id"], "cinema", 30)
        assert rewards.redemption_history()[0]["reward_name"] == "Assistir um filme", \
            "histórico é um retrato do momento do resgate, não deveria mudar com a edição"
        rewards.remove_reward(r["id"])
        assert len(rewards.list_rewards()) == 0
        assert len(rewards.redemption_history()) == 1, "apagar a recompensa não deveria apagar o histórico"

        print("OK — todos os checks passaram")


if __name__ == "__main__":
    run()
