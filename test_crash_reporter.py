"""Self-check do relato remoto de crash (crash_reporter.py). Não abre janela.
Troca supabase_client.report_crash por um capturador — nada vai pra rede."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")


def _boom():
    """Levanta uma exceção de verdade, pra ter type/value/traceback reais."""
    try:
        raise ValueError("explodiu de propósito")
    except ValueError:
        return sys.exc_info()


def run():
    with tempfile.TemporaryDirectory() as tmp:
        import database as db
        db.DB_PATH = Path(tmp) / "t.db"
        db.init_db()

        import settings
        import supabase_client as sb
        import crash_reporter as cr

        enviados = []
        sb.report_crash = lambda payload: enviados.append(payload)
        cr._app_version = "9.9.9"

        et, ev, tb = _boom()

        # --- payload: formato certo, dado anônimo, sem PII ---
        cr._send(et, ev, tb)
        assert len(enviados) == 1, "deveria ter mandado 1 relatório"
        p = enviados[0]
        assert set(p) == {"install_id", "app_version", "platform", "os_version",
                          "error_type", "traceback"}, p.keys()
        assert p["app_version"] == "9.9.9"
        assert p["error_type"] == "ValueError"
        assert "explodiu de propósito" in p["traceback"]
        assert "Traceback" in p["traceback"]
        assert p["install_id"] and len(p["install_id"]) >= 16, "install_id aleatório"
        # nada de e-mail/nome no payload
        blob = repr(p).lower()
        assert "@" not in p["install_id"] and "email" not in blob and "senha" not in blob

        # install_id persiste (mesmo valor no 2º boot)
        iid = p["install_id"]
        assert settings.get_settings()["install_id"] == iid
        assert cr._install_id() == iid, "não regenera a cada chamada"

        # --- dedup por sessão: o MESMO traceback não vai 2x ---
        cr._send(et, ev, tb)
        assert len(enviados) == 1, "traceback repetido não deveria reenviar"
        # um traceback diferente passa
        et2, ev2, tb2 = _boom_other()
        cr._send(et2, ev2, tb2)
        assert len(enviados) == 2

        # --- fail-silent: se report_crash quebra, _send não propaga ---
        def _raise(_p):
            raise RuntimeError("rede caiu no meio do crash")
        sb.report_crash = _raise
        et3, ev3, tb3 = _boom_third()
        cr._send(et3, ev3, tb3)  # não deve levantar nada

        # --- install(): idempotente, e registra os 2 hooks ---
        hook_antes = sys.excepthook
        cr.install("9.9.9")
        assert sys.excepthook is not hook_antes, "excepthook deveria ter sido embrulhado"
        hook_depois = sys.excepthook
        cr.install("9.9.9")
        assert sys.excepthook is hook_depois, "install() 2x não deveria re-embrulhar"

        # o handler do Kivy: registra o envio E devolve RAISE (não mascara o bug)
        from kivy.base import ExceptionManager
        handlers = [h for h in ExceptionManager.handlers
                    if type(h).__name__ == "_KivyCrashHandler"]
        assert len(handlers) == 1, "um handler de crash do Kivy registrado"
        sb.report_crash = lambda payload: enviados.append(payload)
        et4, ev4, tb4 = _boom_fourth()
        ev4.__traceback__ = tb4
        ret = handlers[0].handle_exception(ev4)
        assert ret == ExceptionManager.RAISE, "tem que devolver RAISE (deixa o app cair)"
        assert len(enviados) == 3, "o handler do Kivy também dispara o envio"

    print("OK — relato de crash: payload anônimo, dedup, fail-silent, install idempotente")


def _boom_other():
    try:
        raise KeyError("outra falha")
    except KeyError:
        return sys.exc_info()


def _boom_third():
    try:
        raise IndexError("terceira")
    except IndexError:
        return sys.exc_info()


def _boom_fourth():
    try:
        raise TypeError("quarta, via handler do Kivy")
    except TypeError:
        return sys.exc_info()


if __name__ == "__main__":
    run()
