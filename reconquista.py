"""Reconquista: avisa quem parou de concluir missões — sem Kivy (roda no serviço).

Conta os dias desde a última conclusão (tabela completions) e manda no máximo
3 avisos por ausência, com 2, 5 e 14 dias. Depois disso para: insistir sem fim
é o que faz a pessoa desligar as notificações ou desinstalar. Concluir uma
missão zera a contagem (a "ausência" é identificada pela data da última
conclusão, então uma conclusão nova começa outra).

Quem entrega é o serviço (service_reminder), acordado por um alarme próprio
(android_alarm.agendar_reconquista) no dia do próximo aviso, no horário do
lembrete diário (ou HORA_PADRAO se ele estiver desligado). Usa o MESMO id de
notificação do lembrete diário: no dia em que os dois caem juntos, a
reconquista substitui o "falta terminar as missões de hoje" em vez de empilhar
duas notificações.

Quem nunca concluiu nada não recebe aviso — não há de onde "voltar".
"""
import json
from datetime import date, datetime, time, timedelta

DIAS = (2, 5, 14)
HORA_PADRAO = "19:00"
NOTIF_ID = 2  # = service_reminder.NOTIF_DIARIO, de propósito (ver docstring)


def _ultima_conclusao():
    import database as db

    conn = db.get_connection()
    row = conn.execute("SELECT MAX(date) AS d FROM completions").fetchone()
    conn.close()
    try:
        return date.fromisoformat(row["d"][:10]) if row and row["d"] else None
    except ValueError:
        return None


def _enviados(ultima):
    """Quantos avisos já saíram NESTA ausência (a da `ultima` conclusão)."""
    import settings

    try:
        estado = json.loads(settings.get_settings()["winback_state"] or "{}")
    except ValueError:
        return 0
    if not isinstance(estado, dict) or estado.get("ultima") != ultima.isoformat():
        return 0  # conclusão nova depois do último aviso: ausência nova
    n = estado.get("enviados")
    return n if isinstance(n, int) and n >= 0 else 0


def _hora(prefs):
    return prefs["reminder_time"] if prefs["reminder_enabled"] else HORA_PADRAO


def aviso_devido(hoje=None):
    """(dias_ausente, etapa) se tem aviso pra mandar, senão None."""
    hoje = hoje or date.today()
    ultima = _ultima_conclusao()
    if ultima is None:
        return None
    enviados = _enviados(ultima)
    dias = (hoje - ultima).days
    if enviados >= len(DIAS) or dias < DIAS[enviados]:
        return None
    return dias, enviados


def marcar_enviado(dias):
    import settings

    # conta todas as etapas já vencidas: quem some 20 dias com o celular
    # desligado recebe UM aviso, não três seguidos nos próximos dias
    enviados = sum(1 for d in DIAS if d <= dias)
    settings.set_winback_state(json.dumps({"ultima": _ultima_conclusao().isoformat(),
                                           "enviados": enviados}))


def texto(dias, etapa, lang):
    import i18n

    return (i18n.t("reminder_notification_title", lang),
            i18n.t(f"winback_body_{etapa}", lang).format(dias=dias))


def checar(agora=None):
    """Chamado a cada vez que o serviço acorda. True se notificou."""
    import notify
    import settings

    agora = agora or datetime.now()
    prefs = settings.get_settings()
    if agora.strftime("%H:%M") < _hora(prefs):
        return False  # outro alarme (missão das 7h) acordou o serviço cedo demais
    devido = aviso_devido(agora.date())
    if devido is None:
        return False
    dias, etapa = devido
    titulo, corpo = texto(dias, etapa, prefs["language"])
    if not notify.send(titulo, corpo, notification_id=NOTIF_ID):
        return False  # não marca: o próximo acordar tenta de novo
    marcar_enviado(dias)
    print(f"[reconquista] aviso {etapa + 1}/{len(DIAS)} enviado ({dias} dias sem missão)")
    return True


def proximo_aviso(hoje=None):
    """datetime do próximo aviso, ou None se não há (nunca concluiu / já mandou os 3)."""
    import settings

    hoje = hoje or date.today()
    ultima = _ultima_conclusao()
    if ultima is None:
        return None
    enviados = _enviados(ultima)
    if enviados >= len(DIAS):
        return None
    dia = max(ultima + timedelta(days=DIAS[enviados]), hoje)
    h, m = (int(p) for p in _hora(settings.get_settings()).split(":"))
    return datetime.combine(dia, time(h, m))


def reagendar():
    """Põe o alarme da reconquista de acordo com o estado atual. Chamado no
    boot do app, ao concluir missão e toda vez que o serviço acorda."""
    import android_alarm

    quando = proximo_aviso()
    if quando is None:
        android_alarm.cancelar_reconquista()
    else:
        android_alarm.agendar_reconquista(int(quando.timestamp() * 1000))
    return quando
