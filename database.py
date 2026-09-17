"""Camada de persistência: SQLite puro (stdlib), sem ORM."""
import os
import sqlite3
from pathlib import Path

from plataforma import IS_ANDROID

# No Android, __file__ fica dentro do .apk (extraído pelo p4a num lugar que
# não é garantidamente gravável) — abrir o sqlite3.connect ali crasha o app
# na inicialização (nem o ícone chega a aparecer, cai antes do primeiro
# frame). ANDROID_PRIVATE é o diretório privado de verdade do app
# (Context.getFilesDir() do Android), setado pelo bootstrap do p4a antes do
# Python nem iniciar — ver PythonActivity.java do bootstrap sdl2.
if IS_ANDROID:
    DB_PATH = Path(os.environ["ANDROID_PRIVATE"]) / "daily_quest.db"
else:
    DB_PATH = Path(__file__).parent / "daily_quest.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Bytes indecodificáveis numa coluna TEXT (o SQLite não valida encoding, e
    # um backup de terceiro pode trazer CAST(x'80' AS TEXT)) fariam o driver
    # levantar OperationalError já no fetchone() — ANTES de qualquer
    # saneamento nosso, inclusive o de settings._cycle_values. Como
    # settings.get_settings() é atravessada por todo consumidor e roda no
    # build(), isso derrubava o app em TODA abertura: o "trava pra sempre" do
    # achado F12, por um caminho que não dava pra fechar lá em cima.
    # errors="replace" troca o byte inválido por U+FFFD em vez de estourar;
    # texto válido decodifica idêntico, então nada mais muda.
    conn.text_factory = lambda b: b.decode("utf-8", "replace")
    # WAL: leitor não bloqueia escritor (o app abre conexão em threads — carga
    # da conta, deep link — enquanto a UI lê). journal_mode gruda no arquivo,
    # rodar todo connect é ~no-op depois da 1ª vez. synchronous=NORMAL é por
    # conexão: seguro com WAL (só perde as últimas transações num crash de SO,
    # não corrompe) e corta o fsync de cada marcação de missão.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    # espera até 3s por um lock em vez de estourar SQLITE_BUSY na hora. O app e
    # o serviço do lembrete (service_reminder.py) são PROCESSOS diferentes e
    # disputam a coluna reminders_fired via BEGIN IMMEDIATE (ver
    # settings.claim_reminder_fired) — sem isso, o perdedor da corrida tomava
    # "database is locked" em vez de esperar sua vez.
    conn.execute("PRAGMA busy_timeout=3000")
    return conn


def init_db():
    conn = get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS missions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            periodicity TEXT NOT NULL CHECK(periodicity IN ('diaria', 'semanal', 'mensal')),
            difficulty TEXT NOT NULL CHECK(difficulty IN ('facil', 'media', 'dificil')),
            points INTEGER NOT NULL,
            last_completed_date TEXT,
            custom_days TEXT NOT NULL DEFAULT '',
            challenge_id TEXT NOT NULL DEFAULT '',
            suggestion_id TEXT NOT NULL DEFAULT '',
            follow_cycle INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS completions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mission_id INTEGER NOT NULL,
            mission_name TEXT NOT NULL,
            date TEXT NOT NULL,
            points INTEGER NOT NULL,
            obs TEXT DEFAULT '',
            periodicity TEXT NOT NULL DEFAULT 'diaria'
        )
    """)
    # Loja de Recompensas (ver rewards.py) — o usuário define suas próprias
    # recompensas e troca pontos ganhos por elas. custom_rewards é a
    # definição (reaproveitável, resgata quantas vezes quiser desde que
    # tenha pontos); reward_redemptions é o histórico de resgates, com
    # nome/custo GRAVADOS no momento (mesmo padrão de completions.mission_name
    # — sobrevive se a recompensa for editada ou apagada depois).
    conn.execute("""
        CREATE TABLE IF NOT EXISTS custom_rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            cost INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reward_redemptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reward_id INTEGER NOT NULL,
            reward_name TEXT NOT NULL,
            cost INTEGER NOT NULL,
            redeemed_at TEXT NOT NULL
        )
    """)
    # cache local da sessão do Supabase Auth (quem cuida da conta de verdade
    # agora é a nuvem — ver account.py/supabase_client.py). Só 1 linha, igual
    # app_settings: este app é single-user por aparelho, não multi-perfil.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS local_session (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            user_id TEXT,
            email TEXT,
            name TEXT,
            access_token TEXT,
            refresh_token TEXT,
            expires_at INTEGER
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            language TEXT NOT NULL DEFAULT 'pt',
            dark_mode INTEGER NOT NULL DEFAULT 1
        )
    """)
    # tabela antiga de conta local (senha com hash) — a conta virou de verdade
    # no Supabase, essa aqui não serve mais pra nada (não recria e não escreve
    # de novo, só derruba se ainda existir de uma instalação anterior)
    conn.execute("DROP TABLE IF EXISTS account")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS streak_freezes (
            month TEXT PRIMARY KEY,
            frozen_date TEXT
        )
    """)
    conn.commit()

    # streak_freezes: "month" deixou de poder ser chave única — Premium ganha
    # mais de 1 congelamento por mês (missions.PREMIUM_FREEZE_CAP), e SQLite
    # não altera uma PRIMARY KEY existente com ALTER TABLE, então reconstrói
    # a tabela se ainda estiver no formato antigo de 1 linha por mês.
    freeze_cols = {row["name"]: row for row in conn.execute("PRAGMA table_info(streak_freezes)")}
    if freeze_cols.get("month") and freeze_cols["month"]["pk"] == 1:
        conn.execute("ALTER TABLE streak_freezes RENAME TO streak_freezes_old")
        conn.execute("""
            CREATE TABLE streak_freezes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                month TEXT NOT NULL,
                frozen_date TEXT
            )
        """)
        conn.execute("INSERT INTO streak_freezes (month, frozen_date) SELECT month, frozen_date FROM streak_freezes_old")
        conn.execute("DROP TABLE streak_freezes_old")
        conn.commit()

    # migração leve: colunas novas em tabelas que já existiam antes delas serem
    # adicionadas (ALTER TABLE ADD COLUMN não tem "IF NOT EXISTS" no SQLite)
    existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(app_settings)")}
    for column, ddl in [
        ("accent_theme", "ALTER TABLE app_settings ADD COLUMN accent_theme TEXT NOT NULL DEFAULT 'floresta'"),
        ("reminder_enabled", "ALTER TABLE app_settings ADD COLUMN reminder_enabled INTEGER NOT NULL DEFAULT 0"),
        ("reminder_time", "ALTER TABLE app_settings ADD COLUMN reminder_time TEXT NOT NULL DEFAULT '20:00'"),
        ("best_streak", "ALTER TABLE app_settings ADD COLUMN best_streak INTEGER NOT NULL DEFAULT 0"),
        ("best_streak_semanal", "ALTER TABLE app_settings ADD COLUMN best_streak_semanal INTEGER NOT NULL DEFAULT 0"),
        ("best_streak_mensal", "ALTER TABLE app_settings ADD COLUMN best_streak_mensal INTEGER NOT NULL DEFAULT 0"),
        ("onboarding_done", "ALTER TABLE app_settings ADD COLUMN onboarding_done INTEGER NOT NULL DEFAULT 0"),
        ("profile_avatar", "ALTER TABLE app_settings ADD COLUMN profile_avatar TEXT NOT NULL DEFAULT 'idle'"),
        # premium (compra única, ver README > Monetização) — is_premium é local
        # por enquanto (sem Play Billing real ainda); quando existir, passa a
        # ser confirmado contra a tabela "purchases" do Supabase, não só local
        ("is_premium", "ALTER TABLE app_settings ADD COLUMN is_premium INTEGER NOT NULL DEFAULT 0"),
        ("no_penalty_mode", "ALTER TABLE app_settings ADD COLUMN no_penalty_mode INTEGER NOT NULL DEFAULT 0"),
        ("custom_accent_hue", "ALTER TABLE app_settings ADD COLUMN custom_accent_hue REAL NOT NULL DEFAULT 100"),
        ("custom_accent_sat", "ALTER TABLE app_settings ADD COLUMN custom_accent_sat REAL NOT NULL DEFAULT 55"),
        # emblema (id de achievements.DEFINITIONS) escolhido pra aparecer como
        # título ao lado do avatar no cabeçalho — "" = nenhum equipado
        ("equipped_title", "ALTER TABLE app_settings ADD COLUMN equipped_title TEXT NOT NULL DEFAULT ''"),
        ("profile_frame", "ALTER TABLE app_settings ADD COLUMN profile_frame TEXT NOT NULL DEFAULT 'none'"),
        ("app_icon", "ALTER TABLE app_settings ADD COLUMN app_icon TEXT NOT NULL DEFAULT 'none'"),
        # banner de fundo do cabeçalho (ver banners.py) — preset grátis ou
        # "custom" (Premium: matiz/saturação/estilo abaixo)
        ("profile_banner", "ALTER TABLE app_settings ADD COLUMN profile_banner TEXT NOT NULL DEFAULT 'none'"),
        ("custom_banner_hue", "ALTER TABLE app_settings ADD COLUMN custom_banner_hue REAL NOT NULL DEFAULT 210"),
        ("custom_banner_sat", "ALTER TABLE app_settings ADD COLUMN custom_banner_sat REAL NOT NULL DEFAULT 45"),
        ("custom_banner_pattern", "ALTER TABLE app_settings ADD COLUMN custom_banner_pattern TEXT NOT NULL DEFAULT 'solid'"),
        # ciclo pessoal (escalas rotativas — 12x36, 24x48, etc.), ver
        # missions._cycle_off_today. off_days: CSV de índices 0..(length-1)
        # que são folga. anchor_date: ISO, "dia 0" do ciclo.
        ("cycle_enabled", "ALTER TABLE app_settings ADD COLUMN cycle_enabled INTEGER NOT NULL DEFAULT 0"),
        ("cycle_length", "ALTER TABLE app_settings ADD COLUMN cycle_length INTEGER NOT NULL DEFAULT 7"),
        ("cycle_off_days", "ALTER TABLE app_settings ADD COLUMN cycle_off_days TEXT NOT NULL DEFAULT ''"),
        ("cycle_anchor_date", "ALTER TABLE app_settings ADD COLUMN cycle_anchor_date TEXT NOT NULL DEFAULT ''"),
        # "" = usa a pose do Focum (profile_avatar); senão, caminho de uma
        # foto enviada pelo usuário (Premium, ver main.py > upload_profile_photo)
        ("profile_photo_path", "ALTER TABLE app_settings ADD COLUMN profile_photo_path TEXT NOT NULL DEFAULT ''"),
        # teto diário do intersticial de anúncio (só Android/grátis, ver ads.py)
        ("ad_interstitial_count", "ALTER TABLE app_settings ADD COLUMN ad_interstitial_count INTEGER NOT NULL DEFAULT 0"),
        ("ad_interstitial_date", "ALTER TABLE app_settings ADD COLUMN ad_interstitial_date TEXT NOT NULL DEFAULT ''"),
        # id aleatório gerado no 1º boot pro relato de crash (ver crash_reporter.py).
        # NÃO é user_id — não liga a nenhuma conta, só conta aparelhos distintos.
        ("install_id", "ALTER TABLE app_settings ADD COLUMN install_id TEXT NOT NULL DEFAULT ''"),
        # JSON {"daily": "YYYY-MM-DD", "m<id>": "YYYY-MM-DD"} — de que dia é o
        # último lembrete já disparado. Antes isso só existia em memória, então
        # cada vez que o Android matava e reabria o app o lembrete do dia
        # disparava DE NOVO, em qualquer horário (ver main.py > _check_reminder).
        ("reminders_fired", "ALTER TABLE app_settings ADD COLUMN reminders_fired TEXT NOT NULL DEFAULT ''"),
        # seção "Recompensas de Nível" da aba Missões aberta/recolhida
        ("level_rewards_open", "ALTER TABLE app_settings ADD COLUMN level_rewards_open INTEGER NOT NULL DEFAULT 1"),
        # e-mail do cadastro que ESTE aparelho pediu pra confirmar e ainda não
        # confirmou. "" = nenhum. É a prova de que o próprio app começou o
        # fluxo: o deep link de confirmação (discipliner://login-callback, que
        # QUALQUER app/página pode disparar) só é aceito se trouxer um token
        # desse e-mail — ver account.complete_deeplink_login.
        ("pending_signup_email", "ALTER TABLE app_settings ADD COLUMN pending_signup_email TEXT NOT NULL DEFAULT ''"),
        # mesma ideia pro link de redefinir senha (discipliner://reset-password):
        # e-mail que ESTE aparelho pediu pra redefinir. Sem ele, qualquer app
        # poderia abrir a tela de senha nova com o token da conta que quisesse
        # — ver account.validar_link_reset.
        ("pending_reset_email", "ALTER TABLE app_settings ADD COLUMN pending_reset_email TEXT NOT NULL DEFAULT ''"),
        # ISO do último backup automático na nuvem ("" = nunca). O backup deixou
        # de ser botão e passou a rodar sozinho a cada AUTO_CLOUD_BACKUP_HORAS
        # (ver main._auto_backup_nuvem).
        ("last_cloud_backup", "ALTER TABLE app_settings ADD COLUMN last_cloud_backup TEXT NOT NULL DEFAULT ''"),
        # JSON {"ultima": "YYYY-MM-DD", "enviados": n} — quantos avisos de
        # reconquista já saíram na ausência atual (ver reconquista.py)
        ("winback_state", "ALTER TABLE app_settings ADD COLUMN winback_state TEXT NOT NULL DEFAULT ''"),
    ]:
        if column not in existing_cols:
            conn.execute(ddl)

    existing_mission_cols = {row["name"] for row in conn.execute("PRAGMA table_info(missions)")}
    if "custom_days" not in existing_mission_cols:
        conn.execute("ALTER TABLE missions ADD COLUMN custom_days TEXT NOT NULL DEFAULT ''")
    if "instructions" not in existing_mission_cols:
        # texto livre (ex.: exercícios do treino) — mostrado na aba de detalhes da missão
        conn.execute("ALTER TABLE missions ADD COLUMN instructions TEXT NOT NULL DEFAULT ''")
    if "reminder_time" not in existing_mission_cols:
        # "" = sem lembrete; "HH:MM" = recurso Premium (ver README > Monetização)
        conn.execute("ALTER TABLE missions ADD COLUMN reminder_time TEXT NOT NULL DEFAULT ''")
    if "challenge_id" not in existing_mission_cols:
        # "" = missão comum; id de challenges.CHALLENGES = ganha CHALLENGE_MULTIPLIER
        # ao concluir (ver missions.complete_mission) — só existe pra incentivar
        # quem pega um Desafio a seguir fazendo aquelas missões
        conn.execute("ALTER TABLE missions ADD COLUMN challenge_id TEXT NOT NULL DEFAULT ''")
    if "suggestion_id" not in existing_mission_cols:
        # "" = missão criada na mão; id de mission_suggestions.SUGGESTIONS =
        # veio do popup de sugestões — só existe pra saber quais sugestões já
        # foram adicionadas (mostra "X" em vez de "+" nesse caso, ver main.py)
        conn.execute("ALTER TABLE missions ADD COLUMN suggestion_id TEXT NOT NULL DEFAULT ''")
    if "follow_cycle" not in existing_mission_cols:
        # 1 = agendada "nos meus dias de folga" (ciclo pessoal em app_settings,
        # ver missions._cycle_off_today) em vez de dias fixos da semana
        conn.execute("ALTER TABLE missions ADD COLUMN follow_cycle INTEGER NOT NULL DEFAULT 0")

    existing_completion_cols = {row["name"] for row in conn.execute("PRAGMA table_info(completions)")}
    if "periodicity" not in existing_completion_cols:
        conn.execute("ALTER TABLE completions ADD COLUMN periodicity TEXT NOT NULL DEFAULT 'diaria'")
    # garante que a linha única de preferências já existe, com os defaults das
    # colunas — assim os setters de settings.py podem sempre fazer UPDATE direto
    conn.execute("INSERT OR IGNORE INTO app_settings (id) VALUES (1)")

    # índices em completions (tabela quente — cresce ~1 linha/missão/dia). Sem
    # eles todo refresh de tela era full scan; com histórico de meses, pesa.
    #  - periodicity: current_streak() filtra por ela
    #  - date: gráficos (BETWEEN/LIKE + GROUP BY date) e histórico (ORDER BY date)
    #  - (mission_id, date): DELETE do "desmarcar missão"
    conn.execute("CREATE INDEX IF NOT EXISTS idx_completions_periodicity ON completions(periodicity)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_completions_date ON completions(date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_completions_mission_date ON completions(mission_id, date)")
    conn.commit()
    conn.close()


def history(limit=100):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM completions ORDER BY date DESC, id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return rows
