"""Self-check: apagar missão pede confirmação antes (python test_confirm_delete.py).

O "×" da linha da missão fica coladinho no "Editar" — antes ele apagava na
hora, sem desfazer. Agora abre um ConfirmPopup e só apaga no botão vermelho.
Sobe o App inteiro porque a regra <ConfirmPopup> mora no ui.kv, que só é
carregado no build()."""
import os
import tempfile
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")


def run_pool():
    """As 15 mensagens do lembrete: existem, são distintas, e a do dia troca
    sozinha sem depender de sorteio (app morto e reaberto = mesma mensagem)."""
    from datetime import date, timedelta

    import i18n
    import main

    for lang, tabela in i18n.TRANSLATIONS.items():
        textos = []
        for i in range(1, main.REMINDER_MESSAGE_COUNT + 1):
            chave = f"reminder_msg_{i:02d}"
            assert chave in tabela, f"{lang}: falta {chave}"
            textos.append(tabela[chave])
        assert len(set(textos)) == main.REMINDER_MESSAGE_COUNT, \
            f"{lang}: tem mensagem repetida no pool"

    # a escolha é por data: 15 dias seguidos passam pelas 15 sem repetir
    app = main.DailyQuestApp.__new__(main.DailyQuestApp)
    vistos = []
    for n in range(main.REMINDER_MESSAGE_COUNT):
        dia = date.today() + timedelta(days=n)
        i = dia.toordinal() % main.REMINDER_MESSAGE_COUNT + 1
        vistos.append(i18n.t(f"reminder_msg_{i:02d}", "pt"))
    assert len(set(vistos)) == main.REMINDER_MESSAGE_COUNT, \
        f"15 dias seguidos deviam dar as 15 mensagens, deram {len(set(vistos))}"

    # o texto do popup dentro do app sai sem emoji (o Kivy não desenha)
    assert all(ord(c) < main._GLIFO_MAX for c in main._sem_emoji(vistos[0])), vistos[0]
    # mas a notificação de sistema leva o emoji — pelo menos uma tem
    assert any(ord(c) >= main._GLIFO_MAX for t in vistos for c in t), \
        "nenhuma mensagem tem emoji — a graça era essa"

    print(f"OK — {main.REMINDER_MESSAGE_COUNT} mensagens distintas em "
          f"{len(i18n.TRANSLATIONS)} idiomas, uma por dia")


def run_render():
    tmp = tempfile.mkdtemp()
    import database as db
    db.DB_PATH = Path(tmp) / "c.db"
    db.init_db()
    import missions
    import settings
    settings.set_onboarding_done()
    missions.add_mission("Ler 10 páginas", "diaria", "media")
    missions.add_mission("Correr", "diaria", "facil")
    alvo = next(m for m in missions.list_missions() if m["name"] == "Correr")

    from kivy.clock import Clock
    from kivy.factory import Factory
    import main

    app = main.DailyQuestApp()
    r = {}

    def pedir(_dt):
        try:
            app.switch_screen("missions")
            app.on_remove_mission(alvo["id"])
            Clock.schedule_once(conferir, 0.5)
        except Exception:
            import traceback
            r["err"] = traceback.format_exc()
            app.stop()

    def conferir(_dt):
        try:
            from kivy.core.window import Window
            popups = [w for w in Window.children if isinstance(w, Factory.ConfirmPopup)]
            r["abriu"] = len(popups) == 1
            r["nomes_no_texto"] = "Correr" in (popups[0].message if popups else "")
            # o ponto principal: pedir NÃO pode ter apagado nada ainda
            r["ainda_existe"] = any(m["id"] == alvo["id"] for m in missions.list_missions())
            # cancelar fecha e mantém a missão
            popups[0].dismiss()
            Clock.schedule_once(depois_cancelar, 0.4)
        except Exception:
            import traceback
            r["err"] = traceback.format_exc()
            app.stop()

    def depois_cancelar(_dt):
        try:
            r["sobreviveu_ao_cancelar"] = any(
                m["id"] == alvo["id"] for m in missions.list_missions())
            app.on_remove_mission(alvo["id"])
            Clock.schedule_once(confirmar, 0.4)
        except Exception:
            import traceback
            r["err"] = traceback.format_exc()
            app.stop()

    def confirmar(_dt):
        try:
            from kivy.core.window import Window
            popup = next(w for w in Window.children if isinstance(w, Factory.ConfirmPopup))
            popup.confirm()
            Clock.schedule_once(fim, 0.4)
        except Exception:
            import traceback
            r["err"] = traceback.format_exc()
            app.stop()

    def fim(_dt):
        try:
            nomes = [m["name"] for m in missions.list_missions()]
            r["apagou"] = "Correr" not in nomes
            r["nao_levou_junto"] = "Ler 10 páginas" in nomes
        except Exception:
            import traceback
            r["err"] = traceback.format_exc()
        app.stop()

    Clock.schedule_once(pedir, 1.5)
    Clock.schedule_once(lambda _dt: app.stop(), 20)  # rede de segurança
    app.run()

    assert not r.get("err"), r["err"]
    assert r.get("abriu"), "apagar missão não abriu a confirmação"
    assert r.get("nomes_no_texto"), "a confirmação não diz QUAL missão vai sumir"
    assert r.get("ainda_existe"), "apagou antes de confirmar — é exatamente o bug"
    assert r.get("sobreviveu_ao_cancelar"), "cancelar não podia apagar a missão"
    assert r.get("apagou"), "confirmar não apagou a missão"
    assert r.get("nao_levou_junto"), "levou junto uma missão que não era pra apagar"
    print("OK — apagar missão pede confirmação, cancelar mantém, confirmar apaga")


if __name__ == "__main__":
    run_pool()  # puro, roda em qualquer lugar
    if os.environ.get("CI"):
        print("SKIP run_render() — CI headless (rode local pra checar o popup)")
    else:
        run_render()
