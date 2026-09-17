"""Gera assets/icon.png e assets/icons_alt/*.png a partir da arte do Focum em
assets/focum/raw/ (ver README > Recompensas). Roda de novo sempre que a arte
mudar (python scripts/gen_alt_icons.py).

icon.png = versão de cores normais (recorte "ChatGPT Image 3 de set...").
ic_bronze/ic_prata/ic_ouro/ic_diamante = variantes desenhadas à mão, com o
fundo preto do mockup removido por flood fill a partir dos cantos (o
diamante já veio com fundo transparente, o flood fill não faz nada nele).
"""
from pathlib import Path

from PIL import Image, ImageDraw

APP_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = APP_DIR / "assets" / "focum" / "raw"
ICON_PATH = APP_DIR / "assets" / "icon.png"
# presplash = a tela de carregamento (nativa e a do Kivy). Fica sobre bg_app,
# então precisa do recorte COM alfa: o icon.png virou opaco e sangrando até a
# borda de propósito (ver cheio()), e usar ele aqui pintava um quadrado verde.
PRESPLASH_PATH = APP_DIR / "assets" / "presplash_icon.png"
OUT_DIR = APP_DIR / "assets" / "icons_alt"
SIZE = 512

DEFAULT_SRC = RAW_DIR / "ChatGPT Image 3 de set. de 2026, 11_31_46.png"
TIER_SRC = {
    "ic_bronze": RAW_DIR / "WhatsApp Image 2026-09-04 at 11.44.53 (2).jpeg",
    "ic_prata": RAW_DIR / "WhatsApp Image 2026-09-04 at 11.44.53 (1).jpeg",
    "ic_ouro": RAW_DIR / "WhatsApp Image 2026-09-04 at 11.44.53.jpeg",
    "ic_diamante": RAW_DIR / "diamante.png",
}

# --- ícone adaptativo (Android 8+) ---
# Sem declarar ícone adaptativo, o launcher aplica "legacy icon treatment":
# encolhe o bitmap e centraliza dentro da máscara, com margem. Era por isso que
# o ícone aparecia bem menor que o dos outros apps. Com as camadas abaixo o
# launcher desenha o ícone inteiro, do tamanho certo.
#
# O canvas adaptativo tem 108dp, mas a máscara só garante os 72dp centrais —
# o resto pode ser cortado (cada fabricante usa um formato: círculo, squircle,
# etc.). Por isso a arte é reduzida pra SAFE_RATIO do canvas e centralizada:
# fora dessa zona segura, o pedaço que sobra pode simplesmente sumir.
SAFE_RATIO = 0.70
# Verde do próprio selo, amostrado das bordas internas de assets/icon.png.
# ANTES era #121212 (quase preto): a camada de fundo do ícone adaptativo não
# combinava com a arte, e qualquer sobra em volta do mascote aparecia como
# moldura escura. Com o verde do selo, a sobra some visualmente.
BG_RGBA = (38, 84, 42, 255)


def remove_black_corners(img, thresh=40):
    """Flood fill preto->transparente a partir dos 4 cantos. Não vaza pro
    desenho porque pupila/sombra internas não têm caminho até a borda."""
    img = img.convert("RGBA")
    w, h = img.size
    for corner in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        if img.getpixel(corner)[:3] <= (thresh, thresh, thresh):
            ImageDraw.floodfill(img, corner, (0, 0, 0, 0), thresh=thresh)
    return img


def cheio(icon):
    """Versão OPACA e sem margem: a arte recortada pelo alfa, esticada até
    encostar nas 4 bordas, sobre o verde do selo.

    É o que resolve a "borda branca grossa" no launcher: `icon.filename` tinha
    margem transparente E cantos vazados, e o Android, quando cai no legacy
    icon treatment (ícone não-adaptativo), põe um PLATE BRANCO atrás e encolhe
    o desenho dentro dele. Sem alfa nenhum não há plate: o launcher usa o
    quadrado inteiro e só aplica a máscara dele por cima."""
    bbox = icon.getchannel("A").getbbox() or (0, 0, icon.width, icon.height)
    arte = icon.crop(bbox).resize((SIZE, SIZE), Image.LANCZOS)
    fundo = Image.new("RGBA", (SIZE, SIZE), BG_RGBA)
    fundo.alpha_composite(arte)
    return fundo.convert("RGB")   # RGB puro: garante zero transparência


def foreground(icon, destino):
    """Camada de frente do ícone adaptativo: a arte recortada (sem a margem
    transparente que ela já tenha) e reduzida pra zona segura, centralizada num
    canvas transparente do tamanho cheio."""
    bbox = icon.getchannel("A").getbbox() or (0, 0, icon.width, icon.height)
    arte = icon.crop(bbox)
    lado = round(SIZE * SAFE_RATIO)
    arte.thumbnail((lado, lado), Image.LANCZOS)

    camada = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    camada.paste(arte, ((SIZE - arte.width) // 2, (SIZE - arte.height) // 2))
    camada.save(destino)


ADAPTIVE_XML = """<?xml version="1.0" encoding="utf-8"?>
<!-- Gerado por scripts/gen_alt_icons.py — não editar à mão. -->
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="{fundo}" />
    <foreground android:drawable="@drawable/{nome}_fg" />
</adaptive-icon>
"""
# Fundo do ícone PADRÃO: transparente, não o verde do selo.
#
# A camada de fundo preenche o canvas de 108dp inteiro. No launcher isso não
# aparece (a máscara corta), mas TODO lugar que desenha o ícone sem máscara —
# a tela de carregamento do Android 12+, a caixa de consentimento do AdMob
# (a que tem os termos de uso), diálogos do sistema — mostrava o quadrado
# verde inteiro com o selo pequeno no meio. Sem fundo, esses lugares mostram
# só o selo, que já é arredondado e tem alfa.
#
# O tamanho no launcher NÃO muda por causa disso: SAFE_RATIO (0.70) já faz a
# arte preencher quase exatamente a zona garantida pela máscara (72/108 =
# 0,67), então o selo continua ocupando o espaço inteiro do ícone.
FUNDO_TRANSPARENTE = "@android:color/transparent"
FUNDO_TIER = "@drawable/ic_tier_bg"


def build():
    OUT_DIR.mkdir(exist_ok=True)

    default_icon = Image.open(DEFAULT_SRC).convert("RGBA").resize((SIZE, SIZE), Image.LANCZOS)
    # icon.png (o que o buildozer usa em icon.filename/presplash) sai OPACO e
    # sangrando até a borda — ver cheio()
    cheio(default_icon).save(ICON_PATH)
    default_icon.save(PRESPLASH_PATH)   # com alfa, recortado — ver PRESPLASH_PATH

    tiers = {}
    for name, src in TIER_SRC.items():
        img = remove_black_corners(Image.open(src)).resize((SIZE, SIZE), Image.LANCZOS)
        img.save(OUT_DIR / f"{name}.png")
        tiers[name] = img

    # Camadas adaptativas do ícone PADRÃO. As chaves icon.adaptive_icon_* do
    # buildozer foram testadas num APK real e NÃO surtem efeito aqui: o
    # manifesto sai com android:icon="@mipmap/icon" apontando pro PNG puro, e
    # o launcher encolhe ele (legacy icon treatment). Então o ícone padrão
    # entra pelo MESMO caminho dos tiers — recurso via android.add_resources,
    # com o XML adaptativo em mipmap-anydpi-v26/ usando o mesmo NOME de
    # recurso ("icon") que o PNG, pro Android 8+ preferir o XML.
    fundo = Image.new("RGBA", (SIZE, SIZE), BG_RGBA)
    foreground(default_icon, APP_DIR / "assets" / "icon_fg.png")
    (APP_DIR / "assets" / "icon_adaptive.xml").write_text(
        ADAPTIVE_XML.format(nome="icon", fundo=FUNDO_TRANSPARENTE), encoding="utf-8")

    # e as dos <activity-alias> dos ícones desbloqueáveis, que o buildozer não
    # conhece — entram como recurso via android.add_resources. O PNG cheio
    # continua em drawable/ (Android 7 e anterior); o XML adaptativo vai pra
    # drawable-anydpi-v26/ com o MESMO nome, e o Android 8+ prefere ele.
    fundo.save(OUT_DIR / "ic_tier_bg.png")
    for name, img in tiers.items():
        foreground(img, OUT_DIR / f"{name}_fg.png")
        (OUT_DIR / f"{name}_adaptive.xml").write_text(
            ADAPTIVE_XML.format(nome=name, fundo=FUNDO_TIER), encoding="utf-8")


if __name__ == "__main__":
    build()
    print(f"OK — icon.png + {len(TIER_SRC) + 1} ícones em {OUT_DIR}, "
          f"com camadas adaptativas (_fg.png + _adaptive.xml) e ic_tier_bg.png")
