"""Self-check: python test_mascot.py (não precisa do Kivy)."""
import mascot


def run():
    # idle é sempre liberado, o resto depende da conquista
    status = {a["id"]: a["unlocked"] for a in mascot.avatar_status(set())}
    assert status["idle"] is True
    assert status["thumbsup"] is False
    assert status["sleeping"] is False

    status = {a["id"]: a["unlocked"] for a in mascot.avatar_status({"streak_7", "level_5"})}
    assert status["thumbsup"] is True
    assert status["meditating"] is True
    assert status["writing"] is False, "missions_10 não foi desbloqueada"

    # path vem vazio pra arquivo que não existe (não deve quebrar mesmo sem os PNGs)
    for a in mascot.avatar_status(set()):
        assert a["path"] == "" or a["path"].endswith(a["file"])

    # prévia de recompensa: emblema que libera pose retorna o caminho dela;
    # emblema sem pose associada (ex.: level_10) retorna "" sem quebrar
    assert mascot.reward_preview_path("level_5").endswith("focum_meditating.png")
    assert mascot.reward_preview_path("streak_30").endswith("focum_sleeping.png")
    assert mascot.reward_preview_path("level_10") == ""
    assert mascot.reward_preview_path("nao_existe") == ""

    # moldura/ícone do app: caminho original (sequência/nível) OU o novo
    # (degrau de multiplicador de sequência, ver achievements.py > streak_multiplier_*)
    frames = {f["id"]: f["unlocked"] for f in mascot.frame_status(set())}
    assert frames["none"] is True, "'none' sempre liberado"
    assert frames["bronze"] is False

    via_streak = {f["id"]: f["unlocked"] for f in mascot.frame_status({"streak_7"})}
    assert via_streak["bronze"] is True, "caminho original continua funcionando"

    via_multiplier = {f["id"]: f["unlocked"] for f in mascot.frame_status({"streak_multiplier_125"})}
    assert via_multiplier["bronze"] is True, "novo caminho (multiplicador) também desbloqueia"
    assert via_multiplier["prata"] is False, "só o degrau certo desbloqueia o tier certo"

    # prévia de recompensa do emblema quando ela é uma moldura (multiplicador
    # de sequência não tem pose): retorna a cor do tier; emblema sem moldura
    # associada retorna None
    assert mascot.reward_frame_color("streak_multiplier_125") == (0.80, 0.50, 0.20, 1)
    assert mascot.reward_frame_color("streak_multiplier_200") == (0.55, 0.85, 0.95, 1)
    assert mascot.reward_frame_color("first_mission") is None
    assert mascot.reward_frame_color("none") is None

    print("OK — todos os checks passaram")


if __name__ == "__main__":
    run()
