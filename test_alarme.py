"""Self-check do alarme + serviço do lembrete: python test_alarme.py

O que dá pra testar sem device: o cálculo do próximo horário (errar aqui agenda
o lembrete pra ontem, e ele nunca dispara) e o fato de o serviço não depender do
Kivy — se alguém acidentalmente importar Kivy na cadeia de dependências dele, o
processo de serviço fica caro e pode nem subir no Android. Não abre janela."""
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")
APP_DIR = Path(__file__).resolve().parent


def run_proxima_ocorrencia():
    import android_alarm as al

    def quando(agora, alvo):
        ms = al._proxima_ocorrencia(alvo, agora=agora)
        return datetime.fromtimestamp(ms / 1000)

    agora = datetime(2026, 9, 8, 14, 30)

    # ainda vai acontecer hoje
    assert quando(agora, "20:00") == datetime(2026, 9, 8, 20, 0)
    # já passou -> amanhã, e NÃO hoje (agendar no passado nunca dispara)
    assert quando(agora, "09:00") == datetime(2026, 9, 9, 9, 0)
    # exatamente agora conta como passado: o alarme dispararia imediatamente e
    # o serviço marcaria o dia como feito antes da hora do dia seguinte
    assert quando(agora, "14:30") == datetime(2026, 9, 9, 14, 30)
    # um minuto à frente ainda é hoje
    assert quando(agora, "14:31") == datetime(2026, 9, 8, 14, 31)
    # vira o dia direito
    assert quando(datetime(2026, 12, 31, 23, 50), "23:55") == datetime(2026, 12, 31, 23, 55)
    assert quando(datetime(2026, 12, 31, 23, 59), "00:05") == datetime(2027, 1, 1, 0, 5)

    # milissegundos, não segundos — o AlarmManager espera ms e um valor em
    # segundos cairia em 1970 (dispararia na hora, todo boot)
    ms = al._proxima_ocorrencia("20:00", agora=agora)
    assert ms > 1_000_000_000_000, f"parece segundos, não milissegundos: {ms}"

    # fora do Android, agendar/cancelar/serviço são no-op silenciosos
    assert al.agendar("20:00") is False
    assert al.cancelar() is False
    assert al.iniciar_servico_lembrete() is False
    assert al.parar_servico_lembrete() is False

    # o serviço faz UMA passada e sai — laço infinito era o que mantinha o app
    # em segundo plano o tempo todo
    import inspect

    import service_reminder
    fonte = inspect.getsource(service_reminder.main)
    assert "while True" not in fonte, "o serviço voltou a ser laço permanente"
    # horário corrompido no banco não pode derrubar o app
    assert al.agendar("nao-e-hora") is False
    assert al.agendar("") is False

    print("OK — próximo horário do alarme (hoje/amanhã, virada de ano, ms)")


def run_claim_atomico():
    """claim_reminder_fired: dá a marca a UM só chamador. É o que impede o app
    e o serviço (processos diferentes, sem lock compartilhado) de notificarem
    o mesmo lembrete duas vezes."""
    tmp = tempfile.mkdtemp()
    import database as db
    db.DB_PATH = Path(tmp) / "c.db"
    db.init_db()
    import settings

    hoje = "2026-09-08"
    assert settings.claim_reminder_fired("daily", hoje) is True, "1ª chamada tem que ganhar"
    assert settings.claim_reminder_fired("daily", hoje) is False, "2ª no mesmo dia não ganha"
    assert settings.claim_reminder_fired("m3", hoje) is True, "outra chave é independente"
    # dia novo: pode de novo, e a marca velha é podada
    assert settings.claim_reminder_fired("daily", "2026-09-09") is True
    assert settings.get_reminders_fired() == {"daily": "2026-09-09"}, \
        "claim tem que podar as marcas de dias anteriores"

    # concorrência real: várias threads disputando a MESMA chave -> só 1 True
    import threading
    settings.set_reminder_fired("x", "1970-01-01")  # garante que "x/hoje" não existe
    ganhos = []
    lock = threading.Lock()

    def tentar():
        r = settings.claim_reminder_fired("corrida", hoje)
        with lock:
            ganhos.append(r)

    ts = [threading.Thread(target=tentar) for _ in range(12)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert ganhos.count(True) == 1, f"esperava 1 vencedor, deu {ganhos.count(True)}"

    print("OK — claim_reminder_fired é atômico (1 vencedor mesmo sob concorrência)")


def run_servico_abre_tela_do_alarme():
    """Alarme de missão com o app fechado: o serviço abre a TELA do alarme e
    não posta notificação nem toca daqui (quem toca é a tela). Só sem a
    permissão de sobreposição ele cai pra notificação + toque."""
    tmp = tempfile.mkdtemp()
    import database as db
    db.DB_PATH = Path(tmp) / "t.db"
    db.init_db()
    import missions
    import settings

    import android_alarm
    import notify
    import service_reminder

    agora = datetime.now()
    passado = f"{agora.hour:02d}:{max(0, agora.minute - 1):02d}"
    conn = db.get_connection()
    conn.execute("UPDATE app_settings SET is_premium = 1")
    conn.commit()
    conn.close()
    mission_id = missions.add_mission("Academia", "diaria", "media", reminder_time=passado)

    telas, envios, toques = [], [], []
    notify.send = lambda *a, **k: envios.append(k.get("tela_alarme")) or True
    notify.tocar_alarme = lambda *a: toques.append(True)

    android_alarm.abrir_tela_alarme = lambda nome, horario, lang, **k: telas.append((nome, horario)) or True
    assert service_reminder.checar_missoes() == 1
    assert telas == [("Academia", passado)], telas
    assert not envios and not toques, "com a tela aberta não pode ter notificação nem toque no serviço"

    # sem permissão de sobreposição: plano B, notificação que abre a tela + toque
    settings.set_reminder_fired(f"m{mission_id}", "1970-01-01")
    android_alarm.abrir_tela_alarme = lambda *a, **k: False
    assert service_reminder.checar_missoes() == 1
    assert envios and envios[0][:2] == ("Academia", passado), \
        f"a notificação do plano B tem que abrir a tela do alarme dessa missão: {envios}"
    assert not toques, ("no plano B quem toca é a notificação insistente; tocar também "
                        "no serviço dava som dobrado quando a tela do alarme abria")

    # fora do Android a tela nativa não existe: nunca finge que abriu
    import importlib
    importlib.reload(android_alarm)
    assert android_alarm.abrir_tela_alarme("x", "08:00", "pt", em_primeiro_plano=True) is False

    print("OK — serviço abre a tela do alarme (sem notificação); plano B só sem sobreposição")


def run_servico_reagenda_no_start():
    """O serviço reafirma os alarmes ao subir — rede de segurança pro reboot,
    que apaga os alarmes do sistema."""
    tmp = tempfile.mkdtemp()
    import database as db
    db.DB_PATH = Path(tmp) / "r.db"
    db.init_db()
    import missions
    import settings

    import android_alarm
    import service_reminder

    chamadas = {"diario": [], "missoes": []}
    android_alarm.agendar = lambda hm: chamadas["diario"].append(hm) or True
    android_alarm.sincronizar_missoes = lambda pares: chamadas["missoes"].append(list(pares)) or len(pares)

    settings.set_reminder(True, "07:30")
    missions.add_mission("Academia", "diaria", "media", reminder_time="18:30")
    service_reminder.reagendar_alarmes()

    assert chamadas["diario"] == ["07:30"], chamadas
    assert chamadas["missoes"] and chamadas["missoes"][0], "não reagendou os alarmes de missão"
    print("OK — serviço reafirma alarmes no start (mitiga o reboot)")


def run_servico_sem_kivy():
    """O serviço roda num processo sem interface. Se a cadeia
    service_reminder -> settings/missions/notify/database puxar Kivy, ele fica
    caro e pode falhar no Android. Roda num subprocesso pra medir de verdade."""
    codigo = (
        "import sys; sys.modules['kivy'] = None\n"  # qualquer import de kivy explode
        "import database, settings, missions, notify, i18n, android_alarm\n"
        "print('IMPORTOU SEM KIVY')\n"
    )
    out = subprocess.run([sys.executable, "-c", codigo], cwd=APP_DIR,
                         capture_output=True, text=True, timeout=120)
    assert "IMPORTOU SEM KIVY" in out.stdout, (
        "a cadeia de dependências do serviço importa Kivy:\n" + out.stderr[-1500:])

    print("OK — serviço não depende do Kivy")


def run_servico_decide_certo():
    """O serviço só notifica quando é pra notificar, e nunca duas vezes."""
    tmp = tempfile.mkdtemp()
    import database as db
    db.DB_PATH = Path(tmp) / "s.db"
    db.init_db()
    import missions
    import settings

    import service_reminder

    enviados = []
    import notify
    # devolve True: notify.send avisa se a notificação NÃO saiu, e o serviço
    # usa isso pra devolver a marca de "já avisei" e tentar de novo
    def _send(t, m, notification_id=1, alarme=False):
        enviados.append(m)
        return True

    notify.send = _send
    import android_alarm
    android_alarm.agendar = lambda _hm: True  # sem device não há o que agendar

    agora = datetime.now()
    passado = f"{agora.hour:02d}:{max(0, agora.minute - 1):02d}"

    # lembrete desligado: não notifica
    settings.set_reminder(False, passado)
    missions.add_mission("Ler", "diaria", "media")
    service_reminder.uma_volta()
    assert not enviados, "notificou com o lembrete desligado"

    # ligado, horário passado, missão pendente: notifica uma vez
    settings.set_reminder(True, passado)
    service_reminder.uma_volta()
    assert len(enviados) == 1, f"esperava 1 notificação, veio {len(enviados)}"

    # de novo no mesmo dia: NÃO repete (mesma marca que o app usa)
    service_reminder.uma_volta()
    assert len(enviados) == 1, "o serviço notificou duas vezes no mesmo dia"

    # horário ainda não chegou: não notifica (o alarme exato pode acordar o
    # serviço no minuto anterior). "23:59" é sempre >= agora, exceto no último
    # minuto do dia — aí o sub-teste é pulado (raro no CI e sem valor)
    if agora.strftime("%H:%M") < "23:59":
        settings.set_reminder_fired("daily", "1970-01-01")  # limpa a marca de hoje
        settings.set_reminder(True, "23:59")
        antes = len(enviados)
        service_reminder.uma_volta()
        assert len(enviados) == antes, "notificou antes da hora marcada"

    # notificação que FALHA não pode consumir o dia: o claim já tinha tomado a
    # marca, e sem devolvê-la o lembrete sumia calado (foi o que aconteceu no
    # APK com AudioAttributes.Builder — ver test_notify.run_classes_aninhadas)
    settings.set_reminder_fired("daily", "1970-01-01")
    settings.set_reminder(True, passado)
    notify.send = lambda t, m, notification_id=1, alarme=False: False
    service_reminder.uma_volta()
    assert settings.get_reminders_fired().get("daily") != datetime.now().date().isoformat(), \
        "notificação falhou mas o dia foi marcado como avisado"
    notify.send = _send
    service_reminder.uma_volta()
    assert enviados and enviados[-1], "depois da falha, a próxima volta tem que notificar"

    print("OK — serviço notifica só quando deve, uma vez por dia, e repete se a notificação falhar")


def run_manifesto():
    """O <service> tem que sair do build com foregroundServiceType.

    Sem isso o Android 14 lança MissingForegroundServiceTypeException no
    startForeground() e o lembrete com app fechado morre em silêncio. O p4a não
    gera esse atributo e não há chave no buildozer.spec pra ele, então quem
    injeta é o p4a_hooks — que só roda durante o build, no runner. Aqui o
    teste exercita a função diretamente, com os formatos que o p4a pode emitir."""
    import configparser

    import p4a_hooks

    formatos = [
        '<service android:name="com.zazzysaint.dailyquest.ServiceReminder" '
        'android:process=":service_reminder" />',
        '<service android:name="com.zazzysaint.dailyquest.ServiceReminder" '
        'android:process=":service_reminder"></service>',
        '    <service\n        android:name="com.zazzysaint.dailyquest.ServiceReminder"\n'
        '        android:process=":service_reminder" />',
    ]
    import xml.etree.ElementTree as ET
    for bruto in formatos:
        saida = p4a_hooks._tipar_servico(bruto)
        assert 'android:foregroundServiceType="shortService"' in saida, bruto
        # shortService NÃO leva <property>: aquilo era exigência do specialUse,
        # usado enquanto o serviço era permanente
        assert "PROPERTY_SPECIAL_USE_FGS_SUBTYPE" not in saida, bruto
        # e o resultado tem que ser XML válido — o manifest merger do Gradle é
        # rigoroso, e a tag auto-fechada do p4a vira um par abre/fecha aqui
        ET.fromstring(saida.replace("android:", "a_"))
        assert saida.count("<service") == 1

    # rodar duas vezes não duplica nada (o hook pode reexecutar)
    uma = p4a_hooks._tipar_servico(formatos[0])
    assert p4a_hooks._tipar_servico(uma) == uma, "a injeção não é idempotente"

    # se o <service> sumir do manifesto, tem que FALHAR o build, não passar batido
    try:
        p4a_hooks._tipar_servico('<service android:name="outra.Coisa" />')
        raise AssertionError("devia ter levantado quando o service não existe")
    except RuntimeError:
        pass

    # e o .spec tem que pedir foreground + as permissões, senão o tipo não adianta
    cp = configparser.ConfigParser()
    cp.read(APP_DIR / "buildozer.spec", encoding="utf-8")
    servicos = cp.get("app", "services")
    assert ":foreground" in servicos, (
        f"o serviço precisa rodar em foreground, senão o Android 8+ recusa "
        f"iniciá-lo com o app morto: {servicos!r}")
    assert ":sticky" not in servicos, (
        "o serviço NÃO pode ser sticky: ele acorda pelo alarme, faz uma passada "
        f"e sai — sticky era o que deixava o app em segundo plano sempre: {servicos!r}")
    perms = cp.get("app", "android.permissions")
    for p in ("FOREGROUND_SERVICE", "FOREGROUND_SERVICE_SHORT_SERVICE"):
        assert p in perms, f"falta a permissão {p} em android.permissions"

    print("OK — <service> shortService, spec com foreground sem sticky e permissões")


if __name__ == "__main__":
    run_proxima_ocorrencia()
    run_claim_atomico()
    run_servico_sem_kivy()
    run_servico_decide_certo()
    run_servico_reagenda_no_start()
    run_servico_abre_tela_do_alarme()
    run_manifesto()
