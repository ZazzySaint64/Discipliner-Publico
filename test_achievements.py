"""Self-check: python test_achievements.py (não precisa do Kivy, só sqlite)."""
import tempfile
from pathlib import Path

import database as db


def run():
    with tempfile.TemporaryDirectory() as tmp:
        db.DB_PATH = Path(tmp) / "test.db"
        db.init_db()
        import achievements
        import missions
        import settings

        # do zero, tudo bloqueado
        status = achievements.status()
        assert len(status) == len(achievements.DEFINITIONS)
        assert all(not s["unlocked"] for s in status), "sem nenhuma missão/streak, nada deveria estar desbloqueado"

        # completar 1 missão desbloqueia "first_mission" e nada mais
        missions.add_mission("Ler", "diaria", "facil")
        m = missions.list_missions()[0]
        missions.complete_mission(m["id"])
        status = {s["id"]: s["unlocked"] for s in achievements.status()}
        assert status["first_mission"] is True
        assert status["missions_10"] is False
        assert status["streak_3"] is False

        # best_streak persistido em settings destrava os emblemas de sequência
        settings.set_best_streak("diaria", 7)
        status = {s["id"]: s["unlocked"] for s in achievements.status()}
        assert status["streak_3"] is True and status["streak_7"] is True
        assert status["streak_14"] is False, "7 não deveria destravar o de 14"
        assert status["streak_30"] is False, "7 não deveria destravar o de 30"

        # sequência semanal/mensal são colunas separadas — não devem se confundir
        # com a sequência diária nem entre si
        settings.set_best_streak("diaria", 100)
        settings.set_best_streak("semanal", 4)
        settings.set_best_streak("mensal", 2)
        status = {s["id"]: s["unlocked"] for s in achievements.status()}
        assert status["streak_100"] is True
        assert status["streak_semanal_4"] is True
        assert status["streak_mensal_3"] is False, "2 meses não deveria destravar o de 3"

        # "supporter": não é baseado em progresso, só na compra do Premium
        status = {s["id"]: s["unlocked"] for s in achievements.status()}
        assert status["supporter"] is False, "sem premium, não deveria estar desbloqueado"
        settings.set_premium(True)
        status = {s["id"]: s["unlocked"] for s in achievements.status()}
        assert status["supporter"] is True, "premium comprado deveria desbloquear na hora"

        print("OK — todos os checks passaram")


if __name__ == "__main__":
    run()
