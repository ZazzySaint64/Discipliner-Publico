"""Self-check: python test_mission_suggestions.py (não precisa do Kivy)."""
import i18n
import missions
import mission_suggestions as sugg


def run():
    ids = [s["id"] for s in sugg.SUGGESTIONS]
    assert len(ids) == len(set(ids)), "ids duplicados na lista de sugestões"

    for s in sugg.SUGGESTIONS:
        # toda sugestão tem periodicidade/dificuldade válidas (pontos calculáveis)
        assert missions.points_for(s["periodicity"], s["difficulty"]) > 0, s
        # toda sugestão tem nome traduzido nos 5 idiomas
        key = f"sugg_{s['id']}_name"
        for lang in i18n.LANGUAGES:
            assert i18n.t(key, lang) != key, f"faltou tradução de {key} em {lang}"

    assert sugg.get("water")["periodicity"] == "diaria"
    assert sugg.get("nao_existe") is None

    print("OK — todos os checks passaram")


if __name__ == "__main__":
    run()
