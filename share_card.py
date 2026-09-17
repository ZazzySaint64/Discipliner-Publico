"""Gera uma imagem quadrada (1080x1080, tamanho bom pra Instagram/stories) com
a sequência atual do usuário, pra compartilhar. Tudo local — só desenha um PNG
e devolve, sem servidor nem rede (mesma filosofia do resto do app). PIL já é
dependência do projeto (foi usado pra recortar os assets do Focum).

Textos já vêm traduzidos de quem chama (main.py) — este módulo só desenha,
não sabe de i18n, mesma separação que o resto do app já usa."""
from pathlib import Path

from kivy.utils import platform

# PIL importado dentro das funções, não no topo: ~110ms de import que só
# interessa a quem toca em "compartilhar". main.py também importa este módulo
# sob demanda (ver _lazy_share_card). Depois da 1ª vez é lookup em sys.modules.

SIZE = 1080

# mesmas fontes que o app já usa (main.py) — só existem de verdade no Windows;
# fora dele cai pro bitmap padrão do Pillow (feio, mas não quebra a geração)
_TITLE_FONT_PATH = r"C:\Windows\Fonts\trebucbd.ttf"
_BODY_FONT_PATH = r"C:\Windows\Fonts\Candarab.ttf"


def _font(path, size):
    from PIL import ImageFont
    if platform == "win" and Path(path).exists():
        return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def _rgb255(rgba_float):
    return tuple(round(c * 255) for c in rgba_float[:3])


def generate(dest_path, streak_days, streak_word, level_text, avatar_path, bg_color, accent_color, text_color):
    """streak_word já vem no plural/singular certo ("dia"/"dias" traduzido).
    level_text já vem pronto ("Nível 5 · 320 pontos", já traduzido)."""
    from PIL import Image, ImageDraw
    bg = _rgb255(bg_color)
    accent = _rgb255(accent_color)
    text = _rgb255(text_color)

    img = Image.new("RGB", (SIZE, SIZE), bg)
    draw = ImageDraw.Draw(img)

    title_font = _font(_TITLE_FONT_PATH, 64)
    number_font = _font(_TITLE_FONT_PATH, 220)
    body_font = _font(_BODY_FONT_PATH, 42)
    small_font = _font(_BODY_FONT_PATH, 34)

    draw.text((SIZE / 2, 90), "Discipliner", font=title_font, fill=accent, anchor="mm")

    if avatar_path and Path(avatar_path).exists():
        mascot = Image.open(avatar_path).convert("RGBA")
        target_h = 340
        ratio = target_h / mascot.height
        mascot = mascot.resize((round(mascot.width * ratio), target_h))
        img.paste(mascot, (round(SIZE / 2 - mascot.width / 2), 220), mascot)

    draw.text((SIZE / 2, 690), str(streak_days), font=number_font, fill=text, anchor="mm")
    draw.text((SIZE / 2, 815), streak_word, font=body_font, fill=accent, anchor="mm")
    draw.text((SIZE / 2, 910), level_text, font=small_font, fill=text, anchor="mm")

    img.save(dest_path)


def generate_certificate(dest_path, milestone_days, title_text, subtitle_text, avatar_path, bg_color, accent_color, text_color):
    """Versão "certificado" do cartão acima — pros marcos grandes de sequência
    (7/14/30/100 dias, ver main.DAILY_STREAK_MILESTONES). Layout mais formal
    (moldura dupla) em vez do cartão do dia a dia (generate())."""
    from PIL import Image, ImageDraw
    bg = _rgb255(bg_color)
    accent = _rgb255(accent_color)
    text = _rgb255(text_color)

    img = Image.new("RGB", (SIZE, SIZE), bg)
    draw = ImageDraw.Draw(img)

    margin = 40
    draw.rectangle([margin, margin, SIZE - margin, SIZE - margin], outline=accent, width=6)
    draw.rectangle([margin + 16, margin + 16, SIZE - margin - 16, SIZE - margin - 16], outline=accent, width=2)

    title_font = _font(_TITLE_FONT_PATH, 54)
    number_font = _font(_TITLE_FONT_PATH, 260)
    body_font = _font(_BODY_FONT_PATH, 46)
    small_font = _font(_BODY_FONT_PATH, 32)

    draw.text((SIZE / 2, 130), title_text, font=title_font, fill=accent, anchor="mm")
    draw.text((SIZE / 2, 200), "Discipliner", font=small_font, fill=text, anchor="mm")

    if avatar_path and Path(avatar_path).exists():
        mascot = Image.open(avatar_path).convert("RGBA")
        target_h = 260
        ratio = target_h / mascot.height
        mascot = mascot.resize((round(mascot.width * ratio), target_h))
        img.paste(mascot, (round(SIZE / 2 - mascot.width / 2), 250), mascot)

    draw.text((SIZE / 2, 640), str(milestone_days), font=number_font, fill=text, anchor="mm")
    draw.text((SIZE / 2, 830), subtitle_text, font=body_font, fill=accent, anchor="mm")

    img.save(dest_path)
