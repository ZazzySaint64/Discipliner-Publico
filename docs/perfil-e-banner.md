# Tela de perfil + banner de fundo

## Banner de fundo do cabeçalho

Banner estilo Discord: cobre a faixa rente à foto de perfil. O cabeçalho fica
no root, acima do `ScreenManager`, então **o banner aparece em todas as telas**.

- `banners.py` — `BANNERS` (5 presets + `none`), `PATTERNS` (estilos do
  personalizado), `resolve(id, hue, sat, pattern) -> (pattern, cor)`.
- `widgets.BannerArt` — desenha o padrão no canvas (nada de imagem: assim o
  personalizado é o mesmo desenho com outra cor). Recorta no próprio retângulo
  (stencil) e joga um véu de `bg_app` a 0.28 por cima pra o texto do cabeçalho
  continuar legível. `pattern == "none"` / cor transparente = não desenha nada
  (cabeçalho igual a antes).
- Cabeçalho no `ui.kv`: virou `FloatLayout` com `BannerArt` atrás + o
  `BoxLayout` do avatar/nome por cima (`pos`/`size` presos ao pai). Antes era só
  o `BoxLayout`.
- App (`main.py`): `profile_banner` (id escolhido) + `custom_banner_hue/sat/pattern`.
  `banner_pattern`/`banner_color` são o resultado já resolvido que o kv desenha —
  recalculados em `_apply_banner()` (chamado no `_load_prefs` e nos setters).

### Presets (grátis)
`ocean` (degradê azul), `sunset` (degradê quente), `grove` (listras verdes),
`violet` (bolinhas roxas), `slate` (grade cinza).

### Personalizado (Premium)
Roda HSV (`AccentColorWheel`, reaproveitada) → `pick_custom_banner(hue, sat)`
(grava debounced, igual `pick_custom_accent`) + 6 chips de estilo →
`set_custom_banner_pattern`. Brilho fixo em 0.5 pra ficar legível (mesma ideia
do `custom_accent_variants`).

## Tela "profile"

Abre ao tocar no avatar do cabeçalho (`open_profile_screen` →
`switch_screen("profile")`) — antes era o popup `AvatarPickerPopup`, que foi
**removido**. Sem aba na barra: volta pelo `<` do topo ou pelo botão voltar do
Android (`_screen_history`).

Seções: **Banner** (thumbs `BannerThumb` + painel do personalizado), **Foto de
perfil** (enviar foto Premium + grade de poses do Focum), **Moldura**, **Ícone
do app**. As 4 listas são montadas por `_build_profile_pickers()` ao entrar na
tela (dinâmicas: desbloqueios + traduções). `prof_avatar_list` reaproveita
`_build_avatar_thumbs`; molduras/ícones, `_build_frame_thumbs`.

Migração de dados: `database.py` adiciona `profile_banner`,
`custom_banner_hue/sat`, `custom_banner_pattern` via `ALTER TABLE ADD COLUMN`
(mesmo padrão de `app_icon`).

Checks: `test_profile.py`.
