"""Recorta as poses do Focum da folha de sprites em assets/focum/raw/ e salva
cada uma como assets/focum/focum_<pose>.png com fundo transparente.

Fonte: Gemini_Generated_Image_e3zx91e3zx91e3zx.jpg — grade 5x3, personagem
sobre um xadrez de transparência (o .jpg não tem alfa de verdade). O recorte:

1. acha as calhas entre as células pela densidade de "tinta" (pixel que NÃO é
   o cinza claro do xadrez), então a grade não precisa ser exatamente uniforme;
2. marca como xadrez todo pixel quase-sem-cor-e-claro, e apaga (alfa 0) só o
   que está conectado à borda da célula — props claros DENTRO do personagem
   (garrafa, caneca, livro) ficam, isolados pelo contorno escuro;
3. mantém só o maior blob opaco (o personagem), descarta confete/quadro da
   célula vizinha que tenha vazado;
4. corta no bounding box, deixa quadrado e redimensiona.

Roda de novo quando a arte mudar:  python scripts/gen_focum.py
"""
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

APP_DIR = Path(__file__).resolve().parent.parent
SHEET = APP_DIR / "assets" / "focum" / "raw" / "Gemini_Generated_Image_e3zx91e3zx91e3zx.jpg"
OUT_DIR = APP_DIR / "assets" / "focum"
COLS, ROWS = 5, 3
OUT_SIZE = 512
PAD_FRAC = 0.06        # margem ao redor do personagem no quadro final
# Pega um pouco ALÉM da divisa da grade (não encolhe): o detector de calhas
# às vezes corta rente demais e raspava pé/mesa de algumas poses. O sobrando
# da célula vizinha (confete, quadro) que entrar aqui é descartado pelo
# _largest_blob, então dá pra ser generoso.
CELL_MARGIN = 0.045

# Célula (linha, coluna) 0-indexada da folha -> arquivo final. Poses sem
# equivalente (checklist, placa, calendário, vovó) ficam de fora.
#   (0,0) acenando       (0,1) lendo livro    (0,2) checklist "missões"
#   (0,3) joinha+piscada  (0,4) laptop em pé
#   (1,0) dormindo        (1,1) escrevendo     (1,2) correndo c/ garrafa
#   (1,3) comemorando     (1,4) meditando
#   (2,0) placa FFD       (2,1) laptop na mesa (2,2) segurando estrela
#   (2,3) escrevendo no quadro   (2,4) andando c/ mochila
POSE_MAP = {
    (0, 0): "focum_idle.png",
    (0, 3): "focum_thumbsup.png",
    (1, 0): "focum_sleeping.png",
    (1, 1): "focum_writing.png",
    (1, 2): "focum_walking.png",
    (1, 3): "focum_celebrating.png",
    (1, 4): "focum_meditating.png",
    (2, 1): "focum_studying.png",
    (2, 2): "focum_star.png",
    # tela do alarme de missão: segurando a lista "missões" e apontando pra
    # quem está olhando — é literalmente "ei, tem missão sua aqui"
    (0, 2): "focum_alarm.png",
}


def _is_checker(rgb):
    """True nos pixels do xadrez de transparência: quase sem cor e claros. Os
    tons do personagem (verde, bege, marrom) têm chroma bem maior."""
    a = np.asarray(rgb, dtype=np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    chroma = np.maximum(np.maximum(abs(r - g), abs(g - b)), abs(r - b))
    bright = np.minimum(np.minimum(r, g), b)
    return (chroma < 40) & (bright > 150)


def _cuts(profile, n):
    """Divide [0, len) em n faixas cortando na calha (vale de densidade) mais
    próxima de cada divisa uniforme. Janela de busca estreita: a folha já é
    quase uniforme, e janela larga deixava a divisa entrar no personagem."""
    total = len(profile)
    approx = [round(i * total / n) for i in range(n + 1)]
    bounds = [0]
    slack = max(8, total // (n * 12))
    for k in range(1, n):
        c = approx[k]
        lo, hi = max(bounds[-1] + 1, c - slack), min(total - 1, c + slack)
        window = profile[lo:hi]
        bounds.append(lo + int(window.argmin()) if len(window) else c)
    bounds.append(total)
    return list(zip(bounds[:-1], bounds[1:]))


def _border_connected(mask):
    """Sub-máscara de `mask` (bool) alcançável a partir da borda por 4-vizinhança.
    Usado pra apagar SÓ o xadrez que encosta na borda da célula — props claros
    dentro do personagem (garrafa, caneca, livro) ficam, porque o contorno
    escuro fechado os isola da borda."""
    h, w = mask.shape
    seen = np.zeros_like(mask)
    stack = deque()
    for x in range(w):
        for y in (0, h - 1):
            if mask[y, x] and not seen[y, x]:
                seen[y, x] = True
                stack.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if mask[y, x] and not seen[y, x]:
                seen[y, x] = True
                stack.append((y, x))
    while stack:
        y, x = stack.pop()
        for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
            if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                stack.append((ny, nx))
    return seen


def _largest_blob(alpha):
    """Zera tudo menos o maior componente conexo de alpha>0 (4-vizinhança)."""
    solid = alpha > 8
    seen = np.zeros_like(solid)
    best = None
    best_n = 0
    h, w = solid.shape
    for sy in range(0, h, 6):
        for sx in range(0, w, 6):
            if not solid[sy, sx] or seen[sy, sx]:
                continue
            stack = deque([(sy, sx)])
            seen[sy, sx] = True
            comp = []
            while stack:
                y, x = stack.pop()
                comp.append((y, x))
                for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                    if 0 <= ny < h and 0 <= nx < w and solid[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            if len(comp) > best_n:
                best_n, best = len(comp), comp
    keep = np.zeros_like(solid)
    if best:
        ys, xs = zip(*best)
        keep[list(ys), list(xs)] = True
    out = alpha.copy()
    out[~keep] = 0
    return out


def _cut_pose(cell):
    arr = np.array(cell.convert("RGBA"))
    checker = _is_checker(cell.convert("RGB"))
    bg = _border_connected(checker)          # xadrez que encosta na borda
    arr[bg, 3] = 0
    arr[..., 3] = _largest_blob(arr[..., 3])  # tira respingos/vazamento da vizinha
    img = Image.fromarray(arr)

    bbox = img.getchannel("A").getbbox()
    if bbox:
        img = img.crop(bbox)
    w, h = img.size
    side = int(max(w, h) * (1 + 2 * PAD_FRAC))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - w) // 2, (side - h) // 2), img)
    return canvas.resize((OUT_SIZE, OUT_SIZE), Image.LANCZOS)


def main():
    sheet = Image.open(SHEET).convert("RGB")
    W, H = sheet.size
    ink = (~_is_checker(sheet)).astype(np.uint32)
    col_bounds = _cuts(ink.sum(axis=0), COLS)
    row_bounds = _cuts(ink.sum(axis=1), ROWS)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for (r, c), name in POSE_MAP.items():
        x0, x1 = col_bounds[c]
        y0, y1 = row_bounds[r]
        mx, my = int((x1 - x0) * CELL_MARGIN), int((y1 - y0) * CELL_MARGIN)
        cell = sheet.crop((max(0, x0 - mx), max(0, y0 - my),
                           min(W, x1 + mx), min(H, y1 + my)))
        _cut_pose(cell).save(OUT_DIR / name)
        print(f"  {name:<24} <- celula ({r},{c})")
    print(f"{len(POSE_MAP)} poses geradas em {OUT_DIR}")


if __name__ == "__main__":
    main()
