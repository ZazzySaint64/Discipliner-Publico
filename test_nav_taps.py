"""Self-check: python test_nav_taps.py

Regressão do bug "os botões são clicados mas raramente processam o clique":
`ScreenManager.on_touch_down` retorna False enquanto `transition.is_active`,
então durante a transição de tela TODO toque num botão da tela nova some sem
feedback. O SlideTransition padrão dura 0.4s — uma janela morta enorme depois
de cada navegação. Fix: `transition: SlideTransition(duration=0.13)` no ui.kv.

O teste trava a duração num teto baixo e confirma que, fora de transição, o
toque num botão dispara normalmente.
"""
import os

os.environ.setdefault("KIVY_NO_ARGS", "1")

MAX_TRANSITION_S = 0.15


def run():
    from kivy.base import EventLoop
    from kivy.clock import Clock
    from kivy.input.motionevent import MotionEvent

    import main

    class FakeTouch(MotionEvent):
        def __init__(self, x, y):
            win = EventLoop.window
            self.grab_list = []
            super().__init__("t", 1, {"x": x / float(win.width), "y": y / float(win.height)})
            self.scale_for_screen(win.width, win.height)

        def depack(self, args):
            self.is_touch = True
            self.sx, self.sy = args["x"], args["y"]
            self.profile = ["pos"]
            super().depack(args)

    app = main.DailyQuestApp()
    out = {}

    def drive(_dt):
        # espera o splash acabar: o _finish_splash troca pra Missões, e se ele
        # cair DEPOIS do switch_screen abaixo o toque vai pra tela errada. Um
        # atraso fixo não bastava — o fim do splash varia com a máquina
        if app.current_screen == "splash":
            Clock.schedule_once(drive, 0.2)
            return
        sm = app.root_widget.ids["screen_manager"]
        out["duration"] = float(sm.transition.duration)
        app.onboarding_done = True
        app.switch_screen("rewards_shop")

        def tap_at_rest(_dt):
            # bem depois da transição: o toque tem que pegar
            scr = sm.get_screen("rewards_shop")
            b = next(w for w in _walk(scr)
                     if type(w).__name__ == "ClayButton" and w.width > 1)
            fired = {"v": False}
            b.fbind("on_release", lambda *a: fired.__setitem__("v", True))
            px, py = b.to_window(*b.center)
            t = FakeTouch(px, py)
            EventLoop.post_dispatch_input("begin", t)
            EventLoop.post_dispatch_input("end", t)
            out["rest_tap_fired"] = fired["v"]
            app.stop()

        Clock.schedule_once(tap_at_rest, 0.5)

    def _walk(w):
        yield w
        for c in w.children:
            yield from _walk(c)

    _orig = app.on_start

    def on_start2():
        if _orig:
            _orig()
        Clock.schedule_once(drive, 4.0)

    app.on_start = on_start2
    app.run()

    assert out["duration"] <= MAX_TRANSITION_S, (
        f"transição de tela dura {out['duration']}s (teto {MAX_TRANSITION_S}s) — "
        "acima disso a navegação come clique demais (ScreenManager ignora toque "
        "durante a transição)")
    assert out.get("rest_tap_fired") is True, "toque num botão em repouso não disparou"
    print(f"OK — transição curta ({out['duration']}s); toque em botão fora de transição OK")


if __name__ == "__main__":
    run()
    print("check de navegação+toque passou")
