# Sistema de tipografia + barra de navegação — Discipliner

Inspiração visual: app **Food To Save** (print de referência). O que foi
adotado de lá: títulos de seção **em CAIXA ALTA, bold, pequenos e discretos**;
barra inferior com **ícone de linha + rótulo embaixo**, cor de destaque só na
aba ativa, **sem pílula preenchida**; hierarquia clara entre valor grande /
rótulo / meta nos cards.

Não adotado: o laranja fixo (o app tem cor de destaque temável — `app.accent`);
o cabeçalho colorido de página inteira.

---

## 1. Escala tipográfica

Escala modular de razão **1.2 ("terça menor")** — passo pequeno, calmo, que
cabe em tela de celular sem "pular". Ancorada no corpo de texto em **14sp**.
Valores arredondados pro inteiro em `sp` (o Kivy já resolve densidade de tela).

| Token (`#:set` no `ui.kv`) | Tamanho | Peso | Fonte | Uso |
|---|---|---|---|---|
| `FS_DISPLAY` | 28sp | bold | `TITLE_FONT` (Trebuchet) | identidade "Discipliner" na splash. Marca, não texto. |
| `FS_TITLE`   | 22sp | bold | `TITLE_FONT` | nome no cabeçalho; título de tela quando houver |
| `FS_HEADING` | 17sp | bold | Candara | valor em destaque de card (`Nível 3`, `5 dias`), título de popup |
| `FS_SECTION` | 12sp | bold | Candara | cabeçalho de seção — **sempre em CAIXA ALTA** (ver §2) |
| `FS_BODY`    | 14sp | regular | Candara | texto padrão, nome de missão, corpo de popup |
| `FS_LABEL`   | 12sp | bold | Candara | rótulo de campo de formulário (`FieldLabel`) |
| `FS_CAPTION` | 11sp | regular | Candara | meta secundária: contador de XP, status de freeze, "X%" |
| `FS_NAV`     | 10sp | bold | Candara | rótulo das abas da barra inferior |

**Antes → depois:** 14 tamanhos avulsos (9,10,11,12,13,14,15,16,17,18,20,22,34sp)
colapsam em 8 tokens nomeados. `9sp` sai de cena (era ilegível no aparelho) —
vira `FS_CAPTION`. `13sp`/`15sp`/`18sp`/`20sp`/`34sp` mapeiam pro token vizinho.

Controles (`ClayButton`, `ClaySpinner`) mantêm o auto-encolhimento próprio
(`fit_font_size`, base `sp(15)`) — é lógica de caber-no-botão, não hierarquia de
leitura, então fica fora da escala de propósito.

---

## 2. Hierarquia

Três níveis, distintos por **tamanho + peso + cor** (nunca só um deles):

1. **Primário** — o número/estado que a pessoa abriu o app pra ver.
   `FS_HEADING` bold, `app.text_dark`. Ex.: streak, nível, progresso %.
2. **Rótulo de seção** — orienta, não compete. `FS_SECTION` bold **CAIXA ALTA**,
   `app.muted`. É o "SEUS LOCAIS FAVORITOS" da referência.
3. **Meta / apoio** — `FS_CAPTION` regular, `app.muted`. Ex.: `120/300 XP`,
   `2 freezes disponíveis`.

Contraste de peso faz o trabalho que **espaçamento entre letras faria** — o
Label do Kivy não tem `letter-spacing`. Por isso o rótulo de seção é **CAIXA
ALTA**: some com o problema de descida de letra e dá a textura "etiqueta" sem
precisar de tracking.

### `SectionLabel` (classe nova no `ui.kv`)

```kv
<SectionLabel@Label>:
    color: app.muted
    bold: True
    font_size: FS_SECTION
    size_hint_y: None
    height: dp(28)
    halign: "left"
    valign: "bottom"
    text_size: self.size
```

**Regra de uso:** o Kivy não transforma texto — **sempre passe a string já em
maiúscula**: `text: (app.t('progress_label')).upper()`. `HistorySectionLabel`
passa a ser só um apelido: `<HistorySectionLabel@SectionLabel>:`.

---

## 3. Responsivo

Alvo real: **um** intervalo de largura (celular retrato, ~360–430dp; janela
desktop travada em 400×760 no `build()`). Não há breakpoint de tablet/web.

- **Unidade `sp`**: já escala com a densidade e com a fonte do sistema. Nenhum
  ajuste manual por DPI.
- **Sem escala fluida** (nada de `font_size` calculado da largura da janela):
  numa faixa tão estreita, `sp` fixo é previsível e a escala 1.2 não aperta.
  Se algum dia existir layout de tablet, o único token que muda é `FS_BODY`
  (15sp) e os outros recalculam pela razão — troca de 8 linhas no topo do `kv`.
- **Quebra de texto**: todo Label de texto longo usa `text_size: self.width, None`
  + altura por `texture_size[1]` (padrão que o `FieldLabel` já segue). Rótulo de
  seção e caption têm altura fixa (`dp(28)` / `dp(16)`) porque são de 1 linha
  por contrato.

---

## 4. Espaçamento do texto

Grade base de **4dp** (o `ui.kv` já respira nisso: paddings dp(8)/dp(12)/dp(16),
spacing dp(10)).

| Relação | Valor | Onde |
|---|---|---|
| Rótulo de seção → conteúdo abaixo | dp(8) | `spacing` do BoxLayout da seção |
| Valor primário → meta (dentro do card) | dp(2)–dp(4) | par `FS_HEADING` + `FS_CAPTION` |
| Entre cards / blocos | dp(10)–dp(12) | `spacing` das colunas de card |
| Padding interno de card | dp(8) (card compacto) / dp(14) (card de conteúdo) | — |
| Barra inferior: ícone → rótulo | dp(2) | `spacing` do `NavTab` |
| Altura de linha (multi-linha) | ~1.3 | implícito: `texture_size[1]` do Kivy já dá isso |

Rótulo de seção: `valign: "bottom"` + `height: dp(28)` cria um respiro de ~dp(10)
**acima** do texto e cola ele no conteúdo que rotula — agrupamento por
proximidade sem linha divisória.

---

## 5. Alinhamento à grade

Sem baseline grid tipográfico de verdade (o Kivy não expõe baseline do Label).
Aproximação por **altura de linha múltipla de 4dp**:

| Token | Altura da linha reservada |
|---|---|
| `FS_HEADING` | dp(24) |
| `FS_SECTION` | dp(28) (inclui o respiro de cima) |
| `FS_BODY` / `FS_LABEL` | `max(dp(20), texture_size[1])` |
| `FS_CAPTION` | dp(16) |
| `NavTab` inteiro | dp(60) (dp(24) ícone + dp(2) + dp(14) rótulo + dp(20) padding/folga) |

Tudo cai na grade de 4dp → os blocos empilham sem meio-pixel e o ritmo
vertical fecha com os `spacing` dp(8)/dp(12).

---

## 6. Barra de navegação inferior

### Antes
4× `ClayButton` pill: fundo `app.accent` quando ativo, `app.bg_card` quando não.
Texto only. Ocupa a barra toda de cor no estado ativo.

### Depois (padrão da referência)
5× `NavTab` = **ícone (PNG de silhueta em `assets/nav/`)** + rótulo `FS_NAV` embaixo.
- Ativo: ícone e rótulo em `app.accent`, rótulo **bold**.
- Inativo: ícone e rótulo em `app.muted`, rótulo regular.
- **Sem fundo, sem borda, sem pílula.** A barra mantém só a hairline no topo
  (`rgba 0,0,0,0.08`) separando do conteúdo.
- Altura da barra: dp(60). `NavTab` é `vertical`, `spacing dp(2)`.
- Abas: `missions`, `history`, `chart`, `badges`, `settings`. Ajustes é **só**
  aqui agora — a engrenagem do cabeçalho foi removida; o passo `settings` do
  tutorial guiado (`TUTORIAL_STEPS`) destaca a aba `tut_settings_tab`.

### Ícones (`NavIcon` = `Image`, PNG branco em `assets/nav/`)
Silhueta branca; a barra pinta com `Image.color` (`app.accent` na aba ativa,
`app.muted` nas outras). Antes eram desenhados no canvas; viraram PNG quando
passou a existir a arte pronta. Cortados da folha
`assets/focum/raw/nav_icons_sheet.jpg` por `scripts/gen_nav_icons.py`.

| `kind` | Arquivo | Desenho |
|---|---|---|
| `missions` | `nav_missions.png` | quadrado arredondado + check |
| `history`  | `nav_history.png`  | relógio (aro + ponteiros) |
| `chart`    | `nav_chart.png`    | gráfico de barras |
| `badges`   | `nav_badges.png`   | estrela |
| `settings` | `nav_settings.png` | engrenagem |

`NavIcon` tem só `kind` (StringProperty); troca o `source` no bind de `kind`,
com fallback pra `missions` se o kind for desconhecido. **Não é
`ButtonBehavior`**: quem trata o toque é o `NavTab` que o contém — se o ícone
consumisse o touch, tocar nele (a maior parte da aba) não trocaria de tela.

---

## 7. Regras de uso (resumo)

- **Nunca** um `font_size` literal novo no `kv`. Use um token. Se nenhum serve,
  o problema é a hierarquia, não a escala.
- Rótulo de seção = `SectionLabel` + string **`.upper()`**. Nada de Label solto
  em bold pra fazer as vezes de cabeçalho.
- Valor primário de card sempre pareado com uma meta em `FS_CAPTION` — número
  grande sozinho não diz o que é.
- Ícone em UI = canvas (`NavIcon`) ou PNG em `assets/`. **Jamais** caractere de
  ícone/emoji num Label — vira quadradinho no Android.
- Cor de texto vem sempre de `app.text_dark` / `app.muted` / `app.text_light` /
  `app.accent` (Properties temáveis), nunca RGBA fixo.
