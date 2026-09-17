"""Banner de fundo do cabeçalho (estilo banner de perfil do Discord) — cobre a
faixa rente à foto de perfil, visível em todas as telas.

Cada banner é um PADRÃO desenhado no canvas (widgets.BannerArt), não uma
imagem: assim o "personalizado" (cor escolhida na roda HSV, igual à Cor
Personalizada do accent) reaproveita o mesmo desenho com outra cor, sem
precisar gerar arte.

5 presets grátis + "custom" (Premium): matiz/saturação da roda + um dos
PATTERNS. "none" = sem banner (cabeçalho fica igual a antes, fundo bg_app).
"""
import colorsys

# id -> (pattern, cor base). Cores em valor médio (~0.5) de propósito: o texto
# do cabeçalho é quase branco no tema escuro e precisa continuar legível por
# cima — o BannerArt ainda joga um veuzinho de bg_app em cima pra garantir.
BANNERS = [
    {"id": "none",   "pattern": "none",     "color": None},
    {"id": "ocean",  "pattern": "gradient", "color": (0.15, 0.40, 0.60, 1)},
    {"id": "sunset", "pattern": "gradient", "color": (0.74, 0.38, 0.32, 1)},
    {"id": "grove",  "pattern": "stripes",  "color": (0.28, 0.44, 0.34, 1)},
    {"id": "violet", "pattern": "dots",     "color": (0.42, 0.31, 0.54, 1)},
    {"id": "slate",  "pattern": "grid",     "color": (0.30, 0.33, 0.40, 1)},
]

# estilos que o "personalizado" oferece (o BannerArt sabe desenhar todos)
PATTERNS = ("solid", "gradient", "stripes", "dots", "grid", "chevron")

_EMPTY = ("none", (0, 0, 0, 0))


def ids():
    return [b["id"] for b in BANNERS]


def custom_color(hue, sat):
    """Matiz 0-360 + saturação 0-100 -> rgba. Brilho fixo (0.5) pra ficar
    legível no claro e no escuro — mesma ideia do custom_accent_variants."""
    h = (hue % 360) / 360
    s = max(0.0, min(1.0, sat / 100))
    r, g, b = colorsys.hsv_to_rgb(h, s, 0.5)
    return (r, g, b, 1)


def resolve(banner_id, custom_hue=210, custom_sat=45, custom_pattern="solid"):
    """(pattern, cor) do banner atual, pro BannerArt desenhar.

    "none"/id desconhecido -> ("none", transparente) — o BannerArt não desenha
    nada e o cabeçalho fica igual a antes.
    """
    if banner_id == "custom":
        pattern = custom_pattern if custom_pattern in PATTERNS else "solid"
        return pattern, custom_color(custom_hue, custom_sat)
    entry = next((b for b in BANNERS if b["id"] == banner_id), None)
    if not entry or entry["pattern"] == "none":
        return _EMPTY
    return entry["pattern"], entry["color"]


def demo():
    assert resolve("none") == _EMPTY
    assert resolve("desconhecido") == _EMPTY
    p, c = resolve("ocean")
    assert p == "gradient" and len(c) == 4
    # custom: pattern inválido cai em "solid", cor vem da roda
    p, c = resolve("custom", 120, 80, "zigzag")
    assert p == "solid" and 0.0 <= c[0] <= 1.0 and c[3] == 1
    p, c = resolve("custom", 0, 100, "stripes")
    assert p == "stripes"
    # saturação 0 => cinza (r==g==b)
    r, g, b, _ = custom_color(200, 0)
    assert abs(r - g) < 1e-6 and abs(g - b) < 1e-6
    print("OK — banners.resolve")


if __name__ == "__main__":
    demo()
