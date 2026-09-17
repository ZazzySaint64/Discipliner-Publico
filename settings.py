"""Preferências do app (idioma, tema, lembrete, sequência recorde) — persistem
entre execuções. Separado de account.py de propósito: são preferências do APP,
existem mesmo sem conta criada.

Cada setter faz UPDATE (não INSERT OR REPLACE da linha inteira) — a linha única
(id=1) já existe garantida por database.init_db(), então um UPDATE nunca perde
as outras colunas."""
import json
from datetime import date, timedelta

import database as db
import i18n

DEFAULTS = {
    "language": i18n.DEFAULT_LANGUAGE,
    "dark_mode": True,
    "accent_theme": "floresta",
    "reminder_enabled": False,
    "reminder_time": "20:00",
    "best_streak": 0,
    "best_streak_semanal": 0,
    "best_streak_mensal": 0,
    "onboarding_done": False,
    "profile_avatar": "idle",
    "is_premium": False,
    "no_penalty_mode": False,
    "custom_accent_hue": 100,
    "custom_accent_sat": 55,
    "equipped_title": "",
    "profile_frame": "none",
    "app_icon": "none",  # "none" = ícone padrão; senão um dos ids de mascot.FRAMES (mesmos tiers)
    "profile_photo_path": "",  # "" = usa a pose do Focum (profile_avatar); senão, foto enviada (Premium)
    # banner de fundo do cabeçalho (ver banners.py) — "none"/preset/"custom"
    "profile_banner": "none",
    "custom_banner_hue": 210,   # roda HSV do banner personalizado (Premium)
    "custom_banner_sat": 45,
    "custom_banner_pattern": "solid",  # estilo do banner personalizado (banners.PATTERNS)
    # ciclo pessoal (escalas rotativas — 12x36, 24x48...), ver missions._cycle_off_today
    "cycle_enabled": False,
    "cycle_length": 7,
    "cycle_off_days": "",
    "cycle_anchor_date": "",
    # anúncios (só Android, só grátis): teto diário do intersticial — ver ads.py
    "ad_interstitial_count": 0,
    "ad_interstitial_date": "",  # "YYYY-MM-DD" do dia a que o count se refere
    "install_id": "",  # UUID aleatório do 1º boot, pro relato de crash (ver crash_reporter.py)
    "reminders_fired": "",  # JSON {"daily"/"m<id>": "YYYY-MM-DD"} — ver get_reminders_fired
    "level_rewards_open": True,
    # e-mail do cadastro aguardando confirmação neste aparelho ("" = nenhum) —
    # ver account.sign_up / account.complete_deeplink_login
    "pending_signup_email": "",
    "pending_reset_email": "",
    "last_cloud_backup": "",  # ISO do último backup automático — ver main._auto_backup_nuvem
    "winback_state": "",  # JSON {"ultima", "enviados"} — ver reconquista.py
}

# nome da coluna no banco pra cada periodicidade — "diaria" reusa a coluna
# antiga "best_streak" (existia antes da sequência virar por periodicidade)
BEST_STREAK_COLUMN = {"diaria": "best_streak", "semanal": "best_streak_semanal", "mensal": "best_streak_mensal"}

# faixa de tamanho de ciclo que a UI oferece (main.cycle_length_values monta
# range(2, 16)). Fora dela, o valor não veio deste app — ver _cycle_values.
CYCLE_LENGTH_MIN = 2
CYCLE_LENGTH_MAX = 15


def _cycle_values(row):
    """Sanea os campos do ciclo pessoal na leitura, inclusive o liga/desliga.

    Quem lê faz int() / date.fromisoformat() direto neles (missions._cycle_off_today,
    main._init_work_cycle_ui) e o banco nem sempre foi escrito por aqui — o
    usuário pode ter restaurado um arquivo de backup de terceiro
    (backup.import_from só confere os nomes das tabelas). Valor guardado
    inválido vira o DEFAULTS em vez de estourar no chamador."""
    enabled = bool(row["cycle_enabled"])
    try:
        length = int(row["cycle_length"])
    except (TypeError, ValueError, OverflowError):
        # OverflowError não é subclasse de ValueError: cycle_length gravado
        # como REAL infinito (9e999) faz int() estourar por aqui, e sem isso a
        # exceção escapava do get_settings() — que TODO consumidor atravessa,
        # então o app deixava de subir em vez de só ignorar o ciclo.
        length = 0

    if not CYCLE_LENGTH_MIN <= length <= CYCLE_LENGTH_MAX:
        # Fora da faixa que a própria UI oferece (main.cycle_length_values):
        # é configuração que este app não escreveu. DESLIGA o ciclo em vez de
        # trocar por um tamanho qualquer — só pôr o padrão faria missões
        # "follow_cycle" passarem a ser agendadas por um ciclo que o usuário
        # nunca escolheu. Fechar só o piso não bastava: um tamanho enorme
        # (1099511627776) passava e travava o app no range() que monta as
        # bolinhas de dia (main._rebuild_cycle_day_toggles), que é justamente
        # o "trava pra sempre" que este achado descreve.
        enabled = False
        length = DEFAULTS["cycle_length"]

    off_days = str(row["cycle_off_days"] or "")
    # teto de tamanho ANTES de qualquer parse: com no máximo CYCLE_LENGTH_MAX
    # dias isso nunca passa de ~40 caracteres. get_settings() é chamada por
    # missão renderizada (missions.is_scheduled_today), e sem o teto um campo
    # de megabytes vindo de backup hostil viraria um parse O(n) a cada chamada.
    # lixo em off_days/anchor DESLIGA o ciclo, igual ao tamanho inválido acima
    # — só trocar pelo padrão deixava missões follow_cycle escondidas por um
    # ciclo que o usuário nunca escolheu
    if len(off_days) > 64:
        off_days, enabled = DEFAULTS["cycle_off_days"], False
    else:
        try:
            [int(d) for d in off_days.split(",") if d]
        except ValueError:
            off_days, enabled = DEFAULTS["cycle_off_days"], False

    anchor = str(row["cycle_anchor_date"] or "")
    if anchor:
        try:
            date.fromisoformat(anchor)
        except ValueError:
            anchor, enabled = DEFAULTS["cycle_anchor_date"], False
    return enabled, length, off_days, anchor


def get_settings():
    conn = db.get_connection()
    row = conn.execute("SELECT * FROM app_settings WHERE id = 1").fetchone()
    conn.close()
    if row is None:
        return dict(DEFAULTS)
    cycle_enabled, cycle_length, cycle_off_days, cycle_anchor_date = _cycle_values(row)
    return {
        "language": row["language"],
        "dark_mode": bool(row["dark_mode"]),
        "accent_theme": row["accent_theme"],
        "reminder_enabled": bool(row["reminder_enabled"]),
        "reminder_time": row["reminder_time"],
        "best_streak": row["best_streak"],
        "best_streak_semanal": row["best_streak_semanal"],
        "best_streak_mensal": row["best_streak_mensal"],
        "onboarding_done": bool(row["onboarding_done"]),
        "profile_avatar": row["profile_avatar"],
        "is_premium": bool(row["is_premium"]),
        "no_penalty_mode": bool(row["no_penalty_mode"]),
        "custom_accent_hue": row["custom_accent_hue"],
        "custom_accent_sat": row["custom_accent_sat"],
        "equipped_title": row["equipped_title"],
        "profile_frame": row["profile_frame"],
        "app_icon": row["app_icon"],
        "profile_banner": row["profile_banner"],
        "custom_banner_hue": row["custom_banner_hue"],
        "custom_banner_sat": row["custom_banner_sat"],
        "custom_banner_pattern": row["custom_banner_pattern"],
        "cycle_enabled": cycle_enabled,  # saneado junto do tamanho (ver _cycle_values)
        "cycle_length": cycle_length,
        "cycle_off_days": cycle_off_days,
        "cycle_anchor_date": cycle_anchor_date,
        "profile_photo_path": row["profile_photo_path"],
        "ad_interstitial_count": row["ad_interstitial_count"],
        "ad_interstitial_date": row["ad_interstitial_date"],
        "install_id": row["install_id"],
        "reminders_fired": row["reminders_fired"],
        "level_rewards_open": bool(row["level_rewards_open"]),
        "pending_signup_email": row["pending_signup_email"],
        "pending_reset_email": row["pending_reset_email"],
        "last_cloud_backup": row["last_cloud_backup"],
        "winback_state": row["winback_state"],
    }


def _set(column, value):
    # o nome da coluna entra na SQL por interpolação (não dá pra parametrizar
    # identificador) — hoje todo chamador passa literal fixo, mas trava num
    # allowlist pra isso nunca virar injeção se algum chamador futuro passar
    # algo dinâmico. DEFAULTS tem exatamente os nomes de coluna do app_settings.
    if column not in DEFAULTS:
        raise ValueError(f"coluna de settings desconhecida: {column!r}")
    conn = db.get_connection()
    conn.execute(f"UPDATE app_settings SET {column} = ? WHERE id = 1", (value,))
    conn.commit()
    conn.close()


def set_winback_state(value):
    _set("winback_state", value)


def set_language(lang):
    _set("language", lang)


def set_dark_mode(enabled):
    _set("dark_mode", int(enabled))


def set_accent_theme(theme):
    _set("accent_theme", theme)


def set_reminder(enabled, time_str):
    conn = db.get_connection()
    conn.execute(
        "UPDATE app_settings SET reminder_enabled = ?, reminder_time = ? WHERE id = 1",
        (int(enabled), time_str),
    )
    conn.commit()
    conn.close()


def set_best_streak(periodicity, value):
    _set(BEST_STREAK_COLUMN[periodicity], value)


def set_onboarding_done():
    _set("onboarding_done", 1)


def set_profile_avatar(avatar_id):
    _set("profile_avatar", avatar_id)


def get_reminders_fired():
    """{"daily": "YYYY-MM-DD", "m3": "YYYY-MM-DD"} — de que dia é o último
    lembrete já disparado, por assunto. Persiste em disco de propósito: o
    Android mata o app o tempo todo, e enquanto isso era só um dict em memória
    o lembrete do dia voltava a disparar a cada reabertura (ver main.py >
    _check_reminder). Coluna corrompida/legada = começa do zero."""
    raw = get_settings()["reminders_fired"]
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def set_reminder_fired(key, day_iso):
    fired = get_reminders_fired()
    fired[key] = day_iso
    # só o dia de hoje importa — poda o resto pra coluna não crescer sem fim
    fired = {k: v for k, v in fired.items() if v == day_iso}
    _set("reminders_fired", json.dumps(fired))


def claim_reminder_fired(key, day_iso):
    """Marca `key` como disparado em `day_iso` SÓ SE ainda não estava, de forma
    ATÔMICA. Devolve True pra quem conseguiu a marca (esse deve notificar) e
    False pra todo o resto.

    O app (main._check_reminder) e o serviço (service_reminder) são PROCESSOS
    diferentes: o threading.Lock do app não vale entre eles. Sem esta trava, os
    dois liam get_reminders_fired() como "não disparou" e o lembrete saía em
    dobro. BEGIN IMMEDIATE pega o lock de escrita na hora; o outro processo
    espera (PRAGMA busy_timeout no database.get_connection) e aí lê a marca já
    gravada."""
    conn = db.get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT reminders_fired FROM app_settings WHERE id = 1").fetchone()
        raw = row["reminders_fired"] if row else ""
        try:
            fired = json.loads(raw) if raw else {}
            if not isinstance(fired, dict):
                fired = {}
        except ValueError:
            fired = {}
        if fired.get(key) == day_iso:
            conn.rollback()
            return False
        fired[key] = day_iso
        fired = {k: v for k, v in fired.items() if v == day_iso}  # poda dias velhos
        conn.execute("UPDATE app_settings SET reminders_fired = ? WHERE id = 1",
                     (json.dumps(fired),))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def set_level_rewards_open(is_open):
    _set("level_rewards_open", int(is_open))


def set_profile_photo_path(path):
    """"" = volta a usar a pose do Focum (profile_avatar) — ver
    main.py > upload_profile_photo / set_profile_avatar."""
    _set("profile_photo_path", path)


def set_premium(enabled):
    _set("is_premium", int(enabled))


def set_no_penalty_mode(enabled):
    _set("no_penalty_mode", int(enabled))


def set_equipped_title(badge_id):
    _set("equipped_title", badge_id)


def set_profile_frame(frame_id):
    _set("profile_frame", frame_id)


def set_app_icon(icon_id):
    _set("app_icon", icon_id)


def set_profile_banner(banner_id):
    _set("profile_banner", banner_id)


def set_custom_banner(hue, sat, pattern):
    conn = db.get_connection()
    conn.execute(
        "UPDATE app_settings SET custom_banner_hue = ?, custom_banner_sat = ?, "
        "custom_banner_pattern = ? WHERE id = 1",
        (float(hue), float(sat), pattern),
    )
    conn.commit()
    conn.close()


def set_work_cycle(enabled, length, off_days, today_cycle_day):
    """today_cycle_day: resposta de "hoje é o dia ? do seu ciclo" (1..length)
    — a data-âncora é recalculada a partir de hoje toda vez que o ciclo é
    salvo (sem "recalibração" separada, ver spec do ciclo pessoal)."""
    anchor = (date.today() - timedelta(days=today_cycle_day - 1)).isoformat()
    conn = db.get_connection()
    conn.execute(
        "UPDATE app_settings SET cycle_enabled = ?, cycle_length = ?, cycle_off_days = ?, "
        "cycle_anchor_date = ? WHERE id = 1",
        (int(enabled), length, off_days, anchor),
    )
    conn.commit()
    conn.close()


def set_custom_accent(hue, sat):
    conn = db.get_connection()
    conn.execute(
        "UPDATE app_settings SET custom_accent_hue = ?, custom_accent_sat = ? WHERE id = 1",
        (hue, sat),
    )
    conn.commit()
    conn.close()


def set_install_id(value):
    _set("install_id", value)


def set_last_cloud_backup(iso):
    """Carimbo do último backup automático na nuvem (ver main._auto_backup_nuvem)."""
    _set("last_cloud_backup", iso)


def set_pending_signup_email(email):
    """E-mail do cadastro que este aparelho acabou de pedir pra confirmar, ""
    pra limpar. Único caso em que o deep link de confirmação pode logar
    alguém — ver account.sign_up / account.complete_deeplink_login."""
    _set("pending_signup_email", email)


def set_pending_reset_email(email):
    """E-mail que este aparelho pediu pra redefinir a senha, "" pra limpar.
    Único caso em que o link discipliner://reset-password é aceito — ver
    account.request_password_reset / account.validar_link_reset."""
    _set("pending_reset_email", email)


def set_ad_interstitial(count, date_str):
    """Teto diário do intersticial (ver ads.py). date_str = dia a que o count
    se refere; quando o dia vira, ads.py passa count=1 com a data nova."""
    conn = db.get_connection()
    conn.execute(
        "UPDATE app_settings SET ad_interstitial_count = ?, ad_interstitial_date = ? WHERE id = 1",
        (count, date_str),
    )
    conn.commit()
    conn.close()
