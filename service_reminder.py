"""Serviço do lembrete — roda num processo SEPARADO do app, e fica de pé.

Declarado em `services = reminder:service_reminder.py:foreground:sticky` no
buildozer.spec, o que faz o python-for-android gerar a classe Java
`<pacote>.ServiceReminder`. Como ele fica vivo independente da interface, o
lembrete funciona com o app FECHADO — o caso que a thread do main.py não cobre.

Por que serviço PERMANENTE, e não um que roda e encerra:

Primeiro tentamos serviço comum, disparado sob demanda pelo AlarmManager. O
Android 8+ recusou iniciá-lo com o app morto — confirmado no emulador, o alarme
disparava na hora certa e o sistema respondia "Background start not allowed:
service ... startFg?=false". Depois tentamos serviço de foreground curto
(`shortService`). Este aqui é o passo seguinte: o serviço sobe junto com o app,
se promove a foreground e simplesmente não sai mais.

O PREÇO é uma **notificação permanente na barra de status**, que o Android
exige de todo serviço em foreground e que o usuário não pode dispensar. É o
custo consciente de ter lembrete confiável com o app fechado.

De propósito, este arquivo:

* NÃO importa Kivy. É processo sem interface; importar Kivy custaria caro e não
  serve pra nada aqui. É por isso que database.py e notify.py detectam Android
  por `plataforma.IS_ANDROID` em vez de `kivy.utils.platform`.
* Reusa a MESMA marca de "já disparou hoje" do app (settings.get_reminders_fired),
  então o app e o serviço nunca notificam em dobro.
* Trata TAMBÉM os lembretes por missão (Premium). Eles têm alarme próprio, com
  `setAlarmClock` (ver android_alarm.agendar_missao), porque horário escolhido
  pela pessoa não pode atrasar; o serviço é quem entrega a notificação quando
  esse alarme acorda o processo.
"""
import traceback
from datetime import date, datetime

# id da notificação do lembrete diário. NÃO pode ser 1: esse é o id do
# foreground service permanente (ServiceReminder.getServiceId()), e postar o
# lembrete com 1 SOBRESCREVE a notificação do serviço — ela fica presa com a
# mensagem velha e com FLAG_NO_CLEAR (não dá pra dispensar). Lembretes de missão
# usam 10000 + id da missão, também fora de rota.
NOTIF_DIARIO = 2


def _corpo(pendentes, streak, lang):
    """Mesmo texto que o app usaria — fonte única em reminder_text.py (sem
    Kivy), pra serviço e app nunca discordarem no mesmo dia."""
    import reminder_text

    return reminder_text.daily_body(pendentes, streak, lang)


def checar_diario():
    """Lembrete diário. Devolve True se notificou."""
    import android_alarm
    import i18n
    import missions
    import notify
    import settings

    prefs = settings.get_settings()
    if not prefs["reminder_enabled"]:
        return False
    if datetime.now().strftime("%H:%M") < prefs["reminder_time"]:
        return False
    hoje = date.today().isoformat()
    if settings.get_reminders_fired().get("daily") == hoje:
        return False

    pendentes = missions.pending_today()
    if not pendentes:
        return False  # tudo feito — não marca, pra ainda avisar se desmarcar algo

    if not settings.claim_reminder_fired("daily", hoje):
        return False  # o app (outro processo) ganhou a corrida e já notificou
    if not notify.send(i18n.t("reminder_notification_title", prefs["language"]),
                       _corpo(pendentes, missions.current_streak(), prefs["language"]),
                       notification_id=NOTIF_DIARIO):
        # notificação não saiu: devolve a marca, senão o lembrete de hoje some
        # sem ninguém ver nada (aqui não há tela pra mostrar o popup)
        settings.set_reminder_fired("daily", "1970-01-01")
        return False
    # reafirma o alarme do dia seguinte (defesa em profundidade: se o processo
    # cair, o alarme ainda traz ele de volta)
    android_alarm.agendar(prefs["reminder_time"])
    print(f"[servico] lembrete diário enviado ({len(pendentes)} pendente(s))")
    return True


def checar_missoes():
    """Lembretes por missão (Premium). Devolve quantos disparou."""
    import android_alarm
    import i18n
    import missions
    import notify
    import settings

    prefs = settings.get_settings()
    if not prefs["is_premium"]:
        return 0
    agora = datetime.now().strftime("%H:%M")
    hoje = date.today().isoformat()
    fired = settings.get_reminders_fired()
    enviados = 0
    for m in missions.list_missions():
        if not m["reminder_time"] or m["reminder_time"] > agora:
            continue
        if not missions.is_scheduled_today(m) or missions.is_done_this_period(m):
            continue
        chave = f"m{m['id']}"
        if fired.get(chave) == hoje:
            continue
        if not settings.claim_reminder_fired(chave, hoje):
            continue  # o app já notificou essa missão hoje
        fired = settings.get_reminders_fired()  # claim podou o resto
        # caminho normal: abre o app na tela do alarme, que mostra a missão e
        # toca. Sem notificação, e o serviço sai logo — antes dos ~10s em que o
        # Android mostraria a notificação do próprio serviço
        if android_alarm.abrir_tela_alarme(m["name"], m["reminder_time"], prefs["language"]):
            enviados += 1
            continue
        # plano B (sem permissão de sobreposição): notificação de alarme com
        # tela cheia — com o celular bloqueado/apagado o Android abre a tela do
        # alarme sozinho (USE_FULL_SCREEN_INTENT); com ele em uso vira aviso no
        # topo. O som é da própria notificação, insistente (repete até tocar
        # nela), então o serviço não toca nada e sai logo
        if not notify.send(i18n.t("reminder_notification_title", prefs["language"]),
                           m["name"], notification_id=10000 + m["id"], alarme=True,
                           tela_alarme=(m["name"], m["reminder_time"], prefs["language"])):
            # a marca já foi tomada no claim acima; sem desfazer, uma falha na
            # notificação (ver notify.send) apagaria o alarme do dia em silêncio
            settings.set_reminder_fired(chave, "1970-01-01")
            continue
        enviados += 1
    if enviados:
        print(f"[servico] {enviados} lembrete(s) de missão enviado(s)")
    return enviados


def uma_volta():
    """Uma passada de verificação. Separada do laço pra dar pra testar."""
    import reconquista

    checar_diario()
    checar_missoes()
    # depois do diário: no mesmo dia, a reconquista substitui a notificação
    # dele (mesmo id) em vez de empilhar duas
    reconquista.checar()


def reagendar_alarmes():
    """Reafirma os alarmes do sistema a partir do que está salvo. O Android
    limpa os alarmes ao reiniciar o aparelho; se o serviço subir depois do boot
    (por :sticky ou por um alarme que sobreviveu), é aqui que a rede de
    segurança é rearmada. No-op fora do Android."""
    import android_alarm
    import missions
    import reconquista
    import settings

    reconquista.reagendar()
    prefs = settings.get_settings()
    if prefs["reminder_enabled"]:
        android_alarm.agendar(prefs["reminder_time"])
    horarios = [(m["id"], m["reminder_time"] if prefs["is_premium"] else "")
                for m in missions.list_missions()]
    android_alarm.sincronizar_missoes(horarios)


def main():
    """Uma passada e SAI. Não é mais um laço.

    Antes o serviço ficava de pé pra sempre (:foreground:sticky), e o preço era
    o app aparecer em segundo plano o tempo todo, com notificação permanente na
    barra que o usuário não podia dispensar. Agora quem manda no horário é o
    AlarmManager (`setAlarmClock`, exato): ele acorda este processo na hora
    marcada, aqui a notificação sai, o próximo alarme é reagendado e o processo
    encerra."""
    import database as db

    db.init_db()  # o serviço pode subir antes de o app ter aberto alguma vez
    print("[servico] acordado pelo alarme")
    try:
        uma_volta()
    except Exception:
        print(f"[servico] falha na checagem:\n{traceback.format_exc()}")
    try:
        # reagenda ANTES de sair: sem isso o lembrete só voltaria a existir na
        # próxima vez que o app fosse aberto
        reagendar_alarmes()
    except Exception:
        print(f"[servico] falha ao reagendar:\n{traceback.format_exc()}")
    print("[servico] encerrando")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(f"[servico] falhou:\n{traceback.format_exc()}")
