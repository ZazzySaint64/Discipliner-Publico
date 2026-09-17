"""Notificação local simples.

No Android é feita direto via pyjnius (canal + PendingIntent com
FLAG_IMMUTABLE). NÃO usa plyer.notification: o plyer 2.1.0 chama
PendingIntent.getActivity(..., 0) sem FLAG_IMMUTABLE/FLAG_MUTABLE, o que
estoura IllegalArgumentException no Android 12+ (API 31) — como main.py
engole a exceção, a notificação simplesmente não aparecia.

Chamada tanto pelo app (Clock em main.py, _check_reminder/
_check_mission_reminders) quanto pelo serviço de lembrete com o app fechado
(service_reminder.checar_diario/checar_missoes). Por isso usa
`plataforma.android_context()` e não `PythonActivity.mActivity`: no processo
do serviço não há Activity. Não é alarme de sistema — é a "notificação
simples" que substituiu o AlarmManager + BroadcastReceiver em Java (frágil de
empacotar, impossível de testar fora de um device).

Fora do Android, tenta o plyer (balão do Windows) e, se falhar, só loga.
"""
import threading

from plataforma import IS_ANDROID, android_context

CHANNEL_ID = "discipliner_lembretes"
CHANNEL_NAME = "Lembretes"

# Canal SEPARADO pro lembrete de missão. Precisa ser outro canal, não um flag
# na notificação: a partir do Android 8 som, vibração e importância são
# propriedade do CANAL e ficam congelados na criação — mudar depois no builder
# é ignorado. Um canal à parte também deixa a pessoa silenciar só o alarme (ou
# só o lembrete diário) nas configs do sistema.
ALARM_CHANNEL_ID = "discipliner_alarme_missao"
ALARM_CHANNEL_NAME = "Alarme de missão"


def send(title, message, notification_id=2, alarme=False, tela_alarme=None):
    """notification_id: mesmo id substitui a notificação anterior; use um por
    "assunto" (2 = lembrete diário; 10000+mission_id = lembrete de missão).
    NUNCA 1: é o id do foreground service permanente (ServiceReminder) e
    postar com 1 sobrescreve a notificação dele, que trava com FLAG_NO_CLEAR.

    Devolve False se a notificação NÃO foi postada. Quem não tem outra forma de
    avisar (o serviço, que roda sem tela) usa isso pra desfazer a marca de "já
    avisei hoje" e tentar de novo — senão uma falha aqui engole o lembrete do
    dia inteiro, calada. Foi o que aconteceu com o alarme de missão e o
    AudioAttributes.Builder (ver tocar_alarme)."""
    if IS_ANDROID:
        return _send_android(title, message, notification_id, alarme, tela_alarme)
    return _send_desktop(title, message)


def enabled():
    """As notificações do app estão ligadas nas configs do sistema?

    Se a pessoa nega a permissão (Android 13+) ou desliga o canal, `send()`
    acima simplesmente não mostra nada — e como ele engole exceção, isso é
    invisível. O app usa esta função pra AVISAR (card em Ajustes) em vez de os
    lembretes sumirem calados.

    True fora do Android e em Android < 24 (onde não dá pra checar sem AndroidX).
    Na dúvida devolve True — não assustar sem motivo."""
    if not IS_ANDROID:
        return True
    try:
        from jnius import autoclass, cast

        Context = autoclass("android.content.Context")
        VERSION = autoclass("android.os.Build$VERSION")

        if VERSION.SDK_INT < 24:
            return True
        ctx = android_context()
        nm = cast("android.app.NotificationManager",
                  ctx.getSystemService(Context.NOTIFICATION_SERVICE))
        return bool(nm.areNotificationsEnabled())
    except Exception as e:
        print(f"[notify] não consegui checar se as notificações estão ativas: {e!r}")
        return True


def _send_android(title, message, notification_id, alarme=False, tela_alarme=None):
    try:
        from jnius import autoclass, cast

        Context = autoclass("android.content.Context")
        Builder = autoclass("android.app.Notification$Builder")
        NotificationManager = autoclass("android.app.NotificationManager")
        Intent = autoclass("android.content.Intent")
        PendingIntent = autoclass("android.app.PendingIntent")
        VERSION = autoclass("android.os.Build$VERSION")

        # Context que vale nos dois processos. Antes era PythonActivity.mActivity,
        # que é None no processo do serviço — então o lembrete com o app fechado
        # (o motivo de o serviço existir) estourava aqui e era engolido.
        ctx = android_context()
        # cast explícito: getSystemService devolve um java.lang.Object "cru", e
        # sem o cast o pyjnius não acha createNotificationChannel/notify —
        # AttributeError silencioso engolido pelo except lá embaixo (é o
        # motivo nº 1 de "a notificação não aparece e não dá erro").
        nm = cast("android.app.NotificationManager",
                  ctx.getSystemService(Context.NOTIFICATION_SERVICE))

        canal = ALARM_CHANNEL_ID if alarme else CHANNEL_ID
        if VERSION.SDK_INT >= 26:
            NotificationChannel = autoclass("android.app.NotificationChannel")
            channel = NotificationChannel(
                canal,
                ALARM_CHANNEL_NAME if alarme else CHANNEL_NAME,
                NotificationManager.IMPORTANCE_HIGH)
            if alarme:
                _configurar_canal_alarme(channel, autoclass)
            nm.createNotificationChannel(channel)
            builder = Builder(ctx, canal)
        else:
            builder = Builder(ctx)

        # toque na notificação abre o app (se getLaunchIntentForPackage vier
        # null por algum motivo, segue sem contentIntent — melhor uma
        # notificação que não abre nada do que nenhuma)
        pending = None
        launch = ctx.getPackageManager().getLaunchIntentForPackage(
            ctx.getPackageName())
        if launch is not None:
            launch.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
            if tela_alarme is not None:
                # tocar na notificação do alarme abre a TELA do alarme
                import android_alarm
                launch = android_alarm.intent_tela_alarme(ctx, *tela_alarme, notif_id=notification_id)
            flags = PendingIntent.FLAG_UPDATE_CURRENT
            if VERSION.SDK_INT >= 23:
                flags |= PendingIntent.FLAG_IMMUTABLE
            # requestCode = id da notificação: com 0 em todas, o
            # FLAG_UPDATE_CURRENT reescreveria o extra de um alarme no outro
            pending = PendingIntent.getActivity(ctx, notification_id, launch, flags)

        icon = ctx.getApplicationInfo().icon
        if not icon:  # ícone 0/ausente = Android descarta a notificação sem avisar
            icon = autoclass("android.R$drawable").ic_dialog_info

        builder.setContentTitle(title)
        builder.setContentText(message)
        builder.setSmallIcon(icon)
        builder.setAutoCancel(True)
        if pending is not None:
            builder.setContentIntent(pending)
        if alarme:
            _configurar_alarme(builder, pending, autoclass, VERSION)
        notificacao = builder.build()
        if alarme:
            # FLAG_INSISTENT: o som do canal (volume de alarme) REPETE até a
            # pessoa tocar na notificação — sem isso ele toca uma vez e cala.
            # Quem abre a tela do alarme cancela a notificação e o som para
            # (AlarmeActivity.preencher, extra "notif_id").
            notificacao.flags = notificacao.flags | autoclass("android.app.Notification").FLAG_INSISTENT
        nm.notify(notification_id, notificacao)
        return True
    except Exception as e:
        import traceback
        print(f"[notify] falha no Android: {e!r}\n{traceback.format_exc()}")
        return False


# Tetos de tempo do toque. O som do CANAL de notificação toca uma vez só e
# acaba — é isso que fazia o "alarme" soar como aviso comum; alarme de celular
# insiste até alguém DESLIGAR (parar_alarme).
#
# Dois valores porque quem toca são dois processos diferentes:
#   * serviço (app fechado): é um foreground de trabalho CURTO, o Android
#     derruba ele em poucos minutos — e ninguém pode desligar o toque de lá,
#     porque não há tela. 60s.
#   * app aberto: o popup do lembrete é o botão de desligar, então o toque
#     pode insistir de verdade. 5min é o teto de segurança, pro alarme não
#     ficar tocando pra sempre se o app for morto com o popup aberto.
ALARME_SEGUNDOS = 60
ALARME_APP_SEGUNDOS = 300

# Desligar é o que separa alarme de notificação. Event (e não flag) porque quem
# desliga é sempre outra thread: tocar_alarme BLOQUEIA enquanto o som roda.
_desligar = threading.Event()


def parar_alarme():
    """Desliga o toque que tocar_alarme() estiver tocando agora. No-op se não
    houver nenhum."""
    _desligar.set()


def tocar_alarme(segundos=ALARME_SEGUNDOS):
    """Toca o toque de ALARME do aparelho, em loop, até parar_alarme() ou até
    `segundos`.

    Bloqueia quem chamou — o serviço do lembrete é justamente um processo curto
    que existe pra isso; enquanto o toque roda ele fica vivo, e depois encerra.
    Com o app aberto, quem chama é uma thread (ver App._fire_reminder).

    No-op fora do Android e silencioso em qualquer falha — alarme que não toca
    é ruim, app que fecha porque o alarme não tocou é pior."""
    if not IS_ANDROID:
        return False
    _desligar.clear()
    try:
        import time

        from jnius import autoclass

        RingtoneManager = autoclass("android.media.RingtoneManager")
        AudioAttributes = autoclass("android.media.AudioAttributes")
        # classe ANINHADA: no pyjnius só chega por "$", nunca como atributo da
        # de fora. `AudioAttributes.Builder()` levanta AttributeError, e como
        # todo mundo aqui engole exceção, o alarme sumia calado.
        AudioAttributesBuilder = autoclass("android.media.AudioAttributes$Builder")
        VERSION = autoclass("android.os.Build$VERSION")

        ctx = android_context()
        uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
        if uri is None:
            uri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
        toque = RingtoneManager.getRingtone(ctx, uri)
        if toque is None:
            return False
        # USAGE_ALARM: sai no volume de ALARME, que continua audível com o
        # aparelho no silencioso/vibrar — é o que separa alarme de notificação
        toque.setAudioAttributes(
            AudioAttributesBuilder()
            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
            .setUsage(AudioAttributes.USAGE_ALARM)
            .build())
        if VERSION.SDK_INT >= 28:
            toque.setLooping(True)   # só existe a partir do Android 9
        toque.play()

        fim = time.monotonic() + segundos

        def tocando():
            return time.monotonic() < fim and not _desligar.is_set()

        while tocando() and toque.isPlaying():
            time.sleep(0.3)
        if VERSION.SDK_INT < 28:
            # sem setLooping: o toque acabou sozinho, repete até desligarem
            while tocando():
                toque.play()
                while toque.isPlaying() and tocando():
                    time.sleep(0.3)
        toque.stop()
        return True
    except Exception as e:
        import traceback
        print(f"[notify] toque de alarme falhou: {e!r}\n{traceback.format_exc()}")
        return False


def _configurar_canal_alarme(channel, autoclass):
    """Som de ALARME + vibração no canal do lembrete de missão.

    USAGE_ALARM importa: som com esse uso toca no volume de ALARME, que segue
    tocando com o celular no silencioso/vibrar e ignora o Não Perturbe quando
    a pessoa permite alarmes. É o que separa "alarme" de "notificação"."""
    RingtoneManager = autoclass("android.media.RingtoneManager")
    AudioAttributes = autoclass("android.media.AudioAttributes")
    AudioAttributesBuilder = autoclass("android.media.AudioAttributes$Builder")  # ver tocar_alarme

    som = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
    if som is None:  # aparelho sem toque de alarme padrão: cai pra notificação
        som = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
    atributos = (AudioAttributesBuilder()
                 .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                 .setUsage(AudioAttributes.USAGE_ALARM)
                 .build())
    channel.setSound(som, atributos)
    channel.enableVibration(True)
    channel.setVibrationPattern([0, 700, 400, 700, 400, 700])
    channel.setBypassDnd(True)   # só vale se o usuário autorizar o app no Não Perturbe


def _configurar_alarme(builder, pending, autoclass, VERSION):
    """Deixa a notificação se comportar como alarme, não como aviso passivo."""
    Notification = autoclass("android.app.Notification")

    builder.setCategory(Notification.CATEGORY_ALARM)
    builder.setPriority(Notification.PRIORITY_MAX)   # usado no Android < 26 (pré-canais)
    builder.setOngoing(True)          # não some ao deslizar: exige tocar nela
    builder.setAutoCancel(True)       # ...mas some quando a pessoa toca
    builder.setDefaults(Notification.DEFAULT_VIBRATE)
    if pending is not None and VERSION.SDK_INT >= 21:
        # heads-up em tela cheia: com a tela bloqueada, aparece por cima em vez
        # de virar uma linha na gaveta de notificações
        builder.setFullScreenIntent(pending, True)


def _send_desktop(title, message):
    try:
        from plyer import notification
        notification.notify(title=title, message=message, timeout=10)
        return True
    except Exception as e:
        print(f"[notify] {title}: {message}  ({e!r})")
        return False
