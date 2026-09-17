"""Recorta os 5 ícones da barra de abas da folha em assets/focum/raw/ e salva
como assets/nav/nav_<aba>.png — silhueta BRANCA com fundo transparente.

Fonte: nav_icons_sheet.jpg — 5 ícones brancos em linha (checkmark, relógio,
gráfico de barras, estrela, engrenagem) sobre um xadrez de transparência, com
rótulos embaixo (que a gente descarta).

Branco chapado de propósito: a barra pinta o ícone com `Image.color`
(app.accent quando ativa, app.muted quando não) — um PNG branco tinge liso.
Por isso até os ponteiros escuros do relógio viram parte da silhueta branca.

Roda de novo se a arte mudar:  python scripts/gen_nav_icons.py
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

APP_DIR = Path(__file__).resolve().parent.parent
SHEET = APP_DIR / "assets" / "focum" / "raw" / "nav_icons_sheet.jpg"
OUT_DIR = APP_DIR / "assets" / "nav"
NAMES = ["nav_missions", "nav_history", "nav_chart", "nav_badges", "nav_settings"]
BAND = (0.36, 0.60)     # faixa vertical dos ícones (fração da altura) — sem os rótulos
OUT_SIZE = 128
PAD_FRAC = 0.10


def _ink(rgb):
    """True no traço do ícone; False no xadrez de transparência.

    O xadrez é cinza NEUTRO (chroma ~0), claro ou escuro (brilho 86-162). O
    ícone é branco (>200) OU, no caso dos ponteiros do relógio, azul-acinzentado
    (chroma alto) — que no brilho se confunde com o xadrez escuro, então separa
    por chroma. Sem flood da borda: o furo do checkmark/relógio é xadrez CERCADO
    pelo traço; border-connected deixaria ele opaco e o ícone virava um blob."""
    a = np.asarray(rgb, dtype=np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    bright = (r + g + b) / 3.0
    chroma = np.maximum(np.maximum(abs(r - g), abs(g - b)), abs(r - b))
    return (bright > 195) | (chroma > 16)


def _col_bounds(band, n):
    """Divisas entre os n ícones: vales da densidade de tinta por coluna."""
    ink = _ink(band).sum(axis=0).astype(float)
    total = len(ink)
    bounds = [0]
    for k in range(1, n):
        c = round(k * total / n)
        slack = total // (n * 5)
        lo, hi = max(bounds[-1] + 1, c - slack), min(total - 1, c + slack)
        win = ink[lo:hi]
        bounds.append(lo + int(win.argmin()) if len(win) else c)
    bounds.append(total)
    return list(zip(bounds[:-1], bounds[1:]))


def _icon(cell):
    alpha = np.where(_ink(cell.convert("RGB")), 255, 0).astype(np.uint8)
    # blur leve = anti-alias na borda do traço (o corte binário serrilha muito
    # no downscale pra dp(24))
    a_img = Image.fromarray(alpha, "L").filter(ImageFilter.GaussianBlur(0.8))
    white = Image.new("RGBA", cell.size, (255, 255, 255, 0))
    white.putalpha(a_img)

    bbox = white.getchannel("A").getbbox()
    if bbox:
        white = white.crop(bbox)
    w, h = white.size
    side = int(max(w, h) * (1 + 2 * PAD_FRAC))
    canvas = Image.new("RGBA", (side, side), (255, 255, 255, 0))
    canvas.paste(white, ((side - w) // 2, (side - h) // 2), white)
    return canvas.resize((OUT_SIZE, OUT_SIZE), Image.LANCZOS)


def main():
    sheet = Image.open(SHEET).convert("RGB")
    W, H = sheet.size
    y0, y1 = int(H * BAND[0]), int(H * BAND[1])
    band = sheet.crop((0, y0, W, y1))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for (x0, x1), name in zip(_col_bounds(band, len(NAMES)), NAMES):
        cell = band.crop((x0, 0, x1, band.height))
        _icon(cell).save(OUT_DIR / f"{name}.png")
        print(f"  {name}.png  <- x[{x0}:{x1}]")
    print(f"{len(NAMES)} ícones em {OUT_DIR}")


if __name__ == "__main__":
    main()
