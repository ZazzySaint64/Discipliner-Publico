# ponytail: bug do CPython (github.com/python/cpython/issues/114875) — o
# configure do módulo grp só testa getgrgid, mas grpmodule.c também chama
# setgrent/getgrent/endgrent, que o bionic (libc do Android) não tem. Isso
# vira "error: implicit declaration" e derruba o build da recipe python3.
# O app não usa grupos Unix, então forçamos o configure a pular o módulo
# grp inteiro, herdando tudo mais da recipe original do python-for-android.
# Ativado via `p4a.local_recipes = p4a-recipes` no buildozer.spec.
# Remover se/quando o p4a corrigir isso na própria recipe upstream.
#
# get_recipe_dir() sobrescrito de propósito: por padrão, ter uma recipe em
# local_recipes faz o p4a resolver TODOS os caminhos relativos da recipe
# (inclusive os .patch/.diff que ela aplica) a partir dessa pasta local —
# e ela não tem os patches originais (reproducible-buildinfo.diff etc.),
# só este __init__.py. Sobrescrevendo get_recipe_dir pra sempre apontar pra
# pasta original da recipe, os patches continuam resolvendo lá; só o
# configure_args (definido aqui) é customizado.
from os.path import join
from pythonforandroid.recipes.python3 import Python3Recipe as _Python3Recipe


class Python3Recipe(_Python3Recipe):
    configure_args = _Python3Recipe.configure_args + [
        "ac_cv_func_getgrgid=no",
        "ac_cv_func_setgrent=no",
        "ac_cv_func_getgrent=no",
        "ac_cv_func_endgrent=no",
    ]

    def get_recipe_dir(self):
        return join(self.ctx.root_dir, "recipes", self.name)


recipe = Python3Recipe()
