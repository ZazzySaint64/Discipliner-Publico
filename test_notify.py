"""Self-check do notify.py: python test_notify.py

A notificação de sistema é best-effort (pode falhar por motivo de ambiente), e
como notify.send engole exceção, uma falha some calada. O que dá pra garantir
sem device:
- send() nunca propaga exceção pro chamador (fora do Android cai no plyer/print)
- enabled() devolve True fora do Android (não assusta o usuário à toa)
- reminder_text.daily_body é a fonte ÚNICA que app e serviço usam
"""
import os
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")
APP_DIR = Path(__file__).resolve().parent


def run():
    import notify

    # send não pode explodir na cara de quem chama, aconteça o que acontecer
    try:
        notify.send("Título", "Corpo 🦸", notification_id=1)
        notify.send("", "", notification_id=99)
    except Exception as e:  # pragma: no cover
        raise AssertionError(f"notify.send propagou exceção: {e!r}")

    # fora do Android não dá pra saber o estado do sistema -> assume ligado
    assert notify.enabled() is True, "enabled() deveria ser True fora do Android"

    # a fonte única do texto do lembrete
    import reminder_text
    reminder_text.demo()

    from datetime import date
    corpo = reminder_text.daily_body(["Ler"], 2, "pt", today=date(2026, 9, 8))
    assert isinstance(corpo, str) and corpo, "daily_body veio vazio"

    # o app usa exatamente essa função (sem cópia da lógica)
    import main
    app = main.DailyQuestApp.__new__(main.DailyQuestApp)
    app.streak = 2
    app.language = "pt"
    assert app._reminder_body(["Ler"]) == reminder_text.daily_body(["Ler"], 2, "pt"), \
        "main._reminder_body divergiu de reminder_text.daily_body"

    _checar_modo_alarme()

    print("OK — notify.send não propaga, enabled() seguro, texto do lembrete tem fonte única, "
          "lembrete de missão vai como alarme")


def _checar_modo_alarme():
    """Lembrete de MISSÃO tem que sair como alarme, não como notificação comum.

    Só dá pra checar o wiring fora do Android (o resto é pyjnius puro): que o
    flag existe, que chega no _send_android, e que os DOIS caminhos que mandam
    lembrete de missão (o app e o serviço, processos diferentes) passam ele."""
    import inspect

    import notify

    assert "alarme" in inspect.signature(notify.send).parameters
    assert "alarme" in inspect.signature(notify._send_android).parameters

    # canal separado: som/vibração/importância são propriedade do canal no
    # Android 8+, então alarme e lembrete diário não podem dividir o mesmo
    assert notify.ALARM_CHANNEL_ID != notify.CHANNEL_ID

    recebidos = []
    original = notify._send_android
    notify._send_android = lambda t, m, i, a=False, _missao=None: recebidos.append(a)
    try:
        import plataforma
        era = plataforma.IS_ANDROID
        notify.IS_ANDROID = True   # finge Android só pra rota escolher _send_android
        notify.send("t", "m", notification_id=10001, alarme=True)
        notify.send("t", "m", notification_id=2)
    finally:
        notify._send_android = original
        notify.IS_ANDROID = era
    assert recebidos == [True, False], recebidos

    # e os dois emissores de lembrete de missão marcam alarme=True
    for arq in ("main.py", "service_reminder.py"):
        texto = (APP_DIR / arq).read_text(encoding="utf-8")
        i = texto.find("10000 + m")
        while i != -1:
            trecho = texto[max(0, i - 220):i + 120]
            assert "alarme=True" in trecho, f"{arq}: lembrete de missão sem alarme=True"
            i = texto.find("10000 + m", i + 1)


def run_classes_aninhadas():
    """Classe aninhada de Java (Outer.Inner) só existe no pyjnius como
    autoclass("pacote.Outer$Inner").

    `autoclass("android.media.AudioAttributes").Builder()` levanta
    AttributeError — e como todo caminho de notificação engole exceção, o
    alarme de missão simplesmente NÃO TOCAVA e nada aparecia no log do app
    (visto num APK real: "[notify] falha no Android: AttributeError(...)").
    Este teste varre o projeto atrás dessa forma errada."""
    import re

    ligacoes = re.compile(r'(\w+)\s*=\s*autoclass\("([\w.$]+)"\)')
    usos = re.compile(r'\b(\w+)\.([A-Z]\w*)\(')
    achados = []
    for arq in sorted(APP_DIR.glob("*.py")):
        if arq.name.startswith("test_"):
            continue  # os testes CITAM a forma errada de propósito (este aqui)
        texto = arq.read_text(encoding="utf-8")
        classes = dict(ligacoes.findall(texto))
        # comentário citando a forma errada (como o de notify.py) não conta
        codigo = "\n".join(l for l in texto.splitlines() if not l.lstrip().startswith("#"))
        for var, atributo in usos.findall(codigo):
            if var in classes and not classes[var].endswith(f"${atributo}"):
                achados.append(f"{arq.name}: {var}.{atributo}() — use "
                               f'autoclass("{classes[var]}${atributo}")')
    assert not achados, "classe aninhada acessada como atributo:\n" + "\n".join(achados)

    print("OK — nenhuma classe Java aninhada acessada como atributo (Outer.Inner)")


if __name__ == "__main__":
    run()
    run_classes_aninhadas()
