"""Focum, o mascote — poses/avatares desbloqueáveis por conquista.
As imagens em si vivem em assets/focum/ (ver README lá) e não são obrigatórias:
se o arquivo não existir ainda, a UI simplesmente não mostra aquele estado."""
from pathlib import Path

ASSETS_DIR = Path(__file__).parent / "assets" / "focum"

# id -> (arquivo, id da conquista necessária pra desbloquear; None = sempre liberado)
AVATARS = [
    {"id": "idle", "file": "focum_idle.png", "requires": None},
    {"id": "thumbsup", "file": "focum_thumbsup.png", "requires": "streak_7"},
    {"id": "writing", "file": "focum_writing.png", "requires": "missions_10"},
    {"id": "meditating", "file": "focum_meditating.png", "requires": "level_5"},
    {"id": "sleeping", "file": "focum_sleeping.png", "requires": "streak_30"},
    {"id": "walking", "file": "focum_walking.png", "requires": "streak_14"},
    {"id": "celebrating", "file": "focum_celebrating.png", "requires": "streak_100"},
    {"id": "studying", "file": "focum_studying.png", "requires": "missions_100"},
    {"id": "star", "file": "focum_star.png", "requires": "level_15"},
    # pose exclusiva de quem comprou o Premium — sem arte ainda (ver README);
    # _build_avatar_thumbs (main.py) pula entradas sem arquivo, então isso não
    # aparece como um quadrado em branco no seletor até o arquivo existir
    {"id": "supporter", "file": "focum_supporter.png", "requires": "supporter"},
]

SLEEPING_FILE = "focum_sleeping.png"  # usado também na tela de histórico vazio


def asset_path(filename):
    path = ASSETS_DIR / filename
    return str(path) if path.exists() else ""


def reward_preview_path(badge_id):
    """Caminho da pose que essa conquista libera, ou "" se ela não libera
    nenhuma (a maioria dos emblemas hoje é só o emblema em si, sem pose)."""
    entry = next((a for a in AVATARS if a["requires"] == badge_id), None)
    return asset_path(entry["file"]) if entry else ""


# molduras decorativas ao redor do avatar — arte de verdade agora (assets/
# frame_<id>.png: PNG com centro E fundo transparentes, só o anel ornamentado
# fica opaco), com a cor sólida antiga (`color`) mantida como fallback pro
# seletor pequeno (FrameThumb, ver ui.kv) e pra quem checa só a cor (ver
# reward_frame_color, testado em test_mascot.py). Moldura e ícone do app usam
# a MESMA cor/tier e o MESMO critério (igual às poses acima) — "requires" é
# uma LISTA de emblemas, qualquer um já desbloqueia (ver frame_status), pra
# caber o caminho original (sequência/nível) e o novo de degrau de
# multiplicador de sequência lado a lado.
FRAMES = [
    {"id": "none", "file": None, "color": None, "requires": [], "scale": 1.0},
    # "scale" (ver frame_scale/App.current_frame_scale): tamanho extra pra
    # cobrir um recorte com margem transparente maior que o normal, crescendo
    # centralizado. Nenhuma moldura precisa hoje (o halo branco que parecia
    # "buraco grande demais" era vazamento de cor sob a transparência do PNG,
    # já corrigido nos próprios arquivos — não é mais um problema de tamanho).
    {"id": "bronze", "file": "frame_bronze.png", "color": (0.80, 0.50, 0.20, 1), "requires": ["streak_7", "streak_multiplier_125"], "scale": 1.0},
    {"id": "prata", "file": "frame_prata.png", "color": (0.75, 0.75, 0.78, 1), "requires": ["streak_30", "streak_multiplier_150"], "scale": 1.0},
    {"id": "ouro", "file": "frame_ouro.png", "color": (0.90, 0.75, 0.20, 1), "requires": ["level_10", "streak_multiplier_175"], "scale": 1.0},
    {"id": "diamante", "file": "frame_diamante.png", "color": (0.55, 0.85, 0.95, 1), "requires": ["streak_100", "streak_multiplier_200"], "scale": 1.0},
]

# arte das molduras vive direto em assets/ (não em assets/focum/, que é só do
# Focum) — ver scripts/ da sessão que cortou as 4 de assets/<uuid>.jpg original
FRAMES_DIR = Path(__file__).parent / "assets"


def frame_status(unlocked_badge_ids):
    """Lista de {id, color, unlocked} — mesmo formato de avatar_status."""
    result = []
    for f in FRAMES:
        needed = f["requires"]
        unlocked = not needed or any(r in unlocked_badge_ids for r in needed)
        result.append({"id": f["id"], "color": f["color"], "unlocked": unlocked})
    return result


def frame_color(frame_id):
    """None se "none" ou id desconhecido — quem desenha já trata como "sem moldura"."""
    entry = next((f for f in FRAMES if f["id"] == frame_id), None)
    return entry["color"] if entry else None


def frame_path(frame_id):
    """Caminho do PNG da moldura, ou "" se "none"/id desconhecido/arquivo
    ainda não existe — mesma convenção de asset_path (poses do Focum)."""
    entry = next((f for f in FRAMES if f["id"] == frame_id), None)
    if not entry or not entry["file"]:
        return ""
    path = FRAMES_DIR / entry["file"]
    return str(path) if path.exists() else ""


def frame_scale(frame_id):
    """1.0 (tamanho normal) se id desconhecido — quem desenha multiplica o
    tamanho da moldura por isto, centralizado (ver FRAMES > scale)."""
    entry = next((f for f in FRAMES if f["id"] == frame_id), None)
    return entry["scale"] if entry else 1.0


def reward_frame_color(badge_id):
    """Cor da moldura que esse emblema libera, ou None. Espelha
    reward_preview_path (que é pra pose do Focum), mas pro caminho das
    molduras — emblemas streak_multiplier_* não têm pose, a recompensa
    deles é a moldura (ver FRAMES > requires)."""
    entry = next((f for f in FRAMES if badge_id in f["requires"]), None)
    return entry["color"] if entry else None


def avatar_status(unlocked_badge_ids):
    """Lista de {id, file, path, unlocked} — path é '' se o arquivo ainda não existe."""
    result = []
    for a in AVATARS:
        unlocked = a["requires"] is None or a["requires"] in unlocked_badge_ids
        result.append({
            "id": a["id"],
            "file": a["file"],
            "path": asset_path(a["file"]),
            "unlocked": unlocked,
        })
    return result
