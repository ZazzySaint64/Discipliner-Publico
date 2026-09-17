"""Self-check do lembrete diário: a notificação DENTRO do app (ReminderPopup)
tem que aparecer quando o horário passou e há missão pendente. A de sistema
(notify.send) é best-effort e não dá pra testar sem device — aqui só garante
que _fire_reminder não quebra se ela falhar."""
import os
import tempfile
from datetime import datetime
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")


def run_persist():
    """O lembrete do dia não pode disparar de novo quando o app é reaberto —
    era o "notificação chegando atrasada": o Android mata o processo, a marca
    de "já disparou" só existia em memória, e ao reabrir (em qualquer horário)
    o lembrete das 20:00 saía outra vez. Não abre janela."""
    import tempfile as _tf
    from datetime import date

    tmp = _tf.mkdtemp()
    import database as db
    db.DB_PATH = Path(tmp) / "p.db"
    db.init_db()

    import main
    hoje = date.today().isoformat()

    app = main.DailyQuestApp.__new__(main.DailyQuestApp)  # sem Kivy/janela: só a lógica de marcação
    app._reminder_last_fired = ""
    app._mission_reminders_fired = {}

    assert not app._fired_today("daily"), "instalação nova não pode achar que já disparou"
    app._remember_fired("daily")
    assert app._fired_today("daily"), "logo depois de disparar tem que constar disparado"

    # "reabrir o app": instância nova, memória zerada — a marca vem do banco
    app2 = main.DailyQuestApp.__new__(main.DailyQuestApp)
    app2._reminder_last_fired = ""
    app2._mission_reminders_fired = {}
    assert app2._fired_today("daily"), "app reaberto no mesmo dia NÃO pode notificar de novo"
    assert app2._reminder_last_fired == hoje, "devia ter reidratado o memo em memória do banco"

    # lembrete de missão (Premium) usa a mesma marca, por missão
    assert not app2._fired_today("m7"), "missão 7 ainda não disparou hoje"
    app2._remember_fired("m7")
    app3 = main.DailyQuestApp.__new__(main.DailyQuestApp)
    app3._reminder_last_fired = ""
    app3._mission_reminders_fired = {}
    assert app3._fired_today("m7"), "lembrete de missão também tem que sobreviver a reabrir o app"

    print("OK — lembrete não repete quando o app é morto e reaberto no mesmo dia")


def run_sem_clock():
    """O lembrete tem que disparar SEM o Clock do Kivy rodando.

    É a regressão do "notificação vindo atrasada": o Clock congela quando o app
    vai pra 2º plano, então o lembrete das 20:00 só saía quando a pessoa
    reabria o app, horas depois. Aqui não existe app.run() nenhum — se o
    lembrete sair, ele não depende mais do laço principal do Kivy."""
    import tempfile as _tf
    import time as _time
    from datetime import datetime

    tmp = _tf.mkdtemp()
    import database as db
    db.DB_PATH = Path(tmp) / "w.db"
    db.init_db()

    import main
    import missions
    import settings

    settings.set_onboarding_done()
    agora = datetime.now()
    settings.set_reminder(True, f"{agora.hour:02d}:{max(0, agora.minute - 1):02d}")
    missions.add_mission("Ler 10 páginas", "diaria", "media")

    disparos = []
    app = main.DailyQuestApp.__new__(main.DailyQuestApp)
    app._reminder_last_fired = ""
    app._mission_reminders_fired = {}
    app._reminder_lock = __import__("threading").Lock()
    app._parar_lembrete = __import__("threading").Event()
    app.reminder_enabled = True
    app.reminder_time = settings.get_settings()["reminder_time"]
    app.streak = 0
    app.is_premium = False
    app.language = "pt"
    app._fire_reminder = lambda t, b, notification_id=1: disparos.append(b)

    tick_original = main.REMINDER_TICK_SECONDS
    main.REMINDER_TICK_SECONDS = 0.2  # sem isso o teste esperaria 20s
    try:
        # o _start_reminder_watcher também agenda uma checagem no Clock, mas
        # como não existe app.run() aqui, esse agendamento nunca roda — quem
        # dispara é só a thread
        app._start_reminder_watcher()
        prazo = _time.monotonic() + 5
        while not disparos and _time.monotonic() < prazo:
            _time.sleep(0.1)
    finally:
        app._parar_lembrete.set()
        main.REMINDER_TICK_SECONDS = tick_original

    assert disparos, "o lembrete NÃO saiu sem o Clock — voltou a depender do 1º plano"
    import i18n
    pool = {i18n.t(f"reminder_msg_{i:02d}", "pt")
            for i in range(1, main.REMINDER_MESSAGE_COUNT + 1)}
    assert disparos[0] in pool, f"corpo fora do pool de mensagens: {disparos[0]!r}"
    assert len(disparos) == 1, f"disparou {len(disparos)}x no mesmo dia"
    print("OK — lembrete dispara pela thread, sem o Clock/laço do Kivy rodando")


def run_servico_ganhou():
    """Com o app aberto, o serviço (outro processo) às vezes pega a marca do
    dia primeiro: saía só a notificação de sistema e o popup do app nunca
    aparecia. Agora o app mostra o popup — uma vez, e só perto do horário."""
    import tempfile as _tf
    import threading
    from datetime import date, datetime, timedelta

    tmp = _tf.mkdtemp()
    import database as db
    db.DB_PATH = Path(tmp) / "s.db"
    db.init_db()

    import main
    import missions
    import settings

    missions.add_mission("Ler 10 páginas", "diaria", "media")
    hoje = date.today().isoformat()
    assert settings.claim_reminder_fired("daily", hoje), "o 'serviço' pega a marca primeiro"

    def novo_app(horario):
        app = main.DailyQuestApp.__new__(main.DailyQuestApp)
        app._reminder_last_fired = ""
        app._mission_reminders_fired = {}
        app._reminder_lock = threading.Lock()
        app.reminder_enabled = True
        app.reminder_time = horario
        app.streak = 0
        app.language = "pt"
        app._em_segundo_plano = False
        app.popups, app.sistema = [], []
        app._abrir_popup_lembrete = lambda t, b: app.popups.append(b)
        app._fire_reminder = lambda t, b, notification_id=2: app.sistema.append(b)
        return app

    agora = datetime.now()
    if agora.hour or agora.minute >= 1:  # horário 1 min atrás precisa ser do mesmo dia
        app = novo_app((agora - timedelta(minutes=1)).strftime("%H:%M"))
        app._check_reminder(0)
        app._check_reminder(0)
        assert len(app.popups) == 1, f"popup devia abrir 1x com o serviço tendo ganhado: {app.popups}"
        assert not app.sistema, "o serviço já mandou a notificação de sistema — não pode sair outra"

    if agora.strftime("%H:%M") >= "00:10":
        tarde = novo_app("00:00")  # reabriu o app horas depois do lembrete
        tarde._check_reminder(0)
        assert not tarde.popups and not tarde.sistema, "reabrir horas depois não pode repetir o lembrete"

    print("OK — serviço ganhou a corrida com app aberto: popup aparece 1x, sem notificação dupla")


def run():
    # sobe o App inteiro (app.run()) — instável no CI headless (SDL dummy +
    # timing de Clock). Roda só local. A parte de disparo do lembrete que dá
    # pra testar sem janela já está coberta indiretamente por test_missions.
    if os.environ.get("CI"):
        print("SKIP — CI headless (rode local: python test_reminder.py)")
        return

    tmp = tempfile.mkdtemp()
    import database as db
    db.DB_PATH = Path(tmp) / "t.db"
    db.init_db()

    import missions
    import notify
    import settings

    settings.set_onboarding_done()
    now = datetime.now()
    passado = f"{now.hour:02d}:{max(0, now.minute - 1):02d}"
    settings.set_reminder(True, passado)
    missions.add_mission("Ler 10 páginas", "diaria", "media")

    # notify.send (sistema) sempre falha -> _fire_reminder não pode propagar
    notify.send = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("sem device"))

    from kivy.clock import Clock
    from kivy.uix.popup import Popup
    from kivy.core.window import Window
    import main

    app = main.DailyQuestApp()
    result = {}

    def check(_dt):
        try:
            app._reminder_last_fired = ""
            app._check_reminder(0)
        except Exception as e:
            result["err"] = repr(e)
            app.stop()
            return
        # o popup abre via Clock (o lembrete é checado numa thread, e widget
        # do Kivy só pode ser criado na thread da UI) — espera um frame
        Clock.schedule_once(conferir, 0.3)

    def conferir(_dt):
        popups = [w for w in Window.children if isinstance(w, Popup)]
        result["popup"] = next(
            (type(p).__name__ for p in popups if type(p).__name__ == "ReminderPopup"), None
        )
        result["msg"] = next((p.message for p in popups
                              if type(p).__name__ == "ReminderPopup"), "")
        # 2ª chamada no mesmo dia não abre outro (já marcou _reminder_last_fired).
        # Contar na hora daria falso-positivo agora que o popup abre via Clock,
        # então dispara e só confere no frame seguinte.
        result["n1"] = len([w for w in Window.children if isinstance(w, Popup)])
        app._check_reminder(0)
        Clock.schedule_once(conferir_dup, 0.3)

    def conferir_dup(_dt):
        n2 = len([w for w in Window.children if isinstance(w, Popup)])
        result["dup"] = n2 == result["n1"]
        app.stop()

    Clock.schedule_once(check, 1.5)
    Clock.schedule_once(lambda _dt: app.stop(), 8)
    app.run()

    assert not result.get("err"), result["err"]
    assert result.get("popup") == "ReminderPopup", \
        "o lembrete devia abrir um ReminderPopup dentro do app mesmo com a notificação de sistema falhando"
    assert result.get("msg"), "o popup do lembrete veio sem texto"
    assert result.get("dup"), "checar de novo no mesmo dia não devia abrir um 2º popup"
    print("OK — lembrete abre popup no app (mesmo sem notificação de sistema), sem duplicar")

def run_seletor_horario():
    """TimePickerPopup: a aritmética do +/-. Errar aqui grava um horário que o
    lembrete nunca alcança (hora 24) ou grava o horário errado em silêncio."""
    import main

    pick = main.TimePickerPopup()
    escolhidos = []
    pick.abrir("07:30", "t", escolhidos.append)
    assert (pick.hora, pick.minuto) == (7, 30)

    pick.mexer("hora", -8)
    assert pick.hora == 23, f"a hora tem que dar a volta, deu {pick.hora}"
    pick.mexer("minuto", 5)
    pick.mexer("minuto", 5)
    assert pick.texto() == "23:40", pick.texto()
    pick.mexer("minuto", 25)  # 40+25 = 65 -> 05, sem virar 65
    assert pick.minuto == 5, pick.minuto

    pick.confirmar()
    assert escolhidos == ["23:05"], escolhidos
    pick.confirmar()  # dois toques rápidos no confirmar não aplicam duas vezes
    assert escolhidos == ["23:05"], escolhidos

    # horário vazio/corrompido no banco não pode derrubar o seletor
    outro = main.TimePickerPopup()
    outro.abrir("", "t", lambda _hm: None)
    assert outro.texto() == "08:00", outro.texto()
    outro.dismiss()

    print("OK — seletor de horário (volta em 24/60, passo de 5, confirma uma vez)")

def run_alarme_de_missao():
    """Duas regras do alarme de missão:

    1. Escolher um horário que JÁ PASSOU não pode apitar na hora do clique —
       alarme toca no horário marcado, não quando a pessoa o marca.
    2. Fechar o popup DESLIGA o toque. Sem isso o alarme só parava sozinho no
       teto de tempo, que é o comportamento de aviso, não de despertador.
    """
    import tempfile as _tf
    import threading
    from datetime import date, datetime

    tmp = _tf.mkdtemp()
    import database as db
    db.DB_PATH = Path(tmp) / "a.db"
    db.init_db()

    import main
    import missions
    import notify
    import settings

    agora = datetime.now()
    passado = f"{agora.hour:02d}:{max(0, agora.minute - 1):02d}"
    mission_id = missions.add_mission("Academia", "diaria", "media", reminder_time=passado)
    assert mission_id, "add_mission precisa devolver o id — é a chave do alarme"

    app = main.DailyQuestApp.__new__(main.DailyQuestApp)  # sem janela: só a lógica
    app._reminder_last_fired = ""
    app._mission_reminders_fired = {}
    app._reminder_lock = threading.Lock()
    app.is_premium = True
    app.language = "pt"
    app._em_segundo_plano = False
    disparos = []
    # o alarme abre a tela cheia via Clock (a checagem roda na thread do
    # lembrete); aqui só interessa QUAL missão ele mandou abrir
    app.abrir_alarme = lambda mid: disparos.append(mid)
    from kivy.clock import Clock

    # 1) a pessoa acabou de escolher esse horário: suprime só o dia de hoje
    app._suprimir_se_passou(f"m{mission_id}", passado)
    app._check_mission_reminders_locked()
    Clock.tick()
    assert not disparos, f"o alarme apitou na hora de marcar o horário: {disparos}"

    # ...e amanhã ele volta a tocar normalmente (marca de hoje é só de hoje)
    settings.set_reminder_fired(f"m{mission_id}", "1970-01-01")
    app._mission_reminders_fired = {}
    app._check_mission_reminders_locked()
    Clock.tick()
    assert disparos == [mission_id], f"no dia seguinte o alarme tem que abrir a tela: {disparos}"
    assert settings.get_reminders_fired().get(f"m{mission_id}") == date.today().isoformat()

    # horário FUTURO nunca é suprimido (senão o alarme do dia sumiria)
    app._mission_reminders_fired = {}
    settings.set_reminder_fired(f"m{mission_id}", "1970-01-01")
    app._suprimir_se_passou(f"m{mission_id}", "23:59")
    assert not app._fired_today(f"m{mission_id}") or agora.strftime("%H:%M") >= "23:59"

    # 2) encerrar a tela do alarme para o toque e libera um próximo alarme
    # (sem carregar o ui.kv: a regra visual usa `app.*`, que não existe sem
    # app rodando; aqui só interessa o que o Python amarra)
    parou = []
    original = notify.parar_alarme
    notify.parar_alarme = lambda: parou.append(True)
    try:
        missao = next(m for m in missions.list_missions() if m["id"] == mission_id)
        app._alarme_aberto = view = app._montar_alarme(missao)
        assert view.mission_name == "Academia" and view.horario == passado, \
            "a tela do alarme tem que mostrar a missão e o horário dela"
        view.dispatch("on_dismiss")
        assert parou, "encerrar a tela do alarme tem que parar o toque"
        assert app._alarme_aberto is None, "encerrado, um próximo alarme tem que poder abrir"
    finally:
        notify.parar_alarme = original

    print("OK — alarme de missão: não apita ao marcar, abre a tela no horário e encerrar para o toque")

def run_restaura_ao_entrar():
    """Entrar na conta tem que puxar o backup da nuvem sozinho — antes só
    acontecia se a pessoa achasse o botão em Ajustes. E o banco que estava no
    aparelho vai pra uma cópia de segurança antes, senão quem usou como
    convidado e depois entrou perderia o que fez."""
    import tempfile as _tf
    import threading
    import time as _time

    tmp = _tf.mkdtemp()
    import database as db
    db.DB_PATH = Path(tmp) / "n.db"
    db.init_db()

    import account
    import backup
    import main

    app = main.DailyQuestApp.__new__(main.DailyQuestApp)
    app.language = "pt"
    # a parte visual do restore precisa de tela; aqui só interessa a ida à nuvem
    app._fim_restore = lambda *_a: None
    chamadas = []
    sessao = {"access_token": "tok", "refresh_token": "ref", "user_id": "u1",
              "email": "e@e.com", "name": "Eric", "expires_at": 0}
    originais = (account.current_session, backup.import_from_cloud,
                 account.restore_session_row)
    account.current_session = lambda: sessao
    backup.import_from_cloud = lambda tokn, uid: chamadas.append((tokn, uid)) or True
    account.restore_session_row = lambda _s: None
    try:
        app._apos_entrar()
        prazo = _time.monotonic() + 5
        while not chamadas and _time.monotonic() < prazo:
            _time.sleep(0.05)
        assert chamadas == [("tok", "u1")], f"entrar não puxou o backup da nuvem: {chamadas}"
        copia = db.DB_PATH.with_suffix(".antes-da-nuvem.db")
        assert copia.exists(), "o banco local tem que ser copiado antes de ser substituído"

        # sem conta (convidado) não há nuvem: não pode tentar nada
        chamadas.clear()
        account.current_session = lambda: None
        app._apos_entrar()
        _time.sleep(0.3)
        assert not chamadas, "convidado não tem backup na nuvem pra restaurar"
    finally:
        account.current_session, backup.import_from_cloud, account.restore_session_row = originais

    print("OK — entrar na conta restaura o backup da nuvem (com cópia de segurança antes)")


if __name__ == "__main__":
    run_persist()  # puro (sem janela), roda no CI também
    run_sem_clock()  # idem
    run_servico_ganhou()  # idem
    run_seletor_horario()  # idem
    run_alarme_de_missao()  # idem
    run_restaura_ao_entrar()  # idem
    run()
