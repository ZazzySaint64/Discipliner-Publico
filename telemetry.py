"""Telemetria mínima de retenção — ANÔNIMA e só no Android.

No máximo 2 linhas por aparelho por dia na tabela app_activity do Supabase:
"open" (abriu o app hoje) e "complete" (concluiu alguma missão hoje). Cada
linha leva só o install_id aleatório do crash_reporter (não é user_id, não liga
a conta nenhuma), a data e a versão do app. Nunca quais missões, quantas, nem
nada da conta. Dá pra tirar D1/D7 e "concluiu missão no dia" (ver README >
Telemetria de retenção).

Fora do Android não manda nada: desktop é ambiente de desenvolvimento e os
testes não podem sujar os números. Fail-silent: sem internet, tenta de novo
na próxima abertura/volta ao app do mesmo dia.
"""
import threading
from datetime import date

from kivy.utils import platform

_enviados = set()  # (kind, dia) já mandados neste processo — o banco ignora duplicado de qualquer jeito


def ping(kind, app_version=""):
    if platform != "android":
        return
    dia = date.today().isoformat()
    if (kind, dia) in _enviados:
        return
    _enviados.add((kind, dia))
    threading.Thread(target=_send, args=(kind, dia, app_version), daemon=True).start()


def _send(kind, dia, app_version):
    try:
        import crash_reporter
        import supabase_client as sb
        sb.report_activity({"install_id": crash_reporter._install_id(), "day": dia,
                            "kind": kind, "app_version": app_version})
    except Exception:
        _enviados.discard((kind, dia))  # falhou (rede): a próxima chamada do dia tenta de novo
