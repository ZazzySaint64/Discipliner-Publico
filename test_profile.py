"""Self-check da tela de perfil + banner de fundo: python test_profile.py

Cobre o que a feature nova precisa garantir:
- banners.resolve devolve (pattern, cor) válidos, "none" pro desconhecido
- BannerArt desenha algo pros 6 patterns
- a tela "profile" existe e monta as 4 listas (banner/avatar/moldura/ícone)
- set_profile_banner reflete em banner_pattern/banner_color (o que o kv desenha)
- banner "custom" é Premium: sem Premium não entra; com Premium, a roda grava
"""
import os
import tempfile
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")


def run_banners():
    import banners

    banners.demo()  # asserts internos

    for b in banners.BANNERS:
        pat, col = banners.resolve(b["id"])
        assert pat in ("none",) + banners.PATTERNS, (b["id"], pat)
        assert len(col) == 4

    from widgets import BannerArt
    for pat in banners.PATTERNS:
        art = BannerArt(pattern=pat, color=[0.3, 0.4, 0.6, 1], size=(120, 40), pos=(0, 0))
        assert art.canvas.before.length() > 0, f"BannerArt não desenhou o pattern {pat}"
    # pattern "none" / cor transparente: não desenha nada
    art = BannerArt(pattern="none", color=[0, 0, 0, 0], size=(120, 40))
    assert art.canvas.before.length() == 0
    print("OK — banners.resolve + BannerArt desenha os 6 patterns")


def run_screen():
    tmp = tempfile.mkdtemp()
    import database as db
    db.DB_PATH = Path(tmp) / "u.db"
    db.init_db()
    import settings
    settings.set_onboarding_done()

    import banners
    import main
    app = main.DailyQuestApp()
    app.build()
    ids = app.root_widget.ids

    sm = ids["screen_manager"]
    assert "profile" in [s.name for s in sm.screens], "tela 'profile' não existe"

    app.switch_screen("profile")
    for k, minimo in (("prof_banner_list", 6), ("prof_avatar_list", 1),
                      ("prof_frame_list", 5), ("prof_icon_list", 5)):
        n = len(ids[k].children)
        assert n >= minimo, f"{k}: {n} filhos (esperado >= {minimo})"

    # preset livre: reflete no que o kv desenha + marca o thumb
    app.set_profile_banner("ocean")
    assert app.banner_pattern == "gradient" and app.banner_color[3] == 1
    sel = [t for t in ids["prof_banner_list"].children
           if type(t).__name__ == "BannerThumb" and t.selected]
    assert len(sel) == 1 and sel[0].banner_id == "ocean"

    app.set_profile_banner("none")
    assert app.banner_pattern == "none" and app.banner_color == [0, 0, 0, 0]

    # "custom" é Premium
    app.is_premium = False
    app.set_profile_banner("custom")
    assert app.profile_banner != "custom", "custom não deveria entrar sem Premium"
    app.pick_custom_banner(300, 80)
    assert app.profile_banner != "custom", "pick_custom_banner não deveria funcionar sem Premium"

    app.is_premium = True
    app.set_profile_banner("custom")
    assert app.profile_banner == "custom"
    app.set_custom_banner_pattern("chevron")
    app.pick_custom_banner(300, 80)
    pat, col = banners.resolve("custom", app.custom_banner_hue, app.custom_banner_sat,
                               app.custom_banner_pattern)
    assert app.banner_pattern == pat == "chevron"
    assert app.custom_banner_hue == 300
    # persistiu no banco
    assert settings.get_settings()["profile_banner"] == "custom"

    # o painel do banner personalizado NÃO pode virar widget fantasma por cima
    # da grade de banners quando escondido: a roda HSV com tamanho antigo
    # engolia o toque nos thumbs. Escondido => roda com tamanho ~0.
    from kivy.uix.anchorlayout import AnchorLayout

    def walk(w):
        yield w
        for c in w.children:
            yield from walk(c)

    prof = sm.get_screen("profile")
    wheel = next(w for w in walk(prof) if type(w).__name__ == "AccentColorWheel")
    app.set_profile_banner("custom")            # painel aberto
    assert wheel.width > 100, f"roda deveria aparecer com o painel aberto ({wheel.width})"
    app.set_profile_banner("ocean")             # painel fechado
    assert wheel.width <= 1 and wheel.height <= 1, \
        f"roda ficou {wheel.size} com o painel fechado — vira fantasma e come toque nos thumbs"

    print("OK — tela profile monta as listas; banner preset/custom e Premium; "
          "painel custom não vira fantasma")


if __name__ == "__main__":
    run_banners()
    run_screen()
    print("todos os checks de perfil passaram")
