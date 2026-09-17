"""Self-check das correções de interface: python test_ui_fixes.py

Cobre quatro coisas que só apareciam no celular:
- roda de cores (matiz = ângulo, saturação = raio)
- "voltar" do Android navegando em vez de fechar o app
- linha do "Desempenho por Missão" que cortava o texto de pontos
- fluxo de login por código removido
"""
import os
import tempfile
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")


def run_roda():
    """A roda converte posição de toque em matiz/saturação. Puro: não precisa
    de janela, só de instanciar o widget e simular o toque."""
    import math

    from widgets import AccentColorWheel

    roda = AccentColorWheel(size=(200, 200), pos=(0, 0))
    cx, cy, raio = 100, 100, 100

    class _Toque:
        def __init__(self, x, y):
            self.x, self.y = x, y
            self.pos = (x, y)

    casos = [
        (0, "direita = matiz 0 (vermelho)"),
        (90, "cima = matiz 90"),
        (180, "esquerda = matiz 180"),
        (270, "baixo = matiz 270"),
    ]
    for graus, descricao in casos:
        rad = math.radians(graus)
        # metade do raio => saturação 50%
        t = _Toque(cx + math.cos(rad) * raio * 0.5, cy + math.sin(rad) * raio * 0.5)
        assert roda._escolher(t), descricao
        assert abs(roda.hue - graus) < 1.5, f"{descricao}: veio matiz {roda.hue:.1f}"
        assert abs(roda.sat - 50) < 2, f"{descricao}: veio saturação {roda.sat:.1f}"

    # centro = sem cor; borda = cor pura
    assert roda._escolher(_Toque(cx, cy)) and roda.sat < 2, "centro devia zerar a saturação"
    assert roda._escolher(_Toque(cx + raio * 0.99, cy)) and roda.sat > 95, "borda devia saturar"

    # fora do círculo (canto do widget quadrado) não escolhe nada
    assert not roda._escolher(_Toque(1, 1)), "canto do quadrado está fora da roda"

    # o evento leva os dois valores juntos (é o que o kv liga em pick_custom_accent)
    recebidos = []
    roda.bind(on_pick=lambda _w, h, s: recebidos.append((h, s)))
    roda._escolher(_Toque(cx, cy + raio * 0.5))
    assert recebidos and abs(recebidos[-1][0] - 90) < 1.5, recebidos

    print("OK — roda de cores: ângulo vira matiz, raio vira saturação")


def run_sem_login_por_codigo():
    """O login por código de e-mail foi tirado: nem o botão, nem os métodos,
    nem as chaves de tradução podem ter sobrado (chave órfã aparece como texto
    cru na tela se alguém referenciar de novo)."""
    import i18n
    import main

    for metodo in ("request_settings_login_code", "confirm_settings_login_code",
                   "request_onboarding_login_code", "confirm_onboarding_login_code",
                   "_do_request_login_code", "_do_confirm_login_code"):
        assert not hasattr(main.DailyQuestApp, metodo), f"{metodo} ainda existe"
    assert not hasattr(main.DailyQuestApp, "account_otp_sent"), "a property do OTP ficou"
    # login agora é por link no e-mail (deep link), não código em popup
    assert not hasattr(main, "LoginCodePopup") and not hasattr(main.DailyQuestApp, "confirmar_login_codigo")

    import account
    for f in ("request_login_code", "login_with_code", "confirm_login_code"):
        assert not hasattr(account, f), f"account.{f} ficou sem chamador"

    mortas = {"btn_login_with_code", "otp_hint", "otp_sent_note",
              "btn_confirm_code", "err_otp_invalid", "err_otp_no_account"}
    for lang, tabela in i18n.TRANSLATIONS.items():
        sobrando = mortas & set(tabela)
        assert not sobrando, f"{lang}: chaves do fluxo de código ainda em i18n: {sobrando}"
        assert "btn_forgot_password" in tabela, f"{lang}: 'esqueci minha senha' sumiu junto"
        assert "custom_color_label" in tabela, f"{lang}: falta o rótulo da roda de cores"

    print("OK — login por código removido do app, do account.py e das traduções")


def run_render():
    """Voltar do Android e a linha do histórico. Sobe o App (precisa do kv)."""
    from kivy.clock import Clock
    from kivy.core.window import Window

    tmp = tempfile.mkdtemp()
    import database as db
    db.DB_PATH = Path(tmp) / "u.db"
    db.init_db()
    import missions
    import settings
    settings.set_onboarding_done()
    missions.add_mission("Beber 2L de água", "diaria", "facil")

    import main
    app = main.DailyQuestApp()
    r = {}

    def passo1(_dt):
        try:
            app.switch_screen("missions")
            app.switch_screen("history")
            app.switch_screen("settings")
            r["antes"] = app.current_screen
            # voltar duas vezes desfaz a navegação, sem fechar o app
            app._on_key(Window, 27)
            r["volta1"] = app.current_screen
            app._on_key(Window, 27)
            r["volta2"] = app.current_screen
            # na tela inicial, sem histórico, devolve False = sistema fecha
            app._screen_history.clear()
            r["na_raiz"] = app._on_key(Window, 27)
            # com popup aberto, voltar fecha o popup e não navega
            app.switch_screen("missions")
            app.open_suggestions_popup()
            Clock.schedule_once(passo2, 0.4)
        except Exception:
            import traceback
            r["err"] = traceback.format_exc()
            app.stop()

    def passo2(_dt):
        try:
            from kivy.uix.popup import Popup
            r["popup_aberto"] = any(isinstance(w, Popup) for w in Window.children)
            r["tratou_popup"] = app._on_key(Window, 27)
            Clock.schedule_once(passo3, 0.4)
        except Exception:
            import traceback
            r["err"] = traceback.format_exc()
            app.stop()

    def passo3(_dt):
        try:
            from kivy.uix.popup import Popup
            r["popup_fechado"] = not any(isinstance(w, Popup) for w in Window.children)
            r["tela_intacta"] = app.current_screen  # o popup não podia ter navegado

            # linha do "Desempenho por Missão" com o texto mais comprido
            from kivy.factory import Factory
            linha = Factory.MissionStatRow()
            linha.mission_name = "Beber 2L de chachaça"
            linha.completions_label = "3x"
            linha.points_label = "9 " + app.t("chart_points_label")
            from kivy.uix.gridlayout import GridLayout
            caixa = GridLayout(cols=1, size_hint_x=None, width=360)
            caixa.add_widget(linha)
            Window.add_widget(caixa)
            Clock.schedule_once(lambda _d: passo4(caixa, linha), 0.4)
        except Exception:
            import traceback
            r["err"] = traceback.format_exc()
            app.stop()

    def passo4(caixa, linha):
        try:
            pontos = linha.ids.pontos
            # o texto pode quebrar em 2 linhas; o que não pode é a linha ficar
            # menor que ele e cortar (era o bug do print)
            r["altura_linha"] = linha.height
            r["altura_texto"] = pontos.texture_size[1]
            r["cabe"] = linha.height >= pontos.texture_size[1]
            Window.remove_widget(caixa)
        except Exception:
            import traceback
            r["err"] = traceback.format_exc()
        app.stop()

    Clock.schedule_once(passo1, 1.5)
    Clock.schedule_once(lambda _dt: app.stop(), 20)
    app.run()

    assert not r.get("err"), r["err"]
    assert r.get("antes") == "settings", r.get("antes")
    assert r.get("volta1") == "history", f"1ª volta devia ir pra Histórico, foi pra {r.get('volta1')}"
    assert r.get("volta2") == "missions", f"2ª volta devia ir pra Missões, foi pra {r.get('volta2')}"
    assert r.get("na_raiz") is False, "sem histórico, o voltar tem que devolver False (deixar fechar)"
    assert r.get("popup_aberto"), "o popup nem chegou a abrir — teste não valeria nada"
    assert r.get("tratou_popup") is True, "voltar com popup aberto tinha que ser tratado"
    assert r.get("popup_fechado"), "voltar não fechou o popup"
    assert r.get("tela_intacta") == "missions", "voltar fechou o popup E navegou junto"
    assert r.get("cabe"), (
        f"texto de pontos ({r.get('altura_texto')}px) não cabe na linha "
        f"({r.get('altura_linha')}px) — volta a cortar como no print")
    print("OK — voltar navega (e fecha popup) sem encerrar o app; linha do histórico não corta")


if __name__ == "__main__":
    run_roda()
    run_sem_login_por_codigo()
    if os.environ.get("CI"):
        print("SKIP run_render() — CI headless (rode local)")
    else:
        run_render()
