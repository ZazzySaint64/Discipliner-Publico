"""Gera assets/presplash.json a partir de assets/icon.png — roda de novo
sempre que o ícone mudar (python scripts/gen_presplash.py).

Splash nativo do Android (buildozer.spec: android.presplash_lottie) não
aceita nenhum controle de fade quando é só uma imagem estática — por isso
essa animação é um Lottie (formato de animação em JSON) montado à mão:
fundo sólido (mesma cor do android.presplash_color) + o ícone com 3 fases
de opacidade (fade in, segura, fade out), nos MESMOS tempos da vinheta em
Kivy (main.py: DailyQuestApp._play_splash) — os dois splashes ficam
visualmente contínuos em vez do corte seco de antes.
"""
import base64
import json
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
ICON_PATH = APP_DIR / "assets" / "icon.png"
OUT_PATH = APP_DIR / "assets" / "presplash.json"

W, H = 1080, 1920  # canvas no formato retrato comum (celular) — evita esticar/cortar estranho
ICON = 420          # ~39% da largura, mesma proporção do dp(160) da tela splash do Kivy (janela de referência 400dp)
FR = 30              # frames por segundo
FADE_IN_END = 10    # 0.33s  (Kivy: Animation(opacity=1, duration=0.35))
HOLD_END = 24        # +0.47s (Kivy: Animation(duration=0.45))
OUT_END = 35         # +0.37s (Kivy: Animation(opacity=0, duration=0.35)) — total ~1.15s, igual ao _play_splash


def build():
    b64 = base64.b64encode(ICON_PATH.read_bytes()).decode("ascii")
    return {
        "v": "5.9.6", "fr": FR, "ip": 0, "op": OUT_END, "w": W, "h": H, "nm": "presplash",
        "ddd": 0,
        "assets": [
            {"id": "icon", "w": 512, "h": 512, "u": "", "p": f"data:image/png;base64,{b64}", "e": 1},
        ],
        "layers": [
            # fundo sólido — mesma cor do android.presplash_color / app.bg_app escuro
            # (#121212). p e a IGUAIS (os dois em 0,0): um retângulo sólido já
            # desenha da própria origem local (0,0) até (sw,sh) = a tela inteira —
            # bastava não mover ele. Antes "p" jogava o retângulo pro centro da
            # tela SEM mover a âncora junto, então só um pedaço (canto inferior
            # direito) ficava dentro da área visível — o resto "sumia" pra fora,
            # dando a impressão de imagem cortada.
            {
                "ddd": 0, "ind": 1, "ty": 1, "nm": "bg", "sr": 1,
                "ks": {
                    "o": {"a": 0, "k": 100},
                    "p": {"a": 0, "k": [0, 0, 0]},
                    "a": {"a": 0, "k": [0, 0, 0]},
                    "s": {"a": 0, "k": [100, 100, 100]},
                    "r": {"a": 0, "k": 0},
                },
                "sw": W, "sh": H, "sc": "#121212",
                "ip": 0, "op": OUT_END, "st": 0, "bm": 0,
            },
            # ícone — fade in, segura, fade out (mesmas 3 fases da vinheta do Kivy)
            {
                "ddd": 0, "ind": 2, "ty": 2, "nm": "icon", "refId": "icon", "sr": 1,
                "ks": {
                    "o": {
                        "a": 1,
                        "k": [
                            {"t": 0, "s": [0], "i": {"x": [0.42], "y": [1]}, "o": {"x": [0.58], "y": [0]}},
                            {"t": FADE_IN_END, "s": [100], "i": {"x": [0.42], "y": [1]}, "o": {"x": [0.58], "y": [0]}},
                            {"t": HOLD_END, "s": [100], "i": {"x": [0.42], "y": [1]}, "o": {"x": [0.58], "y": [0]}},
                            {"t": OUT_END, "s": [0]},
                        ],
                    },
                    "p": {"a": 0, "k": [W / 2, H / 2, 0]},
                    "a": {"a": 0, "k": [256, 256, 0]},
                    "s": {"a": 0, "k": [ICON / 512 * 100, ICON / 512 * 100, 100]},
                    "r": {"a": 0, "k": 0},
                },
                "ip": 0, "op": OUT_END, "st": 0, "bm": 0,
            },
        ],
    }


if __name__ == "__main__":
    OUT_PATH.write_text(json.dumps(build()), encoding="utf-8")
    print(f"OK — {OUT_PATH} gerado ({OUT_PATH.stat().st_size} bytes)")
