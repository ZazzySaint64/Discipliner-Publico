"""Gera assets/focum/focum_intro.gif — a animação do ícone que toca na tela
'splash' do Kivy (ver ui.kv > Screen name:"splash" e main._play_splash).

Fonte: assets/focum/raw/faça_um_vídeo_de_introdução_de.mp4 (10s, 1280x720,
o ícone do app animado: pisca, joinha, brilhos). Só usamos ~1.5s dele.

O GIF é PING-PONG (vai e volta): emenda sem pulo nenhum, então "começa igual
ao ícone e acaba igual" de graça, sem depender de o vídeo ser um loop perfeito.

Precisa do ffmpeg. Tenta o binário do pacote imageio-ffmpeg (pip) e, se não
tiver, o ffmpeg do PATH:  python scripts/gen_intro_gif.py
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
SRC = APP_DIR / "assets" / "focum" / "raw" / "faça_um_vídeo_de_introdução_de.mp4"
OUT = APP_DIR / "assets" / "focum" / "focum_intro.gif"

# Recorta EXATAMENTE o selo do ícone (w:h:x:y no frame 1280x720). Os limites
# saíram de varrer a transição de cor no frame: fundo verde-claro (~145,185,117)
# vira verde-escuro do selo (~50,93,53) em x=316 e x=942, y=46 e y=672. O crop
# antigo (680:680:300:20) sobrava uma faixa do fundo em volta.
CROP = "626:626:316:46"
START = 1.0               # segundo em que o trecho começa
DUR = 1.5                # duração do trecho (ping-pong dobra pra ~2.8s de loop)
FPS = 10
SIZE = 288
COLORS = 127            # 1 cor fica reservada pra transparência dos cantos

# Raio dos cantos arredondados do selo, em fração do lado. Cortar no retângulo
# ainda deixava 4 triângulos de fundo verde nos cantos; a máscara os torna
# transparentes, então o GIF assenta em qualquer bg_app (claro ou escuro).
RAIO = 0.22


def _ffmpeg():
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        exe = shutil.which("ffmpeg")
        if not exe:
            raise SystemExit("ffmpeg não encontrado — pip install imageio-ffmpeg")
        return exe


def _arredondar(frames):
    """Vaza os cantos de cada frame com o mesmo raio do selo."""
    from PIL import Image, ImageDraw

    lado = SIZE
    mascara = Image.new("L", (lado, lado), 0)
    ImageDraw.Draw(mascara).rounded_rectangle(
        (0, 0, lado - 1, lado - 1), radius=int(lado * RAIO), fill=255)
    for f in frames:
        img = Image.open(f).convert("RGBA")
        img.putalpha(mascara)
        img.save(f)


def main():
    ff = _ffmpeg()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        # 1) trecho -> PNGs numerados
        subprocess.run([
            ff, "-hide_banner", "-loglevel", "error",
            "-ss", str(START), "-t", str(DUR), "-i", str(SRC),
            "-vf", f"crop={CROP},scale={SIZE}:{SIZE}:flags=lanczos,fps={FPS}",
            str(tmp / "f_%03d.png"),
        ], check=True)
        frames = sorted(tmp.glob("f_*.png"))
        if len(frames) < 3:
            raise SystemExit(f"só {len(frames)} frames extraídos — confira o vídeo")

        # 2) cantos arredondados -> transparentes
        _arredondar(frames)

        # 3) ping-pong: 1..N depois N-1..2 (sem repetir os extremos)
        order = frames + frames[-2:0:-1]
        for i, src in enumerate(order):
            shutil.copy(src, tmp / f"q_{i:03d}.png")

        # 4) PNGs -> GIF com paleta dedicada (nitidez decente num arquivo pequeno).
        # reserve_transparent + alpha_threshold preservam os cantos vazados; sem
        # eles o ffmpeg achata o alfa em preto e volta o quadrado.
        subprocess.run([
            ff, "-hide_banner", "-loglevel", "error", "-framerate", str(FPS),
            "-i", str(tmp / "q_%03d.png"),
            "-vf", (f"split[a][b];[a]palettegen=max_colors={COLORS}:stats_mode=full:"
                    f"reserve_transparent=1[p];"
                    f"[b][p]paletteuse=dither=sierra2_4a:alpha_threshold=128"),
            "-loop", "0", "-y", str(OUT),
        ], check=True)
    kb = OUT.stat().st_size / 1024
    print(f"{OUT.name}: {len(order)} frames, {kb:.0f} KB")


if __name__ == "__main__":
    main()
