"""Self-check da telemetria de retenção: python test_telemetry.py

Fora do Android não manda nada (desktop/CI não pode sujar os números); no
Android manda 1x por tipo por dia, só com dado anônimo; falha de rede libera
pra tentar de novo."""
import tempfile
from pathlib import Path


def run():
    with tempfile.TemporaryDirectory() as tmp:
        import database as db
        db.DB_PATH = Path(tmp) / "t.db"
        db.init_db()
        import supabase_client as sb
        import telemetry

        enviados = []
        sb.report_activity = lambda payload: enviados.append(payload)

        class _ThreadNaHora:  # roda o alvo na hora, sem thread de verdade
            def __init__(self, target, args, daemon):
                self.target, self.args = target, args

            def start(self):
                self.target(*self.args)

        telemetry.threading.Thread = _ThreadNaHora

        telemetry.platform = "win"
        telemetry.ping("open", "2.1")
        assert not enviados, "desktop/testes não podem mandar telemetria"

        telemetry.platform = "android"
        telemetry.ping("open", "2.1")
        telemetry.ping("open", "2.1")
        telemetry.ping("complete", "2.1")
        assert [p["kind"] for p in enviados] == ["open", "complete"], enviados
        p = enviados[0]
        assert set(p) == {"install_id", "day", "kind", "app_version"}, f"campo a mais vaza dado: {set(p)}"
        assert len(p["install_id"]) == 32 and p["app_version"] == "2.1"

        # sem internet: não marca como enviado, a próxima chamada tenta de novo
        telemetry._enviados.clear()
        enviados.clear()

        def sem_rede(payload):
            raise sb.SupabaseError("network_error")

        sb.report_activity = sem_rede
        telemetry.ping("open", "2.1")  # não pode levantar
        sb.report_activity = lambda payload: enviados.append(payload)
        telemetry.ping("open", "2.1")
        assert len(enviados) == 1, "depois de falhar tinha que tentar de novo"

    print("OK — telemetria: só Android, 1x por tipo/dia, anônima, retenta após falha")


if __name__ == "__main__":
    run()
