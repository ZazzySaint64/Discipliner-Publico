# Ciclo pessoal (escalas de trabalho rotativas) — design

## Problema

O app hoje só entende "semana" como o calendário padrão (segunda–domingo).
Missões diárias podem ser restritas a dias específicos da semana
(`missions.custom_days`), mas isso pressupõe um padrão que se repete
IGUAL toda semana. Quem trabalha em escala rotativa (12x36, 24x48, 6x1
com folga que anda, plantão) não tem esse padrão — o dia de folga muda a
cada ciclo, não é sempre a mesma terça-feira.

## Solução

Trocar a unidade de "semana" (calendário, 7 dias fixos) por **ciclo
pessoal**: N dias, definidos pela pessoa, ancorados numa data — opt-in,
configurado uma vez em Ajustes, reutilizável por qualquer missão diária.

Sem configurar nada, nenhum comportamento existente muda.

## Modelo de dados

### `app_settings` (colunas novas, mesmo padrão de `reminder_enabled`/`reminder_time`)

| coluna | tipo | default | significado |
|---|---|---|---|
| `cycle_enabled` | INTEGER (bool) | 0 | ciclo pessoal ativo |
| `cycle_length` | INTEGER | 7 | tamanho do ciclo em dias (2–15) |
| `cycle_off_days` | TEXT | `""` | CSV de índices 0..(length-1) que são folga, ex.: `"1"` |
| `cycle_anchor_date` | TEXT | `""` | data ISO do dia 0 do ciclo |

`settings.py` ganha `set_work_cycle(enabled, length, off_days, anchor_date)`
e os 4 campos entram em `DEFAULTS`/`get_settings()` — mesmo padrão de
`set_reminder`.

### `missions` (coluna nova)

| coluna | tipo | default | significado |
|---|---|---|---|
| `follow_cycle` | INTEGER (bool) | 0 | missão diária agendada "nos dias de folga do ciclo pessoal" em vez de dias fixos da semana |

Migração via `ALTER TABLE ... ADD COLUMN` em `database.init_db()`, mesmo
padrão de `challenge_id`/`suggestion_id`. Mutuamente exclusivo com
`custom_days` na prática (UI só permite escolher um modo por vez; no
banco os dois campos convivem sem problema, `is_scheduled_today` decide
qual olhar).

`missions.add_mission`/`update_mission` ganham o parâmetro
`follow_cycle=False`.

## Lógica de agendamento

```python
def _cycle_off_today(today=None):
    """True se hoje é dia de folga do ciclo pessoal configurado em Ajustes.
    Sem ciclo ativo (ou tamanho inválido), sempre False — falha pro lado
    de "todo dia" (ver is_scheduled_today), nunca esconde a missão."""
    prefs = settings.get_settings()
    if not prefs["cycle_enabled"] or prefs["cycle_length"] <= 0 or not prefs["cycle_anchor_date"]:
        return False
    today = today or date.today()
    anchor = date.fromisoformat(prefs["cycle_anchor_date"])
    cycle_day = (today - anchor).days % prefs["cycle_length"]
    off_days = {int(d) for d in prefs["cycle_off_days"].split(",") if d}
    return cycle_day in off_days
```

`is_scheduled_today` passa a checar `follow_cycle` ANTES de `custom_days`:

```python
def is_scheduled_today(mission_row, today=None):
    if mission_row["periodicity"] != "diaria":
        return True
    if mission_row["follow_cycle"]:
        return _cycle_off_today(today)
    days = mission_row["custom_days"] or ""
    if not days:
        return True
    today = today or date.today()
    return str(today.weekday()) in days.split(",")
```

`missions.py` passa a importar `settings` (sem risco de import circular —
`settings.py` só importa `database`/`i18n`).

Sequência (`current_streak`), progresso do dia (`progress_today`) e o
multiplicador de sequência não mudam — já tratam "agendada hoje" de forma
genérica via `is_scheduled_today`, herdam o comportamento automaticamente.

## UI — Ajustes ("Meu ciclo de trabalho")

Nova seção, mesmo estilo da seção de lembrete:

- `ClayCheck`/toggle: ativar ciclo pessoal.
- 3 `ClayButton` de atalho: **12x36** (length=2, off="1"), **24x48**
  (length=3, off="1,2"), **Personalizado**.
- Personalizado: `ClaySpinner` pro tamanho do ciclo (2–15) + uma linha de
  `DayToggle` (widget já existente, reusado — mesmo componente do seletor
  de dias específicos das missões, só que numerado "1".."N" em vez de
  letras de dia da semana) pra marcar quais dias são folga.
- `ClaySpinner` "Hoje é o dia ? do seu ciclo" (1..tamanho) — ao salvar,
  `anchor_date = hoje - (N-1) dias`. Reconfigurar QUALQUER campo do ciclo
  sempre repassa por essa pergunta e recalcula a âncora do zero — sem
  "recalibração" separada, mantém a UX de uma tela só.

## UI — Missões (`MissionFormPopup`)

Periodicidade "diária" ganha um terceiro modo de agendamento, ao lado de
"Todo dia"/"Dias específicos": **"Nos meus dias de folga"** — só habilitado
se `settings.get_settings()["cycle_enabled"]`; sem ciclo configurado,
aparece desabilitado com uma dica ("configure seu ciclo em Ajustes").

## Tutorial (primeira abertura)

Novo passo em `TUTORIAL_STEPS` (`main.py`), depois de "customize":
`"work_cycle"` — explica o recurso em 1-2 frases + onde configurar.

## i18n

Chaves novas (pt/en/es/fr/de): seção de ajustes (título, toggle, botões
de atalho, spinners), rótulo do novo modo de agendamento na missão, dica
de "configure seu ciclo primeiro", e o par `tutorial_work_cycle_title`/
`tutorial_work_cycle_body`.

## Testes

`test_missions.py`: `_cycle_off_today` isolado (ciclo 2/3/7 dias,
`today` injetado) + `is_scheduled_today` com `follow_cycle=True` nos três
casos (ciclo desativado → sempre True; dia de folga → True; dia de
trabalho → False). `test_settings.py`: `set_work_cycle`/`get_settings`
ida e volta.

## Fora de escopo (ponytail — upgrade se pedirem)

- Ciclo por missão (cada missão com seu próprio ciclo) — só existe o
  ciclo pessoal único, global.
- Calendário manual dia-a-dia — só ciclos repetitivos.
- "5x2 rotativo" como atalho — se o padrão de fato se repete a cada 7
  dias, já é só "dias específicos da semana" (recurso existente); um
  atalho separado seria redundante.
