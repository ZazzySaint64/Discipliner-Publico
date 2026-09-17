[app]

title = Discipliner
package.name = dailyquest
package.domain = com.zazzysaint

source.dir = .
# SEM "db": o app cria o daily_quest.db sozinho no 1º uso (database.init_db).
# Empacotar um .db do diretório de dev colocava o daily_quest.db LOCAL dele
# dentro do APK — e ele tem a tabela local_session (access_token/refresh_token
# do Supabase, e-mail, dados). Qualquer um que baixe o APK e dê `unzip` lia isso.
source.include_exts = py,kv,png,jpg,gif,ttf
# assets/focum/raw = arte-fonte (folhas de sprite, o mp4 da intro) que os
# scripts gen_focum/gen_intro_gif recortam — não vai pro APK, são ~7 MB mortos.
source.exclude_dirs = venv,__pycache__,.git,docs,scripts,supabase,.github,.idea,.vscode,assets/focum/raw
# .gitignore não vale pro buildozer (empacota do disco, não do git). Barra aqui
# o banco local, os scripts de debug (inclusive o que liga Premium na marra) e
# os testes — nada disso deve ir no APK de release.
source.exclude_patterns = daily_quest.db,daily_quest.db-*,*.sqlite,*.sqlite3,_toggle_premium.py,_debug_premium_sync.py,_debug_*.py,_first_run.py,test_*.py,*.spec,*.md,.env,.env.*

# version.filename/version.regex são pra EXTRAIR a versão de um arquivo — não
# pra dar um nome "bonito" ao apk. Usar os dois junto com "version" fixo dá
# "version.regex and version.filename conflict with version" (buildozer real,
# não é o p4a). "alpha" fica só no título mesmo, versão precisa ser só números.
version = 2.3

# python3==3.11.9 fixo de propósito: sem isso, o python-for-android compila o
# hostpython3 mais novo que existe (3.14 hoje) e o próprio pip quebra dentro
# desse ambiente ("ImportError: cannot import name 'BuildDependencyInstallError'
# from pip._internal.exceptions") — mesmo motivo pelo qual a venv do desktop usa
# 3.12 em vez do 3.14 do sistema (Kivy/toolchain ainda não são testados no 3.14).
# kivy sem pin de versão: pinar uma versão sem receita correspondente no p4a faz
# ele cair pra pip install genérico, que não acha wheel pra Android e quebra.
# hostpython3==3.11.9 também precisa estar pinado: o p4a instalado (mais
# recente) tem hostpython3 com versão padrão própria (3.14.2 hoje) e falha
# com "python3 should have same version as hostpython3" se as duas
# receitas não baterem exatamente (pythonforandroid/recipes/hostpython3/
# __init__.py). Isso é diferente do problema do pip quebrado citado acima
# (esse já foi resolvido usando o python3 do sistema no workflow).
# pillow: share_card.py importa PIL sem guarda de plataforma (é chamado pelo
# main.py logo de cara) — faltando aqui, o app crasha com ModuleNotFoundError
# assim que o Python sobe no Android, bem depois do presplash nativo e antes
# da primeira tela Kivy aparecer (parece "trava na logo" pra quem tá usando).
requirements = python3==3.11.9,hostpython3==3.11.9,kivy,plyer,pillow,certifi

orientation = portrait
fullscreen = 0

# ícone provisório — é a pose "idle" do Focum (assets/focum/focum_idle.png),
# trocar por um ícone quadrado de verdade quando tiver um
icon.filename = %(source.dir)s/assets/icon.png

# Ícone adaptativo (Android 8+). SEM ele o launcher aplica "legacy icon
# treatment" no icon.filename: encolhe o bitmap e centraliza dentro da máscara,
# com margem — o ícone fica visivelmente menor que o dos outros apps.
#
# NÃO usar icon.adaptive_icon_foreground/background aqui: foi testado num APK
# real e o buildozer IGNOROU as duas chaves — o manifesto saiu com
# android:icon="@mipmap/icon" apontando pro PNG puro, sem nenhum
# mipmap-anydpi-v26. O ícone padrão entra pelo android.add_resources lá
# embaixo, igual aos ícones de tier.

# splash nativo do Android, aparece instantâneo enquanto o interpretador
# Python ainda está subindo (a parte mais lenta) — a vinheta com fade
# desenhada em Kivy (main.py, tela "splash") só começa depois disso.
# Imagem ESTÁTICA de propósito (sem android.presplash_lottie): a versão
# animada (LottieAnimationView) exigia tema AppCompat e mesmo depois de
# corrigir isso (android.apptheme) o app continuou crashando nativo
# (SIGSEGV na RenderThread, antes do Kivy rodar) — não valeu a pena insistir
# nela. scripts/gen_presplash.py e assets/presplash.json ficaram no repo sem
# uso, dá pra apagar se não for retomar isso depois.
# NÃO use assets/icon.png aqui: ele é opaco e sangra até a borda (pro
# launcher não aplicar plate branco), o que na tela de carregamento vira
# um quadrado verde. presplash_icon.png é o mesmo desenho COM alfa.
presplash.filename = %(source.dir)s/assets/presplash_icon.png
android.presplash_color = #121212

# SYSTEM_ALERT_WINDOW ("sobrepor a outros apps"): a única isenção que um app
# comum tem pro bloqueio de abrir Activity em 2º plano do Android 10+. É o que
# deixa o serviço abrir a TELA do alarme de missão com o app fechado (ver
# android_alarm.abrir_tela_alarme). Não vem na instalação: o app pede ao
# marcar um alarme. Sem ela, o alarme cai pra notificação.
# USE_FULL_SCREEN_INTENT: é o que faz essa notificação ABRIR a tela do alarme
# sozinha com o celular bloqueado/apagado. Sem declarar, o Android 14 recusa a
# tela cheia calado (appops: "USE_FULL_SCREEN_INTENT ... rejectTime") e o
# alarme tocava sem tela nenhuma — era o "parou de funcionar".
# POST_NOTIFICATIONS: exigida a partir do Android 13 (API 33) pro lembrete
# diário funcionar de verdade nesse Android pra cima
# INTERNET: sem ela o Android bloqueia toda conexão de rede do app (Conta/
# Supabase/Stripe) mesmo com wifi ligado — faltou desde que essas telas
# entraram, porque até então o app era 100% local (SQLite)
# com.google.android.gms.permission.AD_ID: o Google Mobile Ads SDK (ver ads.py)
# usa o Advertising ID a partir do Android 13; sem declarar, a Play acusa
# "Advertising ID declaration" incompleta.
# Serviço do lembrete: processo separado pra a notificação sair com o app
# FECHADO (ver service_reminder.py e android_alarm.py). Vira a classe
# <pacote>.ServiceReminder.
#
# Serviço PERMANENTE (":foreground:sticky"): main.android_alarm.iniciar_servico_lembrete()
# sobe ele quando o app abre (e sempre que passa a existir algum lembrete); daí
# ele fica num laço de 60s e não sai mais. ":sticky" faz o Android recriá-lo se
# matar. O AlarmManager (setAlarmClock exato) é a REDE DE SEGURANÇA: se um
# fabricante mata o serviço apesar do :sticky, o alarme dispara no horário e
# getForegroundService sobe ele de novo.
#
# Chegamos aqui por eliminação, testando no emulador:
#   1. serviço comum -> o Android 8+ RECUSA iniciar com o app morto
#      ("Background start not allowed: service ... startFg?=false")
#   2. foreground curto (shortService) -> funciona, mas depende de o alarme
#      conseguir acordar o serviço a cada disparo
#   3. foreground permanente -> o serviço nunca morre, então não depende disso
#
# PREÇOS, os dois conscientes:
#   * NOTIFICAÇÃO PERMANENTE na barra de status, que o Android exige de todo
#     serviço em foreground e o usuário não pode dispensar.
#   * o tipo declarado passa a ser "specialUse" (ver p4a_hooks.py): serviço
#     permanente não se encaixa em nenhum tipo específico do Android 14, e
#     "specialUse" EXIGE justificativa na revisão da Play Console. Era
#     exatamente o que o "shortService" evitava.
services = reminder:service_reminder.py:foreground

# FOREGROUND_SERVICE + _SPECIAL_USE: exigidas pelo serviço permanente do
# lembrete (ver services acima). A partir do Android 14, startForeground() sem
# o tipo declarado lança MissingForegroundServiceTypeException.
#
# USE_EXACT_ALARM: a partir do Android 14 (API 34) o setAlarmClock() TAMBÉM
# passou a exigir permissão de alarme exato — sem ela dá
# "SecurityException: needs SCHEDULE_EXACT_ALARM or USE_EXACT_ALARM" e o
# lembrete diário nunca é agendado (testado no emulador API 34). USE_EXACT_ALARM
# é concedida na instalação, sem prompt, e a Play permite pra apps cuja função
# central é lembrete/alarme/agenda. PONTO DE TROCA PRA PLAY STORE: se a revisão
# recusar, trocar por SCHEDULE_EXACT_ALARM + pedido em runtime
# (ACTION_REQUEST_SCHEDULE_EXACT_ALARM); android_alarm.agendar() já cai pro
# alarme inexato sozinho quando a permissão não está disponível.
android.permissions = POST_NOTIFICATIONS, INTERNET, FOREGROUND_SERVICE, FOREGROUND_SERVICE_SHORT_SERVICE, USE_EXACT_ALARM, SYSTEM_ALERT_WINDOW, USE_FULL_SCREEN_INTENT, VIBRATE, com.google.android.gms.permission.AD_ID

# --- AdMob (ver ads.py / android_java/AdMobBridge.java) ---
# O Google Mobile Ads SDK e o UMP (consentimento) exigem AndroidX.
android.enable_androidx = True
# SDK de anúncios + SDK de consentimento (UMP). Versões fixas pra o build ser
# reprodutível — subir com cuidado (a Play exige um mínimo recente do ads SDK).
android.gradle_dependencies = com.google.android.gms:play-services-ads:23.6.0, com.google.android.ump:user-messaging-platform:3.1.0
# App ID do AdMob (obrigatório no manifesto, senão o app CRASHA ao iniciar o
# SDK). É o de TESTE do Google enquanto ads.USE_TEST_ADS = True — trocar pelo
# real (do painel do AdMob) junto com os ad unit IDs em ads.py.
android.meta_data = com.google.android.gms.ads.APPLICATION_ID=ca-app-pub-3940256099942544~3347511713

# sem isso, o Kivy não sabe redimensionar/subir a tela quando o teclado
# virtual abre — nos formulários (Conta), botões logo abaixo de um campo de
# texto (ex.: "Já tenho conta", logo abaixo da senha) ficam ESCONDIDOS atrás
# do teclado e viram impossíveis de tocar. "below_target" sobe a área visível
# até o campo focado ficar acima do teclado.
android.softinput_mode = below_target

# ícone do app customizável (recompensa desbloqueável — ver README).
# android_manifest_extra.xml define os <activity-alias> (uma "porta de
# entrada" alternativa pra mesma PythonActivity, cada uma com seu próprio
# ícone); os PNGs coloridos (scripts/gen_alt_icons.py) entram como recursos
# "drawable" de verdade pra esses ícones existirem de fato no APK. Troca em
# tempo real via main.py.set_app_icon (PackageManager, só funciona no
# Android — não dá pra testar isso fora de um build real no celular). Todos
# os aliases começam desabilitados; set_app_icon liga um de cada vez e
# desliga a PythonActivity "de base" junto, pra não sobrar 2 ícones na tela
# inicial ao mesmo tempo.
#
# NÃO usar android.extra_manifest_application_arguments pra isso: essa chave
# injeta dentro da tag de abertura <application ...>, entre atributos — não
# dá pra colocar elemento filho (<activity-alias>) ali, quebra o parse do
# manifest (ManifestMerger2$MergeFailureException, sem detalhe de linha).
# p4a_hooks.py insere android_manifest_extra.xml no lugar certo depois que o
# p4a já gerou o manifest (evento before_apk_assemble).
p4a.hook = p4a_hooks.py
# <intent-filter> do deep link discipliner://login-callback (e-mail de
# confirmação de conta volta pro app, ver deeplink.py) — buildozer insere o
# conteúdo desse arquivo dentro do <activity> da PythonActivity.
android.manifest.intent_filters = android_intent_filters.xml
# O PNG cheio fica em drawable/ (Android 7 e anterior). O XML adaptativo vai
# pra drawable-anydpi-v26/ com o MESMO nome do recurso: a partir do Android 8 o
# sistema prefere esse, e o <activity-alias> continua apontando pro mesmo
# @drawable/ic_<tier>. Sem os adaptativos, os ícones dos aliases sofriam o
# mesmo encolhimento do ícone padrão (ver icon.adaptive_icon_* lá em cima).
android.add_resources = assets/icons_alt/ic_bronze.png:drawable/ic_bronze.png, assets/icons_alt/ic_prata.png:drawable/ic_prata.png, assets/icons_alt/ic_ouro.png:drawable/ic_ouro.png, assets/icons_alt/ic_diamante.png:drawable/ic_diamante.png, assets/icons_alt/ic_tier_bg.png:drawable/ic_tier_bg.png, assets/icons_alt/ic_bronze_fg.png:drawable/ic_bronze_fg.png, assets/icons_alt/ic_prata_fg.png:drawable/ic_prata_fg.png, assets/icons_alt/ic_ouro_fg.png:drawable/ic_ouro_fg.png, assets/icons_alt/ic_diamante_fg.png:drawable/ic_diamante_fg.png, assets/icons_alt/ic_bronze_adaptive.xml:drawable-anydpi-v26/ic_bronze.xml, assets/icons_alt/ic_prata_adaptive.xml:drawable-anydpi-v26/ic_prata.xml, assets/icons_alt/ic_ouro_adaptive.xml:drawable-anydpi-v26/ic_ouro.xml, assets/icons_alt/ic_diamante_adaptive.xml:drawable-anydpi-v26/ic_diamante.xml, assets/icon_fg.png:drawable/icon_fg.png, assets/icon_adaptive.xml:mipmap-anydpi-v26/icon.xml, assets/focum/focum_alarm.png:drawable/focum_alarm.png

android.api = 34
android.minapi = 21
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
# recipe local que corrige o build do python3 pro Android (ver p4a-recipes/python3)
p4a.local_recipes = p4a-recipes
# False: o daily_quest.db guarda access_token/refresh_token do Supabase em
# texto puro. Com allow_backup=True, `adb backup` (não precisa de root, só
# depuração USB) extrai os dados privados do app — inclusive esses tokens,
# o que dá pra tomar a conta. O usuário não perde nada: a restauração de
# dados entre aparelhos já é o backup na nuvem explícito (ver backup.py).
android.allow_backup = False
# aceita a licença do SDK sem prompt interativo — necessário rodando em CI
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
