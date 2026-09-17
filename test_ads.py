"""Self-check: python test_ads.py

Só a lógica pura de anúncios (contador de conclusões -> gatilho do
intersticial, teto diário que reseta por data, gate de plataforma/Premium).
O código jnius (banner, consentimento, show do intersticial) só roda no
Android e não é exercitado aqui."""
import tempfile
from datetime import date, timedelta
from pathlib import Path

import database as db


def run():
    with tempfile.TemporaryDirectory() as tmp:
        db.DB_PATH = Path(tmp) / "test.db"
        db.init_db()
        import ads
        import settings

        ads._session_completions = 0
        today = date(2026, 6, 1)

        # dispara na 5ª, 10ª, 15ª conclusão da sessão — não nas outras
        triggers = [ads.record_completion(today=today) for _ in range(15)]
        assert triggers == [False] * 4 + [True] + [False] * 4 + [True] + [False] * 4 + [True], triggers

        # teto de 3/dia: a 20ª conclusão seria o 4º gatilho, mas o teto já bateu
        assert ads.record_completion(today=today) is False  # 16
        for _ in range(3):
            assert ads.record_completion(today=today) is False  # 17,18,19
        assert ads.record_completion(today=today) is False, "20ª conclusão: teto diário (3) já batido"

        # o contador do dia foi gravado
        prefs = settings.get_settings()
        assert prefs["ad_interstitial_count"] == 3
        assert prefs["ad_interstitial_date"] == today.isoformat()

        # vira o dia -> teto reseta, volta a disparar
        ads._session_completions = 0
        amanha = today + timedelta(days=1)
        again = [ads.record_completion(today=amanha) for _ in range(5)]
        assert again == [False, False, False, False, True], again
        assert settings.get_settings()["ad_interstitial_count"] == 1

        # constantes coerentes
        assert ads.INTERSTITIAL_EVERY >= 1
        assert ads.INTERSTITIAL_DAILY_CAP >= 1

        # gate: fora do Android nada é "enabled" (sem app / plataforma errada)
        assert ads._enabled() is False

        # gate de Premium: com um app "premium" mockado, _enabled é False
        class FakeApp:
            is_premium = True
        ads._app = FakeApp()
        assert ads._enabled() is False
        ads._app = None

        print("OK — lógica de anúncios passou")


if __name__ == "__main__":
    run()
