"""Self-check: python test_theme.py — testa custom_accent_variants (main.py),
usado pela cor de destaque personalizada do Premium (ver README > Monetização).
Só importa Kivy pra achar a classe, não chega a abrir janela nenhuma."""
from main import custom_accent_variants


def run():
    theme = custom_accent_variants(140, 55)  # matiz verde, mesma faixa do "floresta"
    for mode in ("light", "dark"):
        for key in ("accent", "accent_soft"):
            r, g, b, a = theme[mode][key]
            assert 0.0 <= r <= 1.0 and 0.0 <= g <= 1.0 and 0.0 <= b <= 1.0, theme[mode][key]
            assert a == 1

    # accent do escuro é mais claro/pop que o do claro — mesma relação dos temas fixos
    light_accent = sum(theme["light"]["accent"][:3])
    dark_accent = sum(theme["dark"]["accent"][:3])
    assert dark_accent >= light_accent, "accent do modo escuro deveria ser tão claro quanto ou mais que o do claro"

    # accent_soft é sempre bem mais suave (mais claro) que o accent da própria variante
    assert sum(theme["light"]["accent_soft"][:3]) > sum(theme["light"]["accent"][:3])

    # matiz dá a volta (360 == 0) sem estourar índice/erro
    wrap = custom_accent_variants(360, 55)
    zero = custom_accent_variants(0, 55)
    assert wrap["light"]["accent"] == zero["light"]["accent"]

    # saturação 0 (sem cor) não quebra — vira tons de cinza
    grey = custom_accent_variants(140, 0)
    r, g, b, _ = grey["light"]["accent"]
    assert abs(r - g) < 1e-6 and abs(g - b) < 1e-6, "saturação 0 deveria dar cinza puro (r==g==b)"

    print("OK — todos os checks passaram")


def run_glyphs():
    """Nenhum texto desenhado pelo Kivy pode usar seta/forma geométrica/emoji.

    O Kivy desenha com UMA fonte só e não faz fallback pro sistema: de U+2190
    pra cima (setas, formas, dingbats, emoji) sai um quadradinho vazio no
    aparelho. Foi o que aconteceu com o "▾"/"▸" do cabeçalho recolhível das
    Recompensas de Nível — no Windows passava despercebido porque a Candara
    tem esses glifos, mas a Roboto do Android não.

    Exceção: as reminder_msg_* levam emoji de propósito. Elas vão pra
    notificação de SISTEMA, desenhada pelo Android; o popup dentro do app
    recebe a versão sem emoji (main._sem_emoji)."""
    from pathlib import Path

    import main

    problemas = []
    for nome in ("ui.kv", "screens_onboarding.kv", "i18n.py"):
        texto = Path(__file__).parent.joinpath(nome).read_text(encoding="utf-8")
        for n_linha, linha in enumerate(texto.splitlines(), 1):
            if "reminder_msg_" in linha:
                continue
            ruins = {c for c in linha if ord(c) >= main._GLIFO_MAX}
            if ruins:
                problemas.append(f"{nome}:{n_linha} {sorted(ruins)} -> {linha.strip()[:70]}")
    assert not problemas, (
        "glifo que a fonte do Kivy não desenha (vira quadradinho):\n  "
        + "\n  ".join(problemas)
    )

    # e o texto que chega no popup do app tem que sair limpo, sem espaço duplo
    assert main._sem_emoji("Não está esquecendo de nada? 👀") == "Não está esquecendo de nada?"
    assert main._sem_emoji("Falta pouco ✍️ pra riscar tudo.") == "Falta pouco pra riscar tudo."
    assert main._sem_emoji("sem emoji aqui") == "sem emoji aqui"

    print("OK — nenhum glifo fora do que a fonte do Kivy desenha")


def run_contraste():
    """Texto dos botões nunca some no fundo: com a cor personalizada dá pra
    escolher um destaque bem claro, e o texto branco ficava ilegível."""
    from widgets import texto_legivel

    branco, escuro = [1, 1, 1, 1], [0.10, 0.10, 0.10, 1]
    verde_claro = [0.62, 0.90, 0.60, 1]
    assert texto_legivel(verde_claro, branco) == escuro, "branco em verde-claro tinha que virar escuro"
    # cor que já contrasta fica como está (não achata o tema)
    verde_escuro = [0.20, 0.45, 0.20, 1]
    assert texto_legivel(verde_escuro, branco) == branco
    cinza_escuro = [0.16, 0.16, 0.16, 1]
    texto_claro = [0.95, 0.95, 0.95, 1]
    assert texto_legivel(cinza_escuro, texto_claro) == texto_claro
    # e o inverso: texto escuro num fundo escuro vira branco
    assert texto_legivel(cinza_escuro, escuro) == branco
    print("OK — texto dos botões troca pra escuro/branco quando some no fundo")


if __name__ == "__main__":
    run()
    run_glyphs()
    run_contraste()
