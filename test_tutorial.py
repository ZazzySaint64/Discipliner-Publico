"""Self-check do tutorial guiado: estrutura de TUTORIAL_STEPS + paridade das
traduções (run) e z-order do overlay (run_render, abre janela)."""
import os
import tempfile
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")


def run():
    import i18n

    # TUTORIAL_STEPS mora em main.py, que importa Kivy — pega a lista sem
    # instanciar o App. (No CI os test_*.py já rodam sob xvfb.)
    import main

    steps = main.TUTORIAL_STEPS
    assert len(steps) >= 10, "o tutorial 'completo' tem que ter uns 10+ passos"

    screens = {"missions", "settings"}
    keys_vistos = set()
    for i, s in enumerate(steps):
        assert set(s) == {"key", "screen", "target"}, f"passo {i} com chaves erradas: {s}"
        assert s["screen"] in screens, f"passo {i}: screen {s['screen']!r} fora de {screens}"
        assert s["target"] is None or (isinstance(s["target"], str) and s["target"]), \
            f"passo {i}: target inválido {s['target']!r}"
        assert s["key"] not in keys_vistos, f"key duplicada: {s['key']}"
        keys_vistos.add(s["key"])

    assert steps[0]["target"] is None, "o 1º passo (boas-vindas) é card centralizado, sem alvo"

    # todo passo tem título+corpo nos 5 idiomas; e o botão de rever também
    faltando = []
    for lang, table in i18n.TRANSLATIONS.items():
        if "btn_review_tutorial" not in table:
            faltando.append(f"{lang}: btn_review_tutorial")
        for s in steps:
            for suf in ("_title", "_body"):
                k = f"tutorial_{s['key']}{suf}"
                if k not in table:
                    faltando.append(f"{lang}: {k}")
    assert not faltando, "traduções faltando:\n  " + "\n  ".join(faltando)

    # não sobrou nenhuma chave tutorial_* órfã (dos 6 passos antigos)
    validas = {f"tutorial_{s['key']}{suf}" for s in steps for suf in ("_title", "_body")}
    orfas = sorted(
        k for k in i18n.TRANSLATIONS["pt"]
        if k.startswith("tutorial_") and k not in validas
    )
    assert not orfas, f"chaves tutorial_* órfãs em i18n.py: {orfas}"

    print(f"OK — {len(steps)} passos, traduções completas nos {len(i18n.TRANSLATIONS)} idiomas")


def run_render():
    """O TutorialOverlay tem que ficar POR CIMA do root no Window — senão fica
    invisível (o Kivy adiciona o root_widget ao Window depois de build() e
    Window.add_widget insere no children[0]/topo; por isso o overlay é anexado
    no on_start, não no build). Regressão do bug "tutorial não funciona a
    partir de Ajustes"."""
    tmp = tempfile.mkdtemp()
    import database as db
    db.DB_PATH = Path(tmp) / "t.db"
    db.init_db()
    import settings
    settings.set_onboarding_done()

    from kivy.clock import Clock
    from kivy.core.window import Window
    import main

    app = main.DailyQuestApp()
    result = {}

    def check(_dt):
        try:
            app.switch_screen("settings")
            app.tutorial_start()  # o que o botão "Rever tutorial" chama
        except Exception as e:
            result["err"] = repr(e)
            app.stop()
            return
        Clock.schedule_once(verify, 0.6)

    def verify(_dt):
        ov = app.tutorial_overlay
        result["on_top"] = bool(Window.children) and Window.children[0] is ov
        result["visible"] = ov.opacity == 1 and not ov.disabled
        result["screen"] = app.root_widget.ids.screen_manager.current
        # passo 0 abre Missões com dados reais -> não pode mentir "ilimitado"
        result["freeze_txt"] = app.freeze_status_text()
        # avança 1 passo por vez (com folga entre eles, como um toque real) até
        # um passo em Ajustes — regressão do "slide 14 travado": scroll_to +
        # to_window() lido cedo demais dava posição fora da tela e o card/anel
        # sumiam.
        import main as _m
        result["alvo"] = next(i for i, s in enumerate(_m.TUTORIAL_STEPS)
                              if s["screen"] == "settings")
        _advance(None)

    def _advance(_dt):
        if app.tutorial_step < result["alvo"]:
            app.tutorial_next()
            Clock.schedule_once(_advance, 0.5)
        else:
            Clock.schedule_once(check_settings_step, 1.2)

    def check_settings_step(_dt):
        ov = app.tutorial_overlay
        card = ov.ids.tut_card
        cx, cy = card.pos
        result["settings_card_onscreen"] = (
            -2 <= cx and -60 <= cy and cy + card.height <= ov.height + 4
        )
        result["settings_hole_onscreen"] = (
            ov.has_hole and -60 < ov.hole[1] < ov.height and ov.hole[3] > 1
        )
        # o anel tem que cercar o ALVO daquele passo, não só cair em algum
        # lugar da tela: com a checagem só de "está dentro da janela", um card
        # de largura inteira passava com a posição de ANTES do scroll_to e o
        # spotlight ia parar longe do card ("Escala rotativa" apontando errado)
        from kivy.metrics import dp as _dp
        import main as _m2
        alvo_id = _m2.TUTORIAL_STEPS[app.tutorial_step]["target"]
        alvo = app.root_widget.ids[alvo_id]
        ax, ay = alvo.to_window(alvo.x, alvo.y)
        pad = _dp(6)
        esperado = [ax - pad, ay - pad, alvo.width + 2 * pad, alvo.height + 2 * pad]
        result["hole_no_alvo"] = all(abs(a - b) <= 2 for a, b in zip(ov.hole, esperado))
        result["hole_debug"] = (list(ov.hole), esperado, alvo_id)
        result["settings_step_screen"] = app.root_widget.ids.screen_manager.current
        # agora encerra pelo "Pular" e confere que o scrim SOME de verdade
        app.tutorial_skip()
        Clock.schedule_once(after_skip, 0.4)

    def after_skip(_dt):
        ov = app.tutorial_overlay
        result["hidden"] = ov.disabled and ov.opacity == 0
        result["scrim_cleared"] = len(ov.canvas.before.children) == 0
        result["screen_after"] = app.root_widget.ids.screen_manager.current
        app.stop()

    Clock.schedule_once(check, 1.5)
    Clock.schedule_once(lambda _dt: app.stop(), 25)  # rede de segurança
    app.run()

    assert not result.get("err"), result["err"]
    assert result.get("on_top"), "overlay do tutorial NÃO está no topo do Window (children[0])"
    assert result.get("visible"), "overlay não ficou visível depois de tutorial_start()"
    assert result.get("screen") == "missions", result.get("screen")
    assert "ilimitad" not in result.get("freeze_txt", "").lower(), \
        f"congelamento não pode constar ilimitado sem premium: {result['freeze_txt']!r}"
    assert result.get("settings_step_screen") == "settings", result.get("settings_step_screen")
    assert result.get("settings_card_onscreen"), "card do passo em Ajustes ficou fora da tela"
    assert result.get("settings_hole_onscreen"), "spotlight do passo em Ajustes ficou fora da tela (scroll_to lido cedo demais)"
    assert result.get("hole_no_alvo"), \
        f"spotlight não cercou o alvo do passo: {result.get('hole_debug')}"
    assert result.get("hidden"), "overlay não ficou escondido depois do Pular"
    assert result.get("scrim_cleared"), "canvas.before do overlay não foi limpo — scrim fica na tela"
    assert result.get("screen_after") == "missions", result.get("screen_after")
    print("OK — overlay por cima, some no fim (scrim limpo), e não mente 'ilimitado'")


if __name__ == "__main__":
    run()  # estrutura + i18n: puro, roda em qualquer lugar
    # run_render() sobe o App inteiro (app.run()) e depende de timing de
    # frame/transição — instável no CI headless (SDL dummy). Roda só local.
    if os.environ.get("CI"):
        print("SKIP run_render() — CI headless (rode local pra checar z-order/scroll)")
    else:
        run_render()
