"""Self-check das abas de tipo de missão: python test_missoes_periodo.py

Na tela Missões, 3 abas (Diárias / Semanais / Mensais) trocam a lista, o
progresso e a sequência pro tipo escolhido — concluir a semanal não mexe no
progresso das diárias. A pílula "Sequências" continua lá em cima."""
import os
import tempfile
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")


def run_logica():
    tmp = tempfile.mkdtemp()
    import database as db
    db.DB_PATH = Path(tmp) / "l.db"
    db.init_db()
    import missions

    missions.add_mission("Ler", "diaria", "facil")
    missions.add_mission("Faxina", "semanal", "media")
    missions.add_mission("Contas", "mensal", "dificil")
    semanal = next(m for m in missions.list_missions() if m["name"] == "Faxina")
    missions.complete_mission(semanal["id"], "")
    assert missions.progress_today("semanal") == 1.0
    assert missions.progress_today("diaria") == 0.0, "concluir a semanal não pode mexer nas diárias"
    assert missions.progress_today("mensal") == 0.0
    assert abs(missions.progress_today() - 1 / 3) < 1e-9, "sem filtro continua sendo o geral"
    print("OK — progresso por tipo de missão")


def run_abas():
    tmp = tempfile.mkdtemp()
    import database as db
    db.DB_PATH = Path(tmp) / "t.db"
    db.init_db()
    import missions
    import settings
    settings.set_onboarding_done()
    missions.add_mission("Ler", "diaria", "facil")
    missions.add_mission("Faxina", "semanal", "media")
    missions.add_mission("Contas", "mensal", "dificil")

    from kivy.clock import Clock
    import main

    app = main.DailyQuestApp()
    r = {}

    def nomes():
        return sorted(w.text_name for w in app.root_widget.ids.missions_list.children)

    def passo(_dt):
        try:
            app.switch_screen("missions")
            app.refresh_missions()
            tela = app.root_widget.ids.screen_manager.get_screen("missions")
            textos = [w.text for w in tela.walk() if isinstance(getattr(w, "text", None), str)]
            r["tem_sequencias"] = app.t("streaks_title") in textos
            r["tres_abas"] = all(app.t(k).upper() in [t.upper() for t in textos]
                                 for k in ("chip_daily", "chip_weekly", "chip_monthly"))
            r["diarias"] = nomes()

            app.set_mission_view("semanal")
            r["semanais"], r["tela"] = nomes(), app.current_screen
            faxina = next(m for m in missions.list_missions() if m["name"] == "Faxina")
            missions.complete_mission(faxina["id"], "")
            app.refresh_after_complete()
            r["prog_semanal"] = app.progress

            app.set_mission_view("mensal")
            r["mensais"], r["prog_mensal"] = nomes(), app.progress
            app.set_mission_view("diaria")
            r["volta_diarias"], r["prog_diaria"] = nomes(), app.progress
        except Exception:
            import traceback
            r["err"] = traceback.format_exc()
        app.stop()

    Clock.schedule_once(passo, 4)  # depois do splash
    Clock.schedule_once(lambda _dt: app.stop(), 25)
    app.run()

    assert not r.get("err"), r["err"]
    assert r["tem_sequencias"], "a pílula Sequências tinha que voltar"
    assert r["tres_abas"], "faltam as abas Diárias/Semanais/Mensais"
    assert r["diarias"] == ["Ler"], r["diarias"]
    assert r["tela"] == "missions", "trocar de aba não pode sair da tela Missões"
    assert r["semanais"] == ["Faxina"] and r["mensais"] == ["Contas"], r
    assert r["volta_diarias"] == ["Ler"], r
    assert r["prog_semanal"] == 1.0 and r["prog_mensal"] == 0.0 and r["prog_diaria"] == 0.0, r
    print("OK — abas Diárias/Semanais/Mensais: lista e progresso só do tipo escolhido")


if __name__ == "__main__":
    run_logica()
    run_abas()
