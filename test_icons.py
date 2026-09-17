"""Self-check dos ícones do app: python test_icons.py

Nada disso dá pra ver sem instalar o APK num celular, e um recurso faltando só
aparece como erro do aapt no meio do build (ou, pior, como ícone em branco no
launcher). Aqui confere o que dá pra conferir sem Android: que todo arquivo
declarado existe e que toda referência @drawable/... aponta pra algo que
realmente entra no APK. Não abre janela."""
import configparser
import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent


def _add_resources():
    """{caminho_origem: destino_em_res} do android.add_resources."""
    cp = configparser.ConfigParser()
    cp.read(APP_DIR / "buildozer.spec", encoding="utf-8")
    bruto = cp.get("app", "android.add_resources")
    pares = {}
    for item in bruto.split(","):
        item = item.strip()
        if not item:
            continue
        origem, destino = item.split(":")
        pares[origem.strip()] = destino.strip()
    return pares, cp


def run():
    recursos, cp = _add_resources()

    # 1) todo arquivo declarado existe
    faltando = [o for o in recursos if not (APP_DIR / o).is_file()]
    assert not faltando, f"android.add_resources aponta pra arquivo inexistente: {faltando}"

    # 2) o ícone PADRÃO tem que ser adaptativo também.
    #
    # Esta checagem existe porque a primeira versão da correção passava no teste
    # e mesmo assim saía errada no APK: eu confiava nas chaves
    # icon.adaptive_icon_foreground/background do buildozer, e elas foram
    # IGNORADAS — o APK saiu com android:icon="@mipmap/icon" apontando pro PNG
    # puro e o launcher encolheu o ícone (verificado com aapt2 e em captura de
    # tela do emulador). Só os ícones de tier ficaram certos, porque esses eu
    # já entregava por android.add_resources.
    #
    # Então o que o teste cobra agora é o RESULTADO no APK, não a intenção:
    # o XML adaptativo tem que estar declarado como recurso, com o mesmo nome
    # ("icon") do PNG, pro Android 8+ preferir ele.
    valor = cp.get("app", "icon.filename").replace("%(source.dir)s/", "")
    assert (APP_DIR / valor).is_file(), f"icon.filename aponta pra {valor}, que não existe"
    assert "mipmap-anydpi-v26/icon.xml" in recursos.values(), (
        "o ícone padrão não tem XML adaptativo declarado em android.add_resources — "
        "vai sofrer 'legacy icon treatment' e aparecer menor que o dos outros apps")
    assert "drawable/icon_fg.png" in recursos.values(), \
        "falta a camada de frente do ícone padrão"
    for chave in ("icon.adaptive_icon_foreground", "icon.adaptive_icon_background"):
        assert not cp.has_option("app", chave), (
            f"{chave} está de volta no buildozer.spec — ela NÃO funciona neste "
            "projeto (o buildozer ignora); o ícone padrão vai pelo add_resources")

    # 3) todo @drawable/X citado no manifest e nos XMLs adaptativos é fornecido
    nomes_no_apk = set()
    for destino in recursos.values():
        nomes_no_apk.add(Path(destino).stem)

    citacoes = []
    fontes = [APP_DIR / "android_manifest_extra.xml"]
    fontes += sorted((APP_DIR / "assets" / "icons_alt").glob("*_adaptive.xml"))
    for fonte in fontes:
        texto = fonte.read_text(encoding="utf-8")
        for nome in re.findall(r"@drawable/([A-Za-z0-9_]+)", texto):
            citacoes.append((fonte.name, nome))

    orfas = [f"{arq} -> @drawable/{n}" for arq, n in citacoes if n not in nomes_no_apk]
    assert not orfas, (
        "referência a drawable que NÃO entra no APK (aapt quebra ou ícone vem "
        f"em branco):\n  " + "\n  ".join(orfas))
    assert citacoes, "nenhum @drawable citado — o teste não estaria conferindo nada"

    # 4) cada alias tem PNG (Android 7-) e XML adaptativo (Android 8+) com o
    # mesmo nome de recurso, senão só metade dos aparelhos pega o ícone certo
    import importlib.util

    from PIL import Image

    # carrega pelo caminho pra não precisar transformar scripts/ em pacote
    # (um __init__.py ali entraria no APK junto com o resto dos .py)
    _spec = importlib.util.spec_from_file_location(
        "gen_alt_icons", APP_DIR / "scripts" / "gen_alt_icons.py")
    gen = importlib.util.module_from_spec(_spec)  # SAFE_RATIO é a fonte da verdade
    _spec.loader.exec_module(gen)

    tiers = sorted({Path(d).stem for d in recursos.values()
                    if d.startswith("drawable/ic_") and not d.endswith(("_fg.png", "_bg.png"))
                    and Path(d).stem != "ic_tier_bg"})
    assert tiers, "nenhum ícone de tier encontrado no add_resources"
    for tier in tiers:
        assert f"drawable-anydpi-v26/{tier}.xml" in recursos.values(), \
            f"{tier} não tem XML adaptativo — vai encolher no Android 8+"
        assert f"drawable/{tier}_fg.png" in recursos.values(), \
            f"{tier} não tem camada de frente"

    # 5) a arte da camada de frente cabe na zona segura da máscara adaptativa;
    # passar disso faz o launcher cortar as bordas do desenho
    limite = gen.SAFE_RATIO + 0.02  # folga do arredondamento do thumbnail
    for origem in recursos:
        if not origem.endswith("_fg.png"):
            continue
        img = Image.open(APP_DIR / origem).convert("RGBA")
        bbox = img.getchannel("A").getbbox()
        ocupa = max(bbox[2] - bbox[0], bbox[3] - bbox[1]) / img.width
        assert ocupa <= limite, \
            f"{origem}: arte ocupa {ocupa:.0%} do canvas, acima da zona segura ({gen.SAFE_RATIO:.0%}) — o launcher corta"

    print(f"OK — {len(recursos)} recursos declarados existem, "
          f"{len(tiers)} tiers com PNG + XML adaptativo, camadas dentro da zona segura")


if __name__ == "__main__":
    run()
