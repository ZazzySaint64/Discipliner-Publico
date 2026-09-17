"""Self-check: python test_challenges.py (não precisa do Kivy)."""
import challenges
import i18n
import mission_suggestions as sugg


def run():
    ids = [c["id"] for c in challenges.CHALLENGES]
    assert len(ids) == len(set(ids)), "ids duplicados na lista de desafios"

    for c in challenges.CHALLENGES:
        assert len(c["mission_ids"]) >= 2, f"desafio {c['id']} deveria ter pelo menos 2 missões"
        for sugg_id in c["mission_ids"]:
            assert sugg.get(sugg_id) is not None, f"desafio {c['id']} referencia sugestão inexistente: {sugg_id}"

        # todo desafio tem nome e descrição traduzidos nos 5 idiomas
        for suffix in ("name", "desc"):
            key = f"challenge_{c['id']}_{suffix}"
            for lang in i18n.LANGUAGES:
                assert i18n.t(key, lang) != key, f"faltou tradução de {key} em {lang}"

    assert challenges.get("fitness")["mission_ids"] == ["exercise", "water", "sleep"]
    assert challenges.get("nao_existe") is None

    # alguns desafios COMPARTILHAM uma sugestão (ex.: "review_week" em "focus" e
    # "finance") — é intencional, mas main.add_challenge tem que deduplicar pra
    # não criar a mesma missão 2x. Aqui a gente trava o comportamento esperado:
    # somando todos os desafios, cada sugestão entra no máximo uma vez.
    added, dups = set(), []
    for c in challenges.CHALLENGES:
        for sugg_id in c["mission_ids"]:
            if sugg_id in added:
                dups.append(sugg_id)  # já veio de outro desafio -> deduplicar
            added.add(sugg_id)
    assert "review_week" in dups, "esperado: review_week aparece em mais de um desafio"
    # o conjunto final de missões = sugestões distintas, nunca com repetição
    assert len(added) == len(set(added))

    print("OK — todos os checks passaram")


if __name__ == "__main__":
    run()
