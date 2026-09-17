# O download.savannah.gnu.org, de onde a recipe original do python-for-android
# baixa o freetype, cai com frequência devolvendo 502/504 — e quando cai leva o
# build inteiro junto, porque o freetype é dependência do SDL2_ttf (ou seja, do
# Kivy). Aconteceu no run de 2026-09-04: as 3 tentativas do step de build
# morreram no mesmo download, ao longo de ~6 minutos de mirror fora do ar.
#
# Aqui só a URL muda: mesmo tarball, mesma versão, servido pelo SourceForge,
# que é ponto de distribuição oficial secundário do freetype (o projeto publica
# cada release nos dois). Todo o resto (configure_args, build_arch, ordem de
# dependências) é herdado da recipe original.
#
# A recipe original não tem patches nem usa get_recipe_dir(), então não precisa
# do contorno que a recipe local do python3 faz aqui do lado — ver o comentário
# em p4a-recipes/python3/__init__.py.
#
# Ativado via `p4a.local_recipes = p4a-recipes` no buildozer.spec.
# Dá pra remover quando/se o p4a passar a apontar pra um mirror estável.
from pythonforandroid.recipes.freetype import FreetypeRecipe as _FreetypeRecipe


class FreetypeRecipe(_FreetypeRecipe):
    url = "https://downloads.sourceforge.net/project/freetype/freetype2/{version}/freetype-{version}.tar.gz"  # noqa


recipe = FreetypeRecipe()
