"""Relato remoto de crash — ANÔNIMO, só dado técnico: o traceback, a versão do
app e do sistema, e um install_id aleatório gerado no 1º boot (NÃO é user_id,
não liga a nenhuma conta — só serve pra contar aparelhos distintos). Sem
e-mail, nome ou conteúdo de missão.

Manda pra tabela crash_reports do Supabase (ver supabase_schema.sql), que só
aceita INSERT e não deixa ninguém ler pela anon key.

Fail-silent em tudo: um reporter que quebra durante um crash é pior do que não
ter reporter nenhum.
"""
import platform as _stdplatform
import sys
import threading
import traceback
import uuid

from kivy.utils import platform as _kivy_platform

_installed = False
_app_version = ""
_seen = set()  # dedup por sessão: o mesmo traceback não é enviado 2x


def _install_id():
    import settings
    iid = settings.get_settings().get("install_id") or ""
    if not iid:
        iid = uuid.uuid4().hex
        settings.set_install_id(iid)
    return iid


def _payload(exc_type, exc_value, tb):
    text = "".join(traceback.format_exception(exc_type, exc_value, tb))
    return text, {
        "install_id": _install_id(),
        "app_version": _app_version,
        "platform": str(_kivy_platform),
        "os_version": _stdplatform.platform(),
        "error_type": getattr(exc_type, "__name__", str(exc_type)),
        "traceback": text[-8000:],  # corta tracebacks gigantes (recursão etc.)
    }


def _send(exc_type, exc_value, tb):
    try:
        text, payload = _payload(exc_type, exc_value, tb)
        key = text[-500:]
        if key in _seen:
            return
        _seen.add(key)
        import supabase_client as sb
        sb.report_crash(payload)
    except Exception:
        pass  # nunca deixa o reporter piorar o crash


def _send_async(exc_type, exc_value, tb, wait=0.0):
    t = threading.Thread(target=_send, args=(exc_type, exc_value, tb), daemon=True)
    t.start()
    # crash fatal: o processo vai morrer logo — dá alguns segundos pro POST sair
    if wait:
        t.join(wait)


def install(app_version=""):
    """Chamado 1x no build(), depois de db.init_db() (precisa do banco pro
    install_id). Idempotente."""
    global _installed, _app_version
    if _installed:
        return
    _installed = True
    _app_version = app_version

    # 1) exceções FORA do loop de eventos do Kivy (import tardio, threads)
    _prev_hook = sys.excepthook

    def _hook(exc_type, exc_value, tb):
        _send_async(exc_type, exc_value, tb, wait=3.0)
        _prev_hook(exc_type, exc_value, tb)

    sys.excepthook = _hook

    # 2) exceções DENTRO do loop do Kivy — sem um handler, o Kivy já derruba o
    #    app; o nosso só registra e devolve RAISE pra NÃO mudar esse
    #    comportamento (não mascara bug nenhum).
    try:
        from kivy.base import ExceptionHandler, ExceptionManager

        class _KivyCrashHandler(ExceptionHandler):
            def handle_exception(self, exc):
                _send_async(type(exc), exc, exc.__traceback__, wait=3.0)
                return ExceptionManager.RAISE

        ExceptionManager.add_handler(_KivyCrashHandler())
    except Exception:
        pass
