"""Self-check da barra de navegação nova: python test_navbar.py

Cobre o que a barra inferior redesenhada precisa garantir (ver
docs/tipografia-e-navegacao.md):
- NavIcon aponta pro PNG certo de cada kind (assets/nav/), com fallback
- NavTab expõe kind/label/active e monta NavIcon + Label
- a árvore real do app tem exatamente as 5 abas certas
"""
import os
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")


def run_navicon():
    """NavIcon é um Image que troca de `source` conforme o `kind`. Cada kind
    real tem que apontar pra um arquivo que existe; kind desconhecido cai no
    'missions' em vez de ficar sem imagem."""
    from widgets import NavIcon

    for kind in ("missions", "history", "chart", "badges", "settings"):
        ic = NavIcon(kind=kind, size=(48, 48), pos=(0, 0))
        assert ic.source.endswith(f"nav_{kind}.png"), f"{kind}: source {ic.source!r}"
        assert Path(ic.source).is_file(), f"{kind}: arquivo não existe: {ic.source}"

    # kind desconhecido: fallback pro 'missions', não fica sem imagem
    ic = NavIcon(kind="???", size=(48, 48))
    assert ic.source.endswith("nav_missions.png"), ic.source

    # tint pela cor da aba: Image.color existe e aceita a troca sem erro
    ic.color = [0.2, 0.8, 0.4, 1]

    # NÃO pode consumir toque: senão tocar no ícone (a maior parte da aba)
    # não trocava de tela. Quem trata o toque é o NavTab.
    from kivy.uix.behaviors import ButtonBehavior
    assert not isinstance(ic, ButtonBehavior), "NavIcon virou ButtonBehavior de novo — vai engolir o toque da aba"

    print("OK — NavIcon: source certo por kind, fallback, tint, não engole toque")


def run_navtab():
    from widgets import NavTab

    t = NavTab()
    assert t.kind == "missions" and t.label == "" and t.active is False, "defaults do NavTab mudaram"
    t.active = True
    assert t.active is True
    print("OK — NavTab: propriedades e default")


def run_arvore():
    """A barra montada no app de verdade tem as 4 abas, cada uma com o ícone
    e o rótulo (regra <NavTab> do ui.kv)."""
    import main

    app = main.DailyQuestApp()
    app.build()

    def walk(w):
        yield w
        for c in w.children:
            yield from walk(c)

    sm = app.root_widget.ids["screen_manager"]
    bar = app.root_widget.ids["tut_nav_bar"]
    tabs = [c for c in bar.children if type(c).__name__ == "NavTab"]
    assert len(tabs) == 5, f"esperado 5 NavTab na barra, achei {len(tabs)}"
    assert {t.kind for t in tabs} == {"missions", "history", "chart", "badges", "settings"}

    telas = {s.name for s in sm.screens}
    for t in tabs:
        assert t.kind in telas, f"aba '{t.kind}' não casa com nenhuma tela do ScreenManager"
        filhos = {type(c).__name__ for c in t.children}
        assert "NavIcon" in filhos and "Label" in filhos, f"{t.kind}: montou {filhos}"

    print("OK — barra do app: 5 abas, cada uma com NavIcon + Label")


if __name__ == "__main__":
    run_navicon()
    run_navtab()
    run_arvore()
    print("todos os checks da barra passaram")
