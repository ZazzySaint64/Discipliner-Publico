"""Self-check: python test_i18n.py — garante que nenhum idioma ficou com chave faltando."""
import i18n


def run():
    langs = list(i18n.LANGUAGES.keys())
    assert len(langs) >= 2, "esperava pelo menos 2 idiomas"
    assert i18n.DEFAULT_LANGUAGE in langs

    # TRANSLATIONS: todo idioma tem exatamente o mesmo conjunto de chaves do default
    chaves_base = set(i18n.TRANSLATIONS[i18n.DEFAULT_LANGUAGE].keys())
    for lang in langs:
        assert lang in i18n.TRANSLATIONS, f"idioma '{lang}' não tem tabela de tradução"
        chaves = set(i18n.TRANSLATIONS[lang].keys())
        faltando = chaves_base - chaves
        sobrando = chaves - chaves_base
        assert not faltando, f"'{lang}' não tem: {faltando}"
        assert not sobrando, f"'{lang}' tem chave a mais que não existe no padrão: {sobrando}"
        for chave, valor in i18n.TRANSLATIONS[lang].items():
            assert valor.strip(), f"'{lang}.{chave}' está vazia"

    # WEEKDAYS/MONTHS/PERIODICITY_LABELS/DIFFICULTY_LABELS: mesma cobertura de idiomas
    for tabela, nome in [
        (i18n.WEEKDAYS, "WEEKDAYS"), (i18n.MONTHS, "MONTHS"),
        (i18n.PERIODICITY_LABELS, "PERIODICITY_LABELS"), (i18n.DIFFICULTY_LABELS, "DIFFICULTY_LABELS"),
    ]:
        for lang in langs:
            assert lang in tabela, f"{nome} não cobre '{lang}'"
    for lang in langs:
        assert len(i18n.WEEKDAYS[lang]) == 7, f"WEEKDAYS['{lang}'] precisa ter 7 dias"
        assert len(i18n.MONTHS[lang]) == 12, f"MONTHS['{lang}'] precisa ter 12 meses"
        assert set(i18n.PERIODICITY_LABELS[lang].keys()) == {"diaria", "semanal", "mensal"}
        assert set(i18n.DIFFICULTY_LABELS[lang].keys()) == {"facil", "media", "dificil"}

    # lookups básicos
    assert i18n.t("btn_cancel", "en") == "Cancel"
    assert i18n.t("chave_que_nao_existe", "en") == "chave_que_nao_existe", "fallback: devolve a própria chave"
    assert i18n.t("btn_cancel", "idioma_invalido") == i18n.t("btn_cancel", i18n.DEFAULT_LANGUAGE)

    assert i18n.periodicity_label("diaria", "en") == "Daily"
    assert i18n.periodicity_key("Daily", "en") == "diaria"
    assert i18n.periodicity_key("Não Existe", "en") is None

    assert i18n.difficulty_label("dificil", "fr") == "Difficile"
    assert i18n.difficulty_key("Difficile", "fr") == "dificil"

    print("OK — todos os checks passaram")


if __name__ == "__main__":
    run()
