# Discipliner — desenvolvimento

Documentação técnica interna do projeto: como rodar, testar, empacotar pro Android, e como cada peça (conta, monetização, notificações, IA de lembrete etc.) funciona por dentro. Para a visão geral do app, veja o [README](../README.md).


App de disciplina por missões (diárias/semanais/mensais) com pontos, sequência própria
por periodicidade (com multiplicador de pontos e congelamento mensal na diária), nível
de XP, emblemas, lembrete diário, temas de cor e gráfico de desempenho (calendário,
colunas ou linhas — troca na hora). Visual minimalista (ex-claymorphism, sem sombra
dupla), formato de janela tipo celular, barra de abas embaixo.

## Rodar

```bash
venv\Scripts\python.exe main.py
```

## Testar a lógica (sem abrir a UI)

```bash
venv\Scripts\python.exe test_missions.py
venv\Scripts\python.exe test_account.py
venv\Scripts\python.exe test_i18n.py
venv\Scripts\python.exe test_achievements.py
venv\Scripts\python.exe test_mascot.py
venv\Scripts\python.exe test_backup.py
venv\Scripts\python.exe test_progress.py
venv\Scripts\python.exe test_mission_suggestions.py
venv\Scripts\python.exe test_challenges.py
venv\Scripts\python.exe test_share_card.py
venv\Scripts\python.exe test_settings.py
venv\Scripts\python.exe test_theme.py
```

## Sequências por periodicidade e multiplicador de pontos

Cada periodicidade (diária/semanal/mensal) tem sua PRÓPRIA sequência, calculada só a
partir das conclusões daquele tipo (`completions.periodicity`, gravado no momento da
conclusão — sobrevive mesmo se a missão for editada ou apagada depois). Acesso pela
aba Missões: o card "Sequência" agora é um botão que abre a tela Sequências, com 3
mini-abas (Diária/Semanal/Mensal).

Congelamento (1 buraco perdoado por mês) só existe na diária — não faz sentido
perdoar 1 semana ou 1 mês inteiro do mesmo jeito.

Um período só conta pra sequência com pelo menos `missions.COMPLETION_THRESHOLD`
(65%) das missões daquela periodicidade concluídas — não basta 1 conclusão
qualquer quando há várias missões do mesmo tipo. O "total" de cada período usa a
lista ATUAL de missões (`list_missions()`), não um retrato histórico de quais
existiam naquele dia — uma missão criada ou apagada depois muda retroativamente o
percentual de períodos antigos também (mesma simplificação que `progress_today()`
já fazia pro dia de hoje; rastrear isso direito exigiria guardar quando cada
missão existiu).

Multiplicador de pontos por degrau de sequência (`missions.MULTIPLIER_TIERS`):

| Diária | Semanal | Mensal | Multiplicador |
|---|---|---|---|
| 5+ dias | 2+ semanas | 1+ mês | 1.25x |
| 10+ dias | 4+ semanas | 2+ meses | 1.5x |
| 20+ dias | 6+ semanas | 3+ meses | 1.75x |
| 30+ dias | 8+ semanas | 4+ meses | 2.0x |

Cada missão usa a sequência do próprio tipo.

Aplicado automaticamente em `complete_mission` — os pontos gravados no histórico já
saem multiplicados (e por isso contam multiplicados pro nível/XP também).

## Nível e limite de missões

Cada nível pede mais XP que o anterior (`missions._xp_needed_for_level`, progressão
aritmética): nível 1 fecha com 50 XP, nível 2 com 75, nível 3 com 100... Os limiares
são cumulativos (nível 3 abre em 50+75=125 XP total).

O número de missões ativas ao mesmo tempo é limitado: 7 no grátis, 15 no Premium
(`missions.FREE_MISSION_CAP`/`PREMIUM_MISSION_CAP`), +1 pra cada nível já
desbloqueado além do 1º (`missions.mission_limit`). Só bloqueia CRIAR — editar uma
missão que já existe nunca trava, mesmo que o limite tenha caído depois (ex.:
Premium desativado).

## Focum, o mascote

Aparece no histórico vazio (dormindo) e como foto de perfil desbloqueável — cada pose
é liberada por uma conquista diferente (ver `mascot.py`). As artes (recortadas e com
fundo removido a partir da folha de referência original) ficam em `assets/focum/`;
sem algum arquivo o app não quebra — só não mostra aquele estado até ele existir.

## Recompensas (além da foto de perfil)

Pesquisa rápida sobre gamificação em apps de hábito indicou que combinar vários tipos
de recompensa retém mais gente que depender só de XP/streak — apps que usam só um
mecanismo tendem a perder a maioria dos usuários antes de 90 dias. 4 recompensas novas:

- **Loja de Recompensas** (`rewards.py`, aba "Loja" na tela Missões) — o usuário define
  as PRÓPRIAS recompensas (ex.: "Assistir um filme", 20 pontos) e troca pontos ganhos
  por elas. Reaproveitáveis (resgata quantas vezes quiser, não é "compra única"). Pontos
  disponíveis = todos os pontos já ganhos (mesmo total do nível) menos o que já foi
  gasto — sempre calculado na hora, nunca uma coluna própria pra não dessincronizar.
- **Moldura de avatar** (`mascot.FRAMES`) — anel colorido ao redor da foto de perfil,
  4 tiers (bronze/prata/ouro/diamante) nos mesmos marcos de sempre (streak 7/30/100,
  nível 10). Cor pura via canvas, sem precisar de arte própria.
- **Certificado de marco** (`share_card.generate_certificate`) — ao desbloquear um
  emblema de sequência diária (3/7/14/30/100 dias), a aba de detalhes do emblema ganha
  um botão "Compartilhar Certificado" — estende o cartão de sequência já existente
  (`share_card.generate`) com um layout mais formal (moldura dupla, número em destaque).
- **Ícone do app customizável** (`main.set_app_icon`, mesmos tiers da moldura) — troca
  o ícone na tela inicial do celular via `<activity-alias>` (técnica padrão do Android:
  várias "portas de entrada" pra mesma atividade, cada uma com seu próprio ícone,
  ligadas/desligadas em tempo real via `PackageManager`). Os PNGs coloridos
  (`assets/icons_alt/`, gerados por `scripts/gen_alt_icons.py` — duotone a partir do
  ícone base, sem arte nova desenhada à mão) entram no APK via `android.add_resources`;
  o XML dos aliases fica em `android_manifest_extra.xml`, injetado via
  `android.extra_manifest_application_arguments`. **Só existe de verdade no Android** —
  no PC essa "tela inicial" nem existe, e essa é a ÚNICA das 4 recompensas que não dá
  pra confirmar rodando local: só verificando num Android real depois de gerar o APK.

## Idioma

Português, English, Español, Français, Deutsch — trocável na aba Ajustes, fica salvo
entre execuções. Só idiomas de escrita latina por enquanto: a fonte do app (Candara)
não tem glifos pra CJK/cirílico/árabe (apareceria como caixa vazia). Nomes de missão e
observações digitados pelo usuário nunca são traduzidos — só a interface.

## Por que uma venv com Python 3.12?

O Kivy ainda não publica wheels pro Python 3.14 (o padrão da máquina) no Windows.
Por isso este projeto usa uma venv isolada com Python 3.12, só pra ele — não mexe
no Python 3.14 do resto do sistema.

## Conta (aba Configurações) — Supabase Auth de verdade

Conta deixou de ser só um perfil local: `account.py` fala com o Supabase Auth
via `supabase_client.py` (Auth + REST, só `urllib` da stdlib, sem SDK novo pro
buildozer empacotar). O SQLite local (`local_session`, em `database.py`) só
guarda um CACHE do token de sessão, pra não pedir login toda vez que o app
abre — quem manda em senha, confirmação e e-mail é o Supabase.

- **Cadastro/login**: onboarding e Ajustes têm os dois num formulário só
  (`account_mode` alterna os campos). E-mail e senha ficam com o Supabase, não
  com este código — nunca há hash de senha local aqui.
- **Confirmação de e-mail**: é real agora (o Supabase manda o e-mail com o
  link) — sem código de 6 dígitos fake. Ficou por LINK de propósito: o Supabase
  só deixa editar o HTML puro ("Source") de um template de e-mail com **SMTP
  próprio configurado** (Authentication → Emails → SMTP Settings); sem
  domínio, configurar isso só pra trocar link por código não compensa — o link
  padrão já funciona sem nenhuma configuração extra.
  - **No Android**, o link volta pro **próprio app**: `account.sign_up` manda
    `redirect_to=discipliner://login-callback` (`account.EMAIL_CONFIRM_DEEPLINK`),
    o `<intent-filter>` da PythonActivity (`android_intent_filters.xml`) captura
    esse scheme, e `deeplink.py` extrai os tokens do fragmento da URI e loga
    direto (`account.complete_deeplink_login`) — o app abre já autenticado.
    Precisa adicionar `discipliner://login-callback` em Supabase Dashboard →
    Authentication → URL Configuration → **Redirect URLs**.
  - **Fallback / desktop**: o link cai numa página estática (`docs/index.html`)
    publicada pelo **GitHub Pages** (Settings → Pages → Source: branch `beta`,
    pasta `/docs`); daí o botão "Já confirmei, entrar" loga com as credenciais
    do cadastro (guardadas só em memória — ver `App._pending_email`). Configura
    essa URL (`https://<usuario>.github.io/<repo>/`) em "Site URL" e também em
    "Redirect URLs".
- **Login (senha + link por e-mail)**: `account.login` confere a senha e manda
  o e-mail "Magic Link" (`/auth/v1/otp`, `create_user=False`,
  `redirect_to=discipliner://login-callback`). Tocar no link abre o app e o
  mesmo deep link do cadastro entra sozinho (`account.complete_deeplink_login`,
  só aceita o e-mail anotado em `pending_signup_email` por este aparelho).
  Senha sozinha não loga. O template Magic Link precisa ter
  `{{ .ConfirmationURL }}` (login) e `{{ .Token }}` (apagar conta).
- **Esqueci minha senha / Trocar senha** (Ajustes > Conta): manda o e-mail de
  redefinição com `redirect_to=discipliner://reset-password`
  (`account.RESET_PASSWORD_DEEPLINK`). O link abre o app direto na tela
  `reset_password` (`screens_onboarding.kv` > `ResetSenha`). Só aceita o link
  de quem pediu NESTE aparelho (`app_settings.pending_reset_email`), igual à
  confirmação de cadastro. **Painel**: adicionar `discipliner://reset-password`
  em Authentication → URL Configuration → Redirect URLs.
- **Apagar conta** (link pequeno no canto de Ajustes > Conta): aviso do que se
  perde → código de uso único por e-mail (`/auth/v1/otp`, template **Magic
  Link** do painel, que precisa ter `{{ .Token }}` e o aviso) → a pessoa digita
  o código → `/auth/v1/verify` devolve uma sessão nova → Edge Function
  `delete-account` (só aceita JWT com `amr=otp` de até 10 min) apaga backup,
  compra e o usuário do Auth → o app apaga o banco local e volta ao primeiro
  acesso (`account.delete_account`).
- **Google**: segue desabilitado — precisa ativar o provider no painel do
  Supabase (Authentication → Providers) com credenciais OAuth do Google Cloud
  Console, configuração externa que só o dono do projeto consegue fazer.
- Schema do banco (Postgres, com RLS por `user_id`) fica em
  `supabase_schema.sql` — roda uma vez no SQL Editor do projeto Supabase.
- `avatar` de perfil não é mais campo de conta — é preferência de aparelho
  (`app_settings.profile_avatar`), funciona igual pra quem tá logado ou como
  convidado.

### Segurança dos fluxos de autenticação

O rate limit "de verdade" dos endpoints de auth é do **Supabase Auth**
(GoTrue), server-side — sign-in/sign-up, envio de OTP/e-mail e refresh de
token já vêm limitados por projeto. Ajuste em **Dashboard → Authentication →
Rate Limits** e, para lançar, **ligue a proteção CAPTCHA** (hCaptcha ou
Cloudflare Turnstile) em **Authentication → Settings** — é isso que barra o
bot que fica martelando `/auth/v1/token`.

Do lado do app (`main.py`, decorator `_auth_action`), a trava é
complementar: nenhum handler de auth reentra enquanto uma chamada está no ar
(as requisições são síncronas, até ~10s num 3G ruim), e os botões de
"reenviar código" / "esqueci a senha" exigem `AUTH_RESEND_COOLDOWN` (60s)
entre tentativas — anti-flood e anti-e-mail-bomba a partir do próprio
cliente.

### Backup na Nuvem — preso à conta

Dois botões novos em Ajustes (só aparecem logado): **"Backup na Nuvem"** e
**"Restaurar da Nuvem"**. Sobe/baixa o `daily_quest.db` (SQLite local) **inteiro**
pro Supabase Storage (bucket privado `backups`, 1 arquivo por conta em
`backups/<user_id>/daily_quest.db`, RLS garantindo que cada um só mexe na
própria pasta — ver `supabase_schema.sql`).

Decisão de propósito: o banco local continua sendo a fonte da verdade, e a
nuvem é só uma cópia de segurança — **nunca sincroniza sozinha**, sempre uma
ação explícita do usuário nos dois sentidos (mesmo motivo do aviso "restaurar
substitui tudo" que já existia pro backup local). Um sync automático/bidirecional
de verdade (mexer em 2 aparelhos ao mesmo tempo, resolver conflito) foi
considerado e descartado por enquanto — muito mais superfície pra bug e risco
de perder dado sem querer, pra um app que hoje é "1 usuário por aparelho".

Cuidado tomado: restaurar sobrescreve o arquivo INTEIRO, `local_session`
(cache do token de sessão) incluso — sem reescrever a sessão atual por cima
depois (`account.restore_session_row`), o restore deslogaria a conta sozinho
(ou pior, deixaria o token de sessão de outro aparelho no lugar).

## Política de Privacidade e Termos de Uso

Ficam em Ajustes → "Sobre o App", como texto só-leitura (sem checkbox de aceite —
não é obrigatório enquanto o app não sai desta beta). Já atualizada pra deixar
claro que conta (nome/e-mail/senha) vive no Supabase agora — missões, conclusões
e preferências continuam 100% locais. Também descreve os anúncios (AdMob, só
grátis) e o relato de crash anônimo (ver seção própria).

## Relato remoto de crash (`crash_reporter.py`)

Toda exceção **não tratada** — fora do loop do Kivy (`sys.excepthook`) ou dentro
dele (`kivy.base.ExceptionManager`) — gera um relatório e faz um `POST` numa
thread daemon pra tabela `crash_reports` do Supabase. O handler do Kivy devolve
`RAISE`: o app continua caindo do mesmo jeito que sem o reporter, ele **não
mascara bug nenhum**, só registra antes. Pra crash fatal dá um `join(3s)` pra
dar chance do envio sair antes do processo morrer. Tudo em `try/except: pass` —
um reporter que quebra durante um crash seria pior que não ter.

O relatório é **anônimo** e só técnico: o traceback (cortado em 8k), `error_type`,
`APP_VERSION` (constante em `main.py`, bump manual por release), a plataforma
(`android`/`win`/…), a versão do OS, e um `install_id` — um UUID aleatório
gerado no 1º crash e guardado em `app_settings.install_id`. **Não** é `user_id`,
não liga a nenhuma conta; só serve pra contar aparelhos distintos. Sem e-mail,
nome, ou conteúdo de missão. Descrito no texto da Política de Privacidade.
Dedup por sessão: o mesmo traceback não vai duas vezes.

A tabela `crash_reports` tem RLS só de `INSERT` pra qualquer um (a anon key
basta) e **nenhuma** policy de `SELECT` — o app grava sem login e ninguém lê
pela anon key; você lê no painel do Supabase (Table Editor / SQL Editor, que
roda como `service_role`). Rodar o trecho de `supabase_schema.sql` uma vez.

## Telemetria de retenção (anônima)

`telemetry.ping` grava no máximo 2 linhas por aparelho por dia na tabela
`app_activity`: `open` (no `build()` e no `on_resume`) e `complete` (ao concluir
uma missão). Cada linha tem só `install_id` (o mesmo UUID aleatório do crash
report), `day`, `kind` e `app_version`. Só no Android — desktop e testes não
mandam nada. Duplicado é ignorado no servidor; sem rede, tenta de novo na
próxima chamada do dia. Descrito na Política de Privacidade.

Mesmo modelo do `crash_reports`: RLS só de `INSERT` (e só com a data de hoje,
±2 dias), nenhum `SELECT` pela anon key. Consultas no SQL Editor:

```sql
-- retenção D1 / D7 por coorte (dia do 1º "open")
with primeiro as (
    select install_id, min(day) as d0 from app_activity where kind = 'open' group by 1
)
select d0 as coorte,
       count(*) as aparelhos,
       count(*) filter (where exists (select 1 from app_activity a
           where a.install_id = p.install_id and a.kind = 'open' and a.day = p.d0 + 1)) as d1,
       count(*) filter (where exists (select 1 from app_activity a
           where a.install_id = p.install_id and a.kind = 'open' and a.day = p.d0 + 7)) as d7
from primeiro p group by 1 order by 1;

-- por dia: quantos abriram e quantos concluíram alguma missão
select day,
       count(*) filter (where kind = 'open') as abriram,
       count(*) filter (where kind = 'complete') as concluiram
from app_activity group by day order by day;
```

## Reconquista (quem parou de concluir missões)

`reconquista.py` (sem Kivy) conta os dias desde a última conclusão e manda no
máximo **3 avisos por ausência**: com 2, 5 e 14 dias. Depois para. Concluir uma
missão começa outra contagem. Quem sumiu muito tempo (celular desligado) recebe
1 aviso, não uma rajada. Quem nunca concluiu nada não recebe.

Entrega: um alarme próprio (`android_alarm.agendar_reconquista`,
`setExactAndAllowWhileIdle` — sem o ícone de despertador do `setAlarmClock`)
acorda o `ServiceReminder` no dia do aviso, no horário do lembrete diário (ou
19:00 se ele estiver desligado). Mesmo id de notificação do lembrete diário:
se os dois caem no mesmo dia, a reconquista substitui em vez de empilhar.
Reagendado no boot do app, ao concluir missão e toda vez que o serviço acorda.
Estado em `app_settings.winback_state`.

## Lembrete diário — limitação real, não escondida

O lembrete é conferido por uma **thread** (`App._start_reminder_watcher`), não pelo
`Clock` do Kivy: o `Clock` congela quando o app vai pra 2º plano, e enquanto ele era
o motor o lembrete das 20:00 só saía quando a pessoa reabria o app — chegando horas
"atrasado". A thread continua rodando com o app minimizado.

Com o app **FECHADO** (morto pelo Android por Doze, falta de memória ou o
usuário deslizando pra fora dos recentes) não há processo nem thread — esse caso
é coberto por um **serviço do p4a acordado pelo `AlarmManager`**
(`service_reminder.py` + `android_alarm.py`, `services = reminder:...` no
buildozer.spec). O serviço é **permanente** (`services = reminder:...:foreground:sticky`): sobe
junto com o app, se promove a foreground e não sai mais.

Chegamos nele por eliminação, testando no emulador:

1. **serviço comum** — o Android 8+ recusa iniciar com o app morto
   (`Background start not allowed: service ... startFg?=false`);
2. **foreground curto** (`shortService`) — funciona, mas cada disparo depende de
   o alarme conseguir acordar o serviço;
3. **foreground permanente** — o serviço nunca morre, então não depende disso.

**Dois preços, os dois conscientes:**

* **notificação permanente na barra de status**, exigida pelo Android de todo
  serviço em foreground e que o usuário não pode dispensar;
* o tipo declarado passa a ser **`specialUse`** (injetado por
  `p4a_hooks._tipar_servico`, com o `<property>` filho que o Android 14 exige),
  e isso **pede justificativa na revisão da Play Console** — era exatamente o
  que o `shortService` evitava.

### Dois mecanismos de alarme, de propósito

| | API | por quê | preço |
|---|---|---|---|
| **Lembrete diário** | `setAndAllowWhileIdle` | atrasar alguns minutos é aceitável | pode atrasar em Doze |
| **Lembrete por missão** (Premium) | `setAlarmClock` | horário escolhido pra uma missão específica não pode atrasar; é exato e imune a Doze sem pedir `SCHEDULE_EXACT_ALARM` | **ícone de despertador** na barra de status e o horário exposto nos relógios do sistema |

Os alarmes de missão têm request code próprio por missão
(`android_alarm._codigo_missao`), pra cada um poder ser substituído e cancelado
sozinho, e são ressincronizados a cada boot e sempre que o lembrete muda
(`main._sincronizar_alarmes_missao`). Sem Premium, todos são cancelados.

**Cuidado ao testar:** `adb shell am force-stop` marca o app como `stopped=true`
e o Android **cancela todos os alarmes dele** — o teste falha por motivo errado.
Use `am kill`, que mata o processo mantendo os alarmes.

Existiu antes uma versão com `AlarmManager` + `BroadcastReceiver` em Java, que
foi removida (frágil de empacotar, impossível de testar sem device). A diferença
agora é que o serviço é Python puro gerado pelo p4a, sem `.java` compilado à mão.

Por isso a entrega é **em camadas** (`App._fire_reminder`):

1. **Popup dentro do app (`ReminderPopup`)** — o mecanismo garantido. Como o lembrete
   só roda com o app aberto, esse popup sempre é visto. É a "notificação" de fato.
2. **Notificação de sistema (`notify.send`)** — best-effort por cima: no Android via
   pyjnius (canal + `PendingIntent` com `FLAG_IMMUTABLE` + `cast()` no
   `NotificationManager`, que sem isso falha calado); no desktop via `plyer` (balão do
   systray, que o Windows 10/11 às vezes engole). Se qualquer uma falhar, o popup do
   passo 1 ainda aparece.

`App.on_resume` re-roda a checagem ao voltar pro app (senão esperaria até 60s do
próximo tick do `Clock`), e há uma checagem ~4s depois do boot.

## Estrutura

- `main.py` — app Kivy (telas, popups, tema claro/escuro/cor, lembrete, wiring)
- `ui.kv` — layout (cards/botões/checkbox/spinner customizados, sem depender de skin padrão do Kivy)
- `screens_onboarding.kv` — as 3 telas de onboarding (boas-vindas / escolha de conta / cadastro), carregadas sob demanda por `App._ensure_screen` no 1º acesso — não pesam no parse de todo boot. O tutorial guiado NÃO é tela, é o `TutorialOverlay`
- `widgets.py` — os componentes visuais reutilizáveis (ClayCard, ClayButton, ClayCheck, ClaySpinner, ClayProgressBar)
- `heatmap.py` — o gráfico em calendário-mapa de calor, desenhado direto no canvas (sem Matplotlib)
- `charts.py` — os gráficos de colunas e de linhas, mesma ideia (canvas puro, mesma fonte de dados do heatmap)
- `database.py` — SQLite puro (tabelas `missions`, `completions`, `local_session`, `app_settings`, `streak_freezes`); WAL + `synchronous=NORMAL` e índices em `completions` (tabela quente)
- `missions.py` — regras de conclusão por período, pontos, sequência (com congelamento) e nível
- `achievements.py` — emblemas: sempre recalculados a partir do estado atual, não guardam estado à parte
- `mascot.py` — poses do Focum e quais conquistas desbloqueiam cada uma (imagens em `assets/focum/`)
- `supabase_client.py` — chamadas HTTP cruas (`urllib`) pro Supabase Auth + REST
- `account.py` — conta de verdade (Supabase Auth), com cache local da sessão em `local_session`
- `supabase_schema.sql` — schema Postgres + RLS pro projeto Supabase (roda 1x no SQL Editor)
- `supabase/functions/stripe-webhook/` — Edge Function que valida o pagamento do Stripe e libera o Premium (ver Monetização)
- `supabase/functions/create-pix-payment/` — gera um Pix novo (Mercado Pago) pro usuário logado
- `supabase/functions/mercadopago-webhook/` — confere o pagamento Pix e libera o Premium, mesma ideia do stripe-webhook
- `settings.py` — preferências persistidas (idioma, tema, lembrete, sequência recorde)
- `backup.py` — exportar/restaurar o `daily_quest.db` inteiro via diálogo nativo (tkinter)
- `mission_suggestions.py` — biblioteca de missões prontas pra adicionar com 1 toque (nomes traduzidos em `i18n.py`)
- `challenges.py` — pacotes temáticos de missões (várias de uma vez), reaproveita `mission_suggestions.py`
- `share_card.py` — gera o PNG compartilhável da sequência e o certificado de marco (PIL, sem servidor)
- `rewards.py` — Loja de Recompensas: recompensas autodefinidas pelo usuário, trocadas por pontos
- `i18n.py` — traduções da interface (pt/en/es/fr/de)
- `progress.py` — monta os dados do heatmap mensal e os resumos semanal/mensal
- `scripts/gen_presplash.py` — gera `assets/presplash.json` (Lottie do presplash nativo)
- `scripts/gen_alt_icons.py` — gera `assets/icons_alt/*.png` (variações de cor do ícone customizável)
- `notify.py` — notificação local (pyjnius direto no Android — canal + PendingIntent com FLAG_IMMUTABLE; o plyer 2.1.0 quebra no Android 12+)
- `deeplink.py` — captura `discipliner://login-callback` (e-mail de confirmação volta pro app) e loga com os tokens do fragmento
- `android_intent_filters.xml` — `<intent-filter>` do deep link, injetado no `<activity>` via `android.manifest.intent_filters`
- `ads.py` — anúncios AdMob (banner + intersticial, só Android/grátis; consentimento UMP) — ver Anúncios
- `crash_reporter.py` — relato remoto de exceção não tratada, anônimo (ver seção própria)
- `android_java/AdMobBridge.java` — load/show do intersticial (o callback do SDK é classe abstrata, pyjnius só faz interface)
- `android_manifest_extra.xml` — `<activity-alias>` do ícone do app customizável (ver Recompensas)
- `p4a_hooks.py` — injeta `android_manifest_extra.xml` no `AndroidManifest.xml` e copia `android_java/*.java` pro projeto Android gerado
- `daily_quest.db` — gerado em runtime, fora do git

## Lembrete inteligente

O lembrete (Ajustes → horário) agora olha o estado do dia antes de notificar: se
todas as missões de hoje já foram concluídas, não manda nada (evitar ruído). Se
sobrou algo, o texto sai de um pool de `REMINDER_MESSAGE_COUNT` mensagens
descontraídas (`reminder_msg_*` no `i18n.py`, algumas com piada geek), escolhida
**pela data** e não sorteada: o app pode ser morto e reaberto que a mensagem do dia
é a mesma, e ela troca sozinha no dia seguinte. Se além disso já existe uma
sequência diária rodando, anexa o que falta ("sua sequência está em risco — ainda
falta: X, Y") — só quando há algo real em jogo.

O emoji dessas mensagens vai só pra notificação de sistema, que é desenhada pelo
Android; o popup dentro do app recebe a versão sem emoji (`main._sem_emoji`),
porque o Kivy desenha com uma fonte só e não faz fallback — emoji viraria
quadradinho. `test_theme.run_glyphs` cobra isso.

**Lembrete por missão (Premium)**: além do horário único acima, cada missão pode
ter seu próprio horário de lembrete (campo no popup de Adicionar/Editar Missão,
`missions.reminder_time`). Ver `DailyQuestApp._check_mission_reminders`.

**Cobertura (as duas):** com o app aberto ou minimizado quem dispara é a thread
(a cada `REMINDER_TICK_SECONDS`); com o app fechado, o serviço acordado pelo
`AlarmManager` (ver acima). O lembrete POR MISSÃO (Premium) ainda depende só da
thread — o serviço cobre o lembrete diário. Existiu
uma versão com `AlarmManager` + um `BroadcastReceiver` em Java (dispararia com o
app fechado), mas era um `.java` compilado por hook do p4a: impossível de testar
sem um device, frágil de empacotar e, na prática, não notificava. Foi removido em
favor da notificação simples. Se o background real virar requisito, o caminho é
um `ForegroundService` do p4a (mais robusto que o `BroadcastReceiver` avulso).

## Ciclo pessoal (escalas de trabalho rotativas)

Pra quem trabalha em escala rotativa (12x36, 24x48, plantão) e o dia de folga
NÃO é sempre o mesmo dia da semana — `custom_days` (dias fixos) não serve pra
isso. Em Ajustes → "Meu Ciclo de Trabalho" (opt-in, desligado por padrão): a
pessoa define um ciclo de N dias (atalhos prontos 12x36/24x48, ou tamanho
livre) + quais dias dele são folga, calibrado por "qual dia do seu ciclo é
hoje" (sem precisar lembrar uma data exata). Missões diárias ganham um
terceiro modo de agendamento, "Nos meus dias de folga" (`missions.follow_cycle`),
mutuamente exclusivo com dias fixos da semana. Ver `missions._cycle_off_today`
e o design completo em `docs/superpowers/specs/2026-08-28-ciclo-pessoal-design.md`.

## Moldura/ícone do app via multiplicador de sequência

Além do caminho original (sequência/nível — `streak_7`, `level_10`, etc.),
moldura e ícone do app agora também desbloqueiam ao alcançar um degrau do
multiplicador de pontos por sequência (`missions.MULTIPLIER_TIERS`: 5/10/20/30
dias de sequência = 1.25×/1.5×/1.75×/2× nos pontos). Cada degrau é um emblema
novo (`streak_multiplier_125/150/175/200` em `achievements.py`) — igual às
poses do Focum: o emblema desbloqueia sozinho, sem precisar marcar nenhuma
missão. `mascot.FRAMES[tier]["requires"]` agora é uma LISTA — o tier
desbloqueia se QUALQUER emblema da lista estiver liberado (o de sempre OU o
novo), ver `mascot.frame_status`.

## Desafios

Tela de Missões → botão "Desafios": pacotes temáticos (Corpo em Dia, Foco Total,
Casa em Ordem, Finanças no Controle) que adicionam várias missões relacionadas de
uma vez. Reaproveita `mission_suggestions.py` pra periodicidade/dificuldade — não
duplica dado, só agrupa. Não é um desafio com prazo (não expira sozinho em 30
dias) — isso pediria estado próprio (data de início, o que fazer ao terminar);
ver comentário `ponytail:` em `challenges.py` pro caminho de upgrade.

## Vinheta de abertura e onboarding

Ao abrir, o app mostra uma tela "splash" com o ícone em fade (entra, segura,
sai, ~1,15s) enquanto os dados carregam, tanto no celular quanto no PC (é só
Kivy puro, `main.py._play_splash`, funciona igual nos dois). No Android, o
`buildozer.spec` também configura um presplash nativo com o mesmo ícone, que
aparece instantâneo enquanto o Python ainda está subindo, a parte mais lenta
e que a vinheta em Kivy não alcança. Esse presplash nativo é uma animação
**Lottie** (`assets/presplash.json`, gerada por `scripts/gen_presplash.py` a
partir de `assets/icon.png`) com o MESMO fade in/segura/fade out da vinheta
em Kivy — sem isso, o presplash nativo é só uma imagem estática, sem
controle de fade nenhum (corte seco). Rode o gerador de novo se o ícone
mudar (`python scripts/gen_presplash.py`).

Na primeira execução (`app_settings.onboarding_done` ainda em 0), depois da
vinheta o app mostra, nesta ordem: tela de boas-vindas (com seletor de
idioma no topo, o que é o app, Política de Privacidade e Termos de Uso),
escolha entre criar conta, entrar numa conta que já existe ou continuar como
convidado (dá pra fazer tudo isso depois em Ajustes também), e por fim o
tutorial guiado. Cadastro/login não bloqueiam o onboarding esperando
confirmação de e-mail — segue pro tutorial de qualquer jeito, e a confirmação
se resolve depois em Ajustes.

O tutorial não é uma tela separada: é o `TutorialOverlay` (`widgets.py`)
adicionado direto ao `Window`, que roda **por cima da tela real** de Missões
(e de Ajustes nos últimos passos). Cada passo escurece a tela, recorta um
foco no widget-alvo (por `id`, ver `TUTORIAL_STEPS` em `main.py` — `tut_*`
no `ui.kv`), contorna de verde e liga uma seta até um card com título/corpo
+ `Voltar`/`Pular`/`Próximo`. ~15 passos cobrindo criar missão,
sugestões/desafios, concluir, progresso, sequência, congelamento, nível,
loja, Focum, Ajustes, escala rotativa, lembrete e backup. `_position_tutorial`
rola o alvo pra vista (Ajustes) e tenta reposicionar alguns frames se o
widget ainda não tiver tamanho. Pulável a qualquer momento; as duas telas
anteriores não têm "Pular" porque são rápidas e não bloqueiam nada depois.
Dá pra rever a qualquer momento pelo botão "Rever tutorial" em Ajustes
(`app.tutorial_start()` sem `from_onboarding`).

Cabeçalho e barra de abas ficam escondidos durante boas-vindas/conta, mas
**aparecem** durante o tutorial guiado (os últimos passos apontam pra eles);
o overlay come todos os toques por baixo, então não dá pra sair do fluxo.
Só marca `onboarding_done` ao sair do tutorial (pulando ou terminando),
então fechar o app no meio mostra tudo de novo na próxima vez. Execuções
seguintes vão direto pra aba Missões.

## Cartão de sequência compartilhável

Tela Sequências → "Compartilhar Sequência": gera um PNG quadrado (1080x1080, bom
pra Instagram/stories) com a pose atual do Focum, a sequência e o nível — tudo
desenhado localmente com Pillow, sem enviar nada pra lugar nenhum. Salva via o
mesmo diálogo nativo do backup (tkinter no desktop, seletor do Android via plyer).

## Monetização — Premium, compra única de US$ 3

Modelo: **compra única**, tipo o Streaks/HabitNow (paga uma vez, desbloqueia tudo pra
sempre). Sem servidor pra gerenciar assinatura — combina com o resto do app.

**O que o Premium desbloqueia** (todo o gate já está implementado e testado —
`missions.py`/`achievements.py`/`main.py`/`ui.kv`, ver `test_missions.py::run_premium_freeze_cap`,
`test_achievements.py`, `test_theme.py`):

- **Modo Sem Penalidade** (Ajustes): a sequência diária deixa de ter teto de
  congelamento no mês — nunca quebra por um dia perdido (`missions.current_streak`
  com `max_freezes_per_month=None`).
- **Mais congelamentos de sequência**: 3 por mês em vez de 1 (`missions.PREMIUM_FREEZE_CAP`).
- **Cor de destaque personalizada**: além dos 4 temas prontos, um seletor livre por
  matiz+saturação (`main.custom_accent_variants`, gera accent/accent_soft claro e
  escuro a partir de HSV — sem precisar desenhar uma roda de cor no Kivy).
- **Pose e emblema exclusivos do Focum** ("Apoiador") — cosmético, não afeta o jogo.
  Sem arte ainda (ver `mascot.py`), a pose só aparece no seletor quando o arquivo existir.
- **Enviar uma foto própria de perfil** — substitui a pose do Focum enquanto existir
  (`current_avatar_path` prioriza `profile_photo_path`); escolher uma pose de novo volta
  a usá-la. Redimensionada pra no máximo 512×512 (PIL) ao enviar, salva no diretório
  gravável do app (`database.DB_PATH.parent`). Ver `main.upload_profile_photo`.
- **Estatísticas avançadas**: desempenho por missão, melhor dia da semana de todos
  os tempos, comparação dos últimos 6 meses (`progress.py`, tela "Estatísticas
  Avançadas" a partir da aba Sequências).

### Como a compra funciona (Stripe, não Google Play Billing)

O app não é vendido pela Play Store (é instalado como APK direto, via GitHub Actions)
então cobrar via **Google Play Billing** exigiria pagar a taxa única de US$ 25 de
cadastro de desenvolvedor só pra ativar o billing — sem necessidade, já que o app já
não passa pela loja mesmo. Em vez disso, o fluxo é web, tudo gratuito pra configurar:

1. Botão "Cartão — US$ 3" em Ajustes chama `account.open_purchase_page()`, que abre
   o **Payment Link do Stripe** (`STRIPE_PAYMENT_LINK_USD` em `account.py`) no
   navegador do sistema (`webbrowser.open`, stdlib — no Android o python-for-android
   traduz isso pra um Intent nativo), com `client_reference_id=<user_id do Supabase>`
   grudado na URL.
2. O usuário paga na página do Stripe (fora do app).
3. O Stripe chama o webhook (`supabase/functions/stripe-webhook/index.ts`, uma Edge
   Function do Supabase) avisando `checkout.session.completed`. A function confere a
   assinatura do Stripe, pega o `client_reference_id` de volta e grava na tabela
   `purchases` (só ela tem a `service_role` key pra escrever lá — o app nunca escreve
   "comprei" sozinho, dá pra forjar).
4. Quando o usuário volta pro app e entra em Ajustes, `account.sync_premium_status()`
   lê a própria linha em `purchases` (RLS libera isso) e liga `is_premium` local.

**O que falta pra ficar 100% funcional** (o código de todos os 4 passos acima já está
pronto e testado — `test_account.py`):

1. Criar uma conta grátis em [stripe.com](https://stripe.com) (ou usar uma já existente).
2. No Dashboard: **Product catalog → Add product** — nome "Discipliner Premium",
   preço US$ 3, **one time** (não recorrente). Depois, na página do produto, criar um
   **Payment Link** pra esse preço — vira `STRIPE_PAYMENT_LINK_USD`.
3. Deploy da function: `supabase functions deploy stripe-webhook` (precisa da
   [Supabase CLI](https://supabase.com/docs/guides/cli)). O comando imprime a URL —
   copia ela.
4. No Stripe Dashboard: **Developers → Webhooks → Add endpoint**, cola a URL do passo
   3, escuta o evento `checkout.session.completed`. O Stripe te dá um "Signing secret"
   (`whsec_...`).
5. Configura os segredos da function (uma vez só):
   `supabase secrets set STRIPE_SECRET_KEY=sk_... STRIPE_WEBHOOK_SECRET=whsec_...`
   (a chave secreta fica em Stripe Dashboard → Developers → API keys).
6. Cola o Payment Link do passo 2 em `account.STRIPE_PAYMENT_LINK_USD` (`account.py`).

Pra testar sem gastar de verdade: o Stripe tem um **modo de teste** (toggle no
Dashboard) com cartões falsos (`4242 4242 4242 4242`, qualquer data futura/CVC) —
dá pra criar produto, payment link e webhook de teste em paralelo aos de produção,
sem nenhum custo, e simular a compra inteira de ponta a ponta.

### Pix (Mercado Pago, não Stripe)

Tentamos habilitar Pix como forma de pagamento direto no Stripe primeiro — não deu:
mesmo com a conta Stripe sendo brasileira (saldo em BRL, `pk_live_...`), o Pix não
aparecia na lista de formas de pagamento, e não achamos como liberar sem abrir chamado
com o suporte do Stripe. Em vez de bloquear nisso, o Pix virou um fluxo TOTALMENTE
separado, via **Mercado Pago** (grátis pra criar conta, aceita CPF, API bem
documentada, gera QR code na hora).

Diferença de arquitetura importante: o Stripe usa um **Payment Link** (uma URL que
abre no navegador, fora do app). O Pix não tem esse conceito — o app pede um QR code
NOVO a cada tentativa de compra, mostrado dentro do próprio app (`PixPaymentPopup`):

1. Botão "Pix" em Ajustes chama `account.create_pix_payment()`, que chama a Edge
   Function `create-pix-payment` (`supabase/functions/create-pix-payment/index.ts`) —
   ela sim fala com a API do Mercado Pago, usando o `MERCADOPAGO_ACCESS_TOKEN`
   (secreto, só existe lá dentro, igual o `STRIPE_SECRET_KEY`). Devolve o QR code
   (imagem em base64 + "copia e cola" em texto) pro app.
2. O popup mostra os dois: a imagem do QR (`kivy.core.image.Image` decodificado do
   base64 direto em memória, sem salvar arquivo) e um botão "Copiar Código" (usa
   `Clipboard.copy` — no celular quem paga é o MESMO aparelho que mostra o QR, não dá
   pra escanear a própria tela, então "copia e cola" é o caminho de verdade).
3. O usuário paga no app do banco dele (fora do app).
4. O Mercado Pago chama o webhook (`supabase/functions/mercadopago-webhook/index.ts`)
   avisando que o pagamento mudou de status. A function **rebusca o pagamento na API
   do Mercado Pago** com o access token antes de confiar em qualquer coisa (a
   notificação em si não é assinada, dá pra forjar — só o token secreto garante que
   "approved" é real) e, se aprovado, grava na MESMA tabela `purchases` de sempre
   (`external_reference` = user_id, gravado na criação do pagamento no passo 1).
5. O usuário toca "Já Paguei, Verificar" no popup (ou volta em Ajustes depois) —
   mesmo `account.sync_premium_status()` de sempre, lê `purchases` e liga `is_premium`.

**Pra ficar funcional** (código pronto e testado — `test_account.py`):

1. Criar conta grátis em [mercadopago.com.br](https://www.mercadopago.com.br) (aceita
   CPF, não precisa CNPJ).
2. **Suas integrações → Criar aplicação** → pega o **Access Token** (em
   Credenciais de produção, ou "de teste" pra testar sem valor real primeiro).
3. Deploy das 2 functions:
   `supabase functions deploy create-pix-payment` e
   `supabase functions deploy mercadopago-webhook` (a segunda imprime a URL do
   webhook — copia ela).
4. No painel do Mercado Pago (Sua aplicação → Webhooks), cola a URL do passo 3,
   escuta o evento **"Pagamentos"**.
5. Configura o segredo (uma vez só, vale pras duas functions):
   `supabase secrets set MERCADOPAGO_ACCESS_TOKEN=APP_USR-...` (ou o token de teste,
   que começa com `TEST-`).

Mercado Pago também tem **modo de teste** (credenciais separadas, começando com
`TEST-`) com "usuários de teste" pra simular o pagamento inteiro sem dinheiro real.

## Anúncios (AdMob) — só Android, só grátis

O usuário grátis vê anúncios do **Google AdMob**; **Premium remove todos**. Nada disso
roda no desktop nem afeta quem é Premium — `ads._enabled()` só é `True` no Android com
`is_premium == False`, e todo o resto é no-op.

- **Banner** fixo no rodapé da tela de Missões (`AdView`, pyjnius puro). O `.kv` reserva
  `dp(50)` (`app.ad_banner_visible`) só pra ele não cobrir a barra de abas — o `AdView`
  de verdade é sobreposto pelo próprio SDK (gravity BOTTOM).
- **Intersticial** a cada `ads.INTERSTITIAL_EVERY` (5) conclusões de missão, no máx.
  `ads.INTERSTITIAL_DAILY_CAP` (3) por dia. O teto é persistido em `app_settings`
  (`ad_interstitial_count`/`_date`) — reabrir o app não zera. `android_java/AdMobBridge.java`
  faz só o load/show do intersticial: o callback de load do SDK atual é uma classe
  abstrata e o pyjnius só implementa interfaces.
- **Consentimento (UMP)** roda antes de qualquer request de anúncio (`ads._android_init`)
  — exigência da Play pra usuários da UE.
- `buildozer.spec`: `android.gradle_dependencies` (ads + ump), `android.enable_androidx`,
  `android.meta_data` com o App ID do AdMob, permissão `AD_ID`.

**O que falta pra ficar 100%** (mesma ideia do Stripe):

1. Criar o app no [AdMob](https://apps.admob.com) → criar um **ad unit** de banner e um
   de intersticial.
2. Trocar em `ads.py`: `REAL_APP_ID`, `REAL_BANNER_ID`, `REAL_INTERSTITIAL_ID`, e virar
   `USE_TEST_ADS = False`.
3. Trocar em `buildozer.spec` o `android.meta_data` (`APPLICATION_ID`) pelo App ID real.
4. No AdMob → **Privacy & messaging → GDPR** → publicar uma mensagem de consentimento
   (o UMP no app só mostra a mensagem que você configurar lá).

Enquanto `USE_TEST_ADS = True`, os IDs são os **de teste públicos do Google** — anúncios
de teste aparecem, não geram receita e não arriscam banimento por auto-cliques.

**Ressalva:** o lado jnius/Java só roda no device — não dá pra testar o banner/intersticial
fora de um build real. A lógica pura (contador → gatilho, teto diário) é o que
`test_ads.py` cobre.

## Usar no celular (Android)

O código já está pronto pra empacotar — `buildozer.spec` configurado, e as duas coisas
que só funcionavam no Windows já têm alternativa por plataforma:

- **Fonte**: Candara só existe no Windows; em qualquer outro SO o app cai pro Roboto
  padrão do Kivy em vez de quebrar ao iniciar (`main.py`, checa `platform == "win"`).
- **Backup**: o diálogo de escolher arquivo usa `tkinter` no desktop (não existe
  runtime Tk no Android) e o seletor nativo via `plyer.filechooser` no Android.

**Buildozer só roda em Linux/macOS** — o toolchain do python-for-android não
suporta Windows, nem dentro da venv. Como a máquina de dev é Windows, o build
acontece no **WSL2 + Ubuntu 22.04**.

**Como o `.apk` é gerado:** `scripts/build-local.sh`, rodado dentro do Ubuntu do
WSL, espelha o que a CI fazia (mesma lista de pacotes, mesmo retry de mirror,
mesmo pin do pip). Passo a passo:

1. Instala o WSL: PowerShell como Admin → `wsl --install -d Ubuntu-22.04`,
   reinicia, cria usuário. (22.04 de propósito: o 24.04 removeu `libtinfo5` /
   `libncurses5-dev` que o p4a precisa.)
2. Clona o repo **dentro do Linux** (não em `/mnt/c` — OneDrive + `.buildozer`
   brigam e fica lento): `git clone … ~/Discipliner && cd ~/Discipliner`.
3. `bash scripts/build-local.sh --setup` — `--setup` só na 1ª vez (instala deps
   do sistema + buildozer, pede sudo). 1º build: 30-60 min (baixa NDK/SDK/recipes,
   ~15 GB em `~/.buildozer`); os seguintes são incrementais, minutos.
4. O `.apk` sai em `~/Discipliner/bin/`. Do Windows, acessa via
   `\\wsl$\Ubuntu-22.04\home\SEU_USUARIO\Discipliner\bin\`.

`--clean` força build do zero; `--release` faz o release (precisa de keystore).

O **GitHub Actions** (`.github/workflows/testes.yml`) não builda mais o APK — só
roda a suíte `test_*.py` a cada push, como auditoria.

Ícone do app é `assets/icon.png` (512x512, logo "D" verde) — usado no
`buildozer.spec` (empacotamento Android) e como ícone da janela no desktop
(`main.py`, `App.icon`). `package.domain` no `buildozer.spec` ainda é só um
placeholder (`com.zazzysaint`) — ajusta se quiser outro.
