"""Serviço do lembrete + alarme do sistema — o que faz a notificação sair com o
app FECHADO.

A thread de `main._start_reminder_watcher` só cobre o app ABERTO ou minimizado.
Com o processo morto (Doze, falta de memória, o usuário deslizando o app pra
fora dos recentes), quem entrega é:

1. O **serviço** (`service_reminder.py`, classe `<pacote>.ServiceReminder`),
   um foreground service permanente (`:foreground:sticky`) que
   `iniciar_servico_lembrete()` sobe quando o app abre e que fica num laço
   conferindo o relógio a cada 60s. É o caminho normal.
2. O **AlarmManager** como rede de segurança: se um fabricante mata o serviço
   apesar do `:sticky`, o alarme dispara no horário e `getForegroundService`
   sobe o serviço de novo.

`setAlarmClock` (exato) no lembrete diário, e não `setAndAllowWhileIdle`
(inexato): o inexato (a) pode atrasar bem além de "alguns minutos" em Doze
profundo e (b) **não** dá a isenção temporária que o Android 12+ exige pra
iniciar um foreground service em segundo plano — `getForegroundService` a
partir dele estoura `ForegroundServiceStartNotAllowedException`.

`setAlarmClock` no Android 14 (API 34) exige a permissão `USE_EXACT_ALARM`
(declarada no buildozer.spec; concedida na instalação, sem prompt). Sem ela
o `setAlarmClock` joga `SecurityException` — `agendar()` então cai pro
`setAndAllowWhileIdle` (inexato) pra ainda entregar, com atraso, em vez de
falhar em silêncio. Preço do exato: o ícone de despertador na barra + o
próximo horário exposto nos relógios do sistema — o mesmo que os lembretes
por missão já mostram.

Fora do Android tudo aqui é no-op.
"""
import traceback
from datetime import datetime, timedelta

from plataforma import IS_ANDROID

_REQUEST_CODE = 0xA1A2  # identifica o alarme DIÁRIO, pra poder substituir/cancelar

# Os lembretes por missão (Premium) ganham um request code próprio, derivado do
# id da missão, pra cada um poder ser substituído/cancelado sozinho. A base é
# alta o bastante pra nunca colidir com _REQUEST_CODE.
_BASE_MISSAO = 0xB000
_MAX_MISSOES_AGENDADAS = 64  # teto de alarmes; acima disso o resto fica com a thread


def agendar(hora_minuto):
    """Agenda (ou reagenda) o lembrete diário pro próximo "HH:MM" que ainda vai
    acontecer. Chamar de novo substitui o alarme anterior (FLAG_UPDATE_CURRENT
    reusa o mesmo PendingIntent).

    Tenta `setAlarmClock` (exato, imune a Doze); se faltar a permissão
    `USE_EXACT_ALARM` (build de Play Store que a trocou), cai pro
    `setAndAllowWhileIdle` (inexato — atrasa em Doze, mas entrega). Ver o
    docstring do módulo."""
    if not IS_ANDROID:
        return False
    try:
        quando = _proxima_ocorrencia(hora_minuto)
    except (ValueError, AttributeError):
        print(f"[alarme] horário inválido, não agendei: {hora_minuto!r}")
        return False
    exato = _com_alarm_manager(lambda am, pi, cls: (
        am.setAlarmClock(cls["AlarmClockInfo"](quando, pi), pi),
        print(f"[alarme] lembrete (exato) para {hora_minuto} "
              f"({datetime.fromtimestamp(quando / 1000):%d/%m %H:%M})"),
    ))
    if exato:
        return True
    return _com_alarm_manager(lambda am, pi, cls: (
        am.setAndAllowWhileIdle(cls["AlarmManager"].RTC_WAKEUP, quando, pi),
        print(f"[alarme] lembrete (inexato, fallback) para {hora_minuto} "
              f"({datetime.fromtimestamp(quando / 1000):%d/%m %H:%M})"),
    ))


def cancelar():
    """Desliga o alarme — chamado quando a pessoa desativa o lembrete."""
    if not IS_ANDROID:
        return False
    return _com_alarm_manager(lambda am, pi, _cls: (
        am.cancel(pi),
        print("[alarme] lembrete cancelado"),
    ))


_REQUEST_RECONQUISTA = 0xA1A3  # alarme da reconquista (ver reconquista.py)


def agendar_reconquista(quando_ms):
    """Alarme do próximo aviso de reconquista (dias à frente).

    `setExactAndAllowWhileIdle`, não `setAlarmClock`: o AlarmClock põe ícone de
    despertador na barra e expõe o horário nos relógios do sistema — pra um
    aviso daqui a 5 dias isso seria ruído permanente. E exato, não inexato: só
    alarme exato dá a isenção que o Android 12+ exige pra subir o serviço em
    foreground (ver docstring do módulo). Sem a permissão de exato, cai pro
    inexato."""
    if not IS_ANDROID:
        return False
    if _com_alarm_manager(lambda am, pi, cls: am.setExactAndAllowWhileIdle(
            cls["AlarmManager"].RTC_WAKEUP, quando_ms, pi), codigo=_REQUEST_RECONQUISTA):
        print(f"[alarme] reconquista para {datetime.fromtimestamp(quando_ms / 1000):%d/%m %H:%M}")
        return True
    return _com_alarm_manager(lambda am, pi, cls: am.setAndAllowWhileIdle(
        cls["AlarmManager"].RTC_WAKEUP, quando_ms, pi), codigo=_REQUEST_RECONQUISTA)


def cancelar_reconquista():
    if not IS_ANDROID:
        return False
    return _com_alarm_manager(lambda am, pi, _cls: am.cancel(pi), codigo=_REQUEST_RECONQUISTA)


def disponivel_para_missoes():
    """Só faz sentido mexer em alarme de missão no Android — evita o caller
    montar a lista de missões à toa no desktop."""
    return IS_ANDROID


def _servico_reminder():
    """(ctx, classe Java ServiceReminder) — ou levanta se não for Android.

    `android_context()` porque isto roda tanto no app quanto no próprio
    processo do serviço (reagendar_alarmes no start), onde não há Activity."""
    from jnius import autoclass

    from plataforma import android_context

    ctx = android_context()
    return ctx, autoclass(f"{ctx.getPackageName()}.ServiceReminder")


def iniciar_servico_lembrete():
    """Sobe o ServiceReminder em foreground. É o que garante o serviço rodando
    ANTES do primeiro alarme (e de novo depois de o app ser reaberto pós-boot,
    quando o Android já limpou os alarmes). Chamado do main a cada abertura e
    sempre que passa a existir algum lembrete.

    Usa o `ServiceReminder.start()` gerado pelo p4a: ele monta o Intent COM os
    extras que o PythonService.onStartCommand exige (androidPrivate, pythonHome,
    serviceStartAsForeground...) e o serviço se promove a foreground sozinho.
    Um `startForegroundService` com Intent "pelado" crashava o serviço num
    NullPointerException em `intent.getExtras()` (testado no emulador API 34).

    Idempotente: o onStartCommand do serviço tem guarda de thread única, então
    chamar com o serviço já no ar não cria um 2º laço."""
    if not IS_ANDROID:
        return False
    try:
        ctx, servico = _servico_reminder()
        servico.start(ctx, "")
        print("[servico] ServiceReminder iniciado")
        return True
    except Exception:
        print(f"[servico] falha ao iniciar:\n{traceback.format_exc()}")
        return False


def parar_servico_lembrete():
    """Derruba o serviço — some a notificação permanente da barra. Chamado
    quando não sobra nenhum lembrete (diário desligado E nenhuma missão com
    horário): não faz sentido manter um foreground service sem nada a lembrar."""
    if not IS_ANDROID:
        return False
    try:
        ctx, servico = _servico_reminder()
        servico.stop(ctx)
        print("[servico] ServiceReminder parado")
        return True
    except Exception:
        print(f"[servico] falha ao parar:\n{traceback.format_exc()}")
        return False


def agendar_missao(mission_id, hora_minuto):
    """Alarme de um lembrete de missão (Premium), com `setAlarmClock`.

    Por que `setAlarmClock` aqui e não o `setAndAllowWhileIdle` do diário:
    lembrete de missão é marcado pra um horário específico que a pessoa
    escolheu ("academia 18:30"), então atrasar alguns minutos estraga o
    propósito. `setAlarmClock` é EXATO e imune a Doze. Precisa da permissão
    `USE_EXACT_ALARM` (buildozer.spec); sem ela o `_com_alarm_manager` engole
    a `SecurityException` e o lembrete de missão simplesmente não agenda (a
    thread do app aberto ainda cobre) — diferente do diário, aqui não há
    fallback inexato de propósito.

    O preço é visível: o Android mostra o ÍCONE DE DESPERTADOR na barra de
    status e expõe o próximo horário nos relógios do sistema, porque essa API
    existe pra alarmes que o usuário reconhece como tal. É um efeito colateral
    aceito de propósito, não um descuido."""
    if not IS_ANDROID:
        return False
    try:
        quando = _proxima_ocorrencia(hora_minuto)
    except (ValueError, AttributeError):
        print(f"[alarme] horário inválido na missão {mission_id}: {hora_minuto!r}")
        return False

    def acao(am, pi, cls):
        # o 2º PendingIntent é o que o relógio do sistema abre se o usuário
        # tocar no alarme; mandar o próprio serviço é o comportamento esperado
        am.setAlarmClock(cls["AlarmClockInfo"](quando, pi), pi)
        print(f"[alarme] missão {mission_id} agendada para {hora_minuto}")

    return _com_alarm_manager(acao, codigo=_codigo_missao(mission_id),
                              extra_missao=mission_id)


def cancelar_missao(mission_id):
    if not IS_ANDROID:
        return False
    return _com_alarm_manager(
        lambda am, pi, _cls: (am.cancel(pi),
                              print(f"[alarme] missão {mission_id} cancelada")),
        codigo=_codigo_missao(mission_id), extra_missao=mission_id)


def sincronizar_missoes(missoes_com_horario):
    """Reagenda os alarmes das missões a partir da lista atual.

    `missoes_com_horario` é uma lista de (mission_id, "HH:MM"). Quem tem
    horário ganha alarme; o resto é cancelado. Chamada quando as missões mudam
    e a cada boot, porque o Android descarta alarmes ao reiniciar o aparelho."""
    if not IS_ANDROID:
        return 0
    agendadas = 0
    for mission_id, hora in missoes_com_horario[:_MAX_MISSOES_AGENDADAS]:
        if hora and agendar_missao(mission_id, hora):
            agendadas += 1
        elif not hora:
            cancelar_missao(mission_id)
    return agendadas


# --- tela do alarme de missão ---
#
# A tela é NATIVA (android_java/AlarmeActivity.java), não Kivy: precisa acender
# a tela e passar por cima do bloqueio na hora, e uma tela Kivy depende de o
# Python subir — com o aparelho dormindo ela nem chegava a rodar (testado).
# Sem notificação: é a tela, o toque e a vibração.
#
# O Android 10+ BLOQUEIA abrir Activity a partir de segundo plano — e o
# bloqueio é silencioso (só um "Background activity launch blocked" no
# logcat, nenhuma exceção). A isenção que um app comum consegue é a permissão
# "sobrepor a outros apps" (SYSTEM_ALERT_WINDOW), que a pessoa concede nas
# configurações. Por isso abrir_tela_alarme confere canDrawOverlays ANTES e
# devolve False sem ela: o serviço então cai pra notificação + toque.


def pode_abrir_tela_alarme():
    """True se o app pode abrir a tela do alarme sozinho, com o app fechado."""
    if not IS_ANDROID:
        return False
    try:
        from jnius import autoclass

        from plataforma import android_context

        if autoclass("android.os.Build$VERSION").SDK_INT < 23:
            return True  # antes do Android 6 a permissão vinha na instalação
        return bool(autoclass("android.provider.Settings").canDrawOverlays(android_context()))
    except Exception:
        print(f"[alarme] não consegui checar a sobreposição:\n{traceback.format_exc()}")
        return False


def intent_tela_alarme(ctx, nome, horario, lang, notif_id=None):
    """Intent da AlarmeActivity com os textos já traduzidos nos extras (a tela
    é Java e não enxerga o i18n.py). Serve pro startActivity e pra notificação
    do plano B."""
    from jnius import autoclass

    import i18n

    Intent = autoclass("android.content.Intent")
    intent = Intent()
    # setClassName e não Intent(ctx, Classe): o proxy do pyjnius não é um
    # java.lang.Class, e o construtor não o aceita
    intent.setClassName(ctx.getPackageName(), f"{ctx.getPackageName()}.AlarmeActivity")
    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    # Bundle.putString, NÃO intent.putExtra: putExtra tem dezenas de overloads
    # e o pyjnius escolheu putExtra(String, char[]) pra str do Python — no
    # device o getStringExtra da tela voltava null ("Key titulo expected String
    # but value was a [C") e ela abria sem horário, sem missão e com botão "OK".
    # putString só tem uma assinatura, então não há o que adivinhar.
    extras = autoclass("android.os.Bundle")()
    extras.putString("nome", str(nome))
    extras.putString("horario", str(horario))
    extras.putString("titulo", i18n.t("alarm_title", lang))
    extras.putString("botao", i18n.t("btn_stop_alarm", lang))
    if notif_id is not None:
        # a tela cancela a notificação insistente que a abriu (e o som dela)
        extras.putInt("notif_id", int(notif_id))
    intent.putExtras(extras)
    return intent


def abrir_tela_alarme(nome, horario, lang, em_primeiro_plano=False):
    """Abre a tela do alarme. False se não deu — quem chama faz o plano B.

    `em_primeiro_plano`: o app aberto pode abrir Activity à vontade; só o
    serviço (app fechado) precisa da permissão de sobreposição."""
    if not IS_ANDROID or (not em_primeiro_plano and not pode_abrir_tela_alarme()):
        return False
    try:
        from plataforma import android_context

        ctx = android_context()
        ctx.startActivity(intent_tela_alarme(ctx, nome, horario, lang))
        print(f"[alarme] tela do alarme aberta ({nome} {horario})")
        return True
    except Exception:
        print(f"[alarme] não consegui abrir a tela do alarme:\n{traceback.format_exc()}")
        return False


def abrir_config_sobreposicao():
    """Abre, nas configurações do Android, a chave "sobrepor a outros apps"
    DESTE app."""
    if not IS_ANDROID:
        return False
    try:
        from jnius import autoclass

        from plataforma import android_context

        Intent = autoclass("android.content.Intent")
        Settings = autoclass("android.provider.Settings")
        Uri = autoclass("android.net.Uri")
        ctx = android_context()
        intent = Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                        Uri.parse("package:" + ctx.getPackageName()))
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        ctx.startActivity(intent)
        return True
    except Exception:
        print(f"[alarme] não consegui abrir a config de sobreposição:\n{traceback.format_exc()}")
        return False


def _codigo_missao(mission_id):
    # id da missão cabe no espaço reservado; o módulo evita estourar pra cima
    # do request code do lembrete diário se algum id crescer demais
    return _BASE_MISSAO + (int(mission_id) % _MAX_MISSOES_AGENDADAS)



def _proxima_ocorrencia(hora_minuto, agora=None):
    """Timestamp em MILISSEGUNDOS do próximo HH:MM (hoje se ainda não passou,
    senão amanhã). Milissegundos porque é o que o AlarmManager espera."""
    agora = agora or datetime.now()
    hora, minuto = (int(p) for p in hora_minuto.split(":"))
    alvo = agora.replace(hour=hora, minute=minuto, second=0, microsecond=0)
    if alvo <= agora:
        alvo += timedelta(days=1)
    return int(alvo.timestamp() * 1000)


def _com_alarm_manager(acao, codigo=None, extra_missao=None):
    """Resolve AlarmManager + PendingIntent e entrega pra `acao(am, pi, cls)`.

    `codigo` separa os alarmes entre si (o diário e um por missão); sem isso um
    sobrescreveria o outro, porque o PendingIntent é identificado por
    (contexto, requestCode, intent). `extra_missao` viaja no Intent pro serviço
    saber QUAL missão lembrar quando acordar."""
    try:
        from jnius import autoclass, cast

        from plataforma import android_context

        PendingIntent = autoclass("android.app.PendingIntent")
        AlarmManager = autoclass("android.app.AlarmManager")
        Context = autoclass("android.content.Context")
        VERSION = autoclass("android.os.Build$VERSION")

        # android_context(), NÃO PythonActivity.mActivity: reagendar_alarmes()
        # roda no processo do serviço (sem Activity) e a chamada dava
        # AttributeError: 'NoneType' object has no attribute 'getPackageName'.
        contexto = android_context()
        servico = autoclass(f"{contexto.getPackageName()}.ServiceReminder")

        # getDefaultIntent (gerado pelo p4a) já traz os extras que o
        # PythonService.onStartCommand exige (androidPrivate, pythonHome,
        # serviceStartAsForeground...). Um Intent(contexto, servico) "pelado"
        # faz o serviço crashar com NullPointerException em getExtras() quando
        # o alarme o inicia — mesmo bug do iniciar_servico_lembrete.
        intent = servico.getDefaultIntent(contexto, "", "Discipliner", "Reminder", "")
        if extra_missao is not None:
            intent.putExtra("mission_id", int(extra_missao))
        flags = PendingIntent.FLAG_UPDATE_CURRENT
        if VERSION.SDK_INT >= 23:
            # obrigatório a partir do Android 12 (API 31) e inofensivo antes —
            # sem um dos dois flags o PendingIntent estoura IllegalArgumentException
            flags |= PendingIntent.FLAG_IMMUTABLE

        # getForegroundService, NÃO getService: com o app morto, o Android 8+
        # recusa iniciar serviço comum a partir do alarme. Testado no emulador
        # com getService — o alarme disparava e o sistema respondia
        # "Background start not allowed: service ... startFg?=false".
        alvo = codigo if codigo is not None else _REQUEST_CODE
        if VERSION.SDK_INT >= 26:
            pi = PendingIntent.getForegroundService(contexto, alvo, intent, flags)
        else:
            pi = PendingIntent.getService(contexto, alvo, intent, flags)

        # cast explícito: getSystemService devolve java.lang.Object "cru" e sem
        # isso o pyjnius não acha os métodos (mesma armadilha do notify.py)
        am = cast("android.app.AlarmManager",
                  contexto.getSystemService(Context.ALARM_SERVICE))
        acao(am, pi, {"AlarmManager": AlarmManager,
                      "AlarmClockInfo": autoclass("android.app.AlarmManager$AlarmClockInfo")})
        return True
    except Exception:
        # sem alarme o app continua funcionando (a thread cobre o app aberto),
        # então isso nunca pode derrubar nada
        print(f"[alarme] falhou:\n{traceback.format_exc()}")
        return False
