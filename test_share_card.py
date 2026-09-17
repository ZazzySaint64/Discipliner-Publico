"""Self-check: python test_share_card.py (não precisa do Kivy, só Pillow)."""
import tempfile
from pathlib import Path

from PIL import Image

import share_card

APP_DIR = Path(__file__).parent


def run():
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "cartao.png"
        avatar = APP_DIR / "assets" / "focum" / "focum_idle.png"

        share_card.generate(
            dest, streak_days=12, streak_word="dias", level_text="Nível 3 · 120 Pontos no Mês",
            avatar_path=str(avatar), bg_color=(0.071, 0.071, 0.071, 1),
            accent_color=(0.53, 0.62, 0.30, 1), text_color=(0.95, 0.95, 0.95, 1),
        )
        assert dest.exists(), "generate() deveria ter criado o arquivo"
        with Image.open(dest) as img:
            size = img.size
        assert size == (share_card.SIZE, share_card.SIZE), "imagem deveria ser quadrada no tamanho SIZE"

        # sem avatar (arquivo não existe) não deveria quebrar — só não desenha o mascote
        dest2 = Path(tmp) / "sem_avatar.png"
        share_card.generate(
            dest2, streak_days=0, streak_word="dias", level_text="Nível 1 · 0 Pontos no Mês",
            avatar_path="", bg_color=(0.071, 0.071, 0.071, 1),
            accent_color=(0.53, 0.62, 0.30, 1), text_color=(0.95, 0.95, 0.95, 1),
        )
        assert dest2.exists()

        print("OK — todos os checks passaram")


if __name__ == "__main__":
    run()
