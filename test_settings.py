"""Self-check: python test_settings.py (não precisa do Kivy, só sqlite)."""
import tempfile
from pathlib import Path

import database as db


def run():
    with tempfile.TemporaryDirectory() as tmp:
        db.DB_PATH = Path(tmp) / "test.db"
        db.init_db()
        import settings

        # instalação nova: onboarding ainda não visto, modo escuro já é o padrão
        prefs = settings.get_settings()
        assert prefs["onboarding_done"] is False, "onboarding deveria começar não concluído"
        assert prefs["dark_mode"] is True, "modo escuro deveria ser o padrão de instalação nova"

        settings.set_onboarding_done()
        assert settings.get_settings()["onboarding_done"] is True, "deveria persistir depois de marcado"

        # avatar de perfil é preferência do app (settings), não da conta — funciona pra convidado também
        assert prefs["profile_avatar"] == "idle", "avatar padrão deveria ser 'idle'"
        settings.set_profile_avatar("celebrating")
        assert settings.get_settings()["profile_avatar"] == "celebrating", "deveria persistir depois de trocado"

        # Premium (ver README > Monetização): tudo desligado por padrão numa instalação nova
        assert prefs["is_premium"] is False
        assert prefs["no_penalty_mode"] is False
        settings.set_premium(True)
        settings.set_no_penalty_mode(True)
        settings.set_custom_accent(210, 70)
        after = settings.get_settings()
        assert after["is_premium"] is True and after["no_penalty_mode"] is True
        assert after["custom_accent_hue"] == 210 and after["custom_accent_sat"] == 70

        # título equipado (emblema ao lado do avatar): "" por padrão, persiste ao trocar
        assert prefs["equipped_title"] == "", "nenhum título equipado numa instalação nova"
        settings.set_equipped_title("streak_7")
        assert settings.get_settings()["equipped_title"] == "streak_7", "deveria persistir depois de equipado"
        settings.set_equipped_title("")
        assert settings.get_settings()["equipped_title"] == "", "deveria persistir depois de desequipado"

        # moldura de avatar e ícone do app (recompensas): "none" por padrão, persistem ao trocar
        assert prefs["profile_frame"] == "none" and prefs["app_icon"] == "none"
        settings.set_profile_frame("ouro")
        settings.set_app_icon("diamante")
        after2 = settings.get_settings()
        assert after2["profile_frame"] == "ouro" and after2["app_icon"] == "diamante"

        # foto de perfil enviada (Premium): "" por padrão, persiste ao trocar
        assert prefs["profile_photo_path"] == ""
        settings.set_profile_photo_path("/tmp/foto.png")
        assert settings.get_settings()["profile_photo_path"] == "/tmp/foto.png"
        settings.set_profile_photo_path("")  # voltar a usar a pose do Focum
        assert settings.get_settings()["profile_photo_path"] == ""

        # ciclo pessoal (escalas rotativas): desligado por padrão, e a data-âncora
        # é derivada de "hoje é o dia N" — não é passada direto
        assert prefs["cycle_enabled"] is False and prefs["cycle_length"] == 7
        from datetime import date, timedelta
        settings.set_work_cycle(enabled=True, length=2, off_days="1", today_cycle_day=2)
        after3 = settings.get_settings()
        assert after3["cycle_enabled"] is True and after3["cycle_length"] == 2
        assert after3["cycle_off_days"] == "1"
        expected_anchor = (date.today() - timedelta(days=1)).isoformat()  # dia 2 -> âncora foi ontem
        assert after3["cycle_anchor_date"] == expected_anchor, after3["cycle_anchor_date"]

        # banco restaurado de um backup de terceiro pode trazer lixo nos campos
        # do ciclo — get_settings sanea na leitura pra ninguém estourar no
        # int() / date.fromisoformat() lá na frente (crash no boot, ver
        # missions._cycle_off_today e main._init_work_cycle_ui)
        conn = db.get_connection()
        conn.execute(
            "UPDATE app_settings SET cycle_enabled = 1, cycle_length = ?, cycle_off_days = ?, "
            "cycle_anchor_date = ? WHERE id = 1",
            ("nao-e-numero", "x", "ontem"),
        )
        conn.commit()
        conn.close()
        sujo = settings.get_settings()
        assert sujo["cycle_length"] == settings.DEFAULTS["cycle_length"], sujo["cycle_length"]
        assert sujo["cycle_off_days"] == "", sujo["cycle_off_days"]
        assert sujo["cycle_anchor_date"] == "", sujo["cycle_anchor_date"]
        int(sujo["cycle_length"])  # o que os chamadores fazem: nenhum pode levantar
        {int(d) for d in sujo["cycle_off_days"].split(",") if d}
        assert sujo["cycle_enabled"] is False, "config que este app nunca escreveu tem que desligar o ciclo"

        def _forca(coluna, valor):
            conn = db.get_connection()
            conn.execute(f"UPDATE app_settings SET cycle_enabled = 1, {coluna} = ? WHERE id = 1", (valor,))
            conn.commit()
            conn.close()
            return settings.get_settings()

        # REAL infinito: int(float('inf')) levanta OverflowError, que NÃO é
        # ValueError — escapava do get_settings() e derrubava o app inteiro no
        # boot, porque todo consumidor passa por essa função
        inf = _forca("cycle_length", 9e999)
        assert inf["cycle_length"] == settings.DEFAULTS["cycle_length"], inf["cycle_length"]
        assert inf["cycle_enabled"] is False

        # tamanho absurdo passava pelo piso e travava o range() que monta as
        # bolinhas de dia (main._rebuild_cycle_day_toggles) — o "trava pra sempre"
        gigante = _forca("cycle_length", 1099511627776)
        assert gigante["cycle_enabled"] is False, "ciclo gigante tinha que ser desligado"
        assert gigante["cycle_length"] <= settings.CYCLE_LENGTH_MAX, gigante["cycle_length"]
        list(range(gigante["cycle_length"]))  # o que o chamador faz; não pode explodir nem travar

        # campo enorme não pode virar parse O(n) a cada get_settings()
        enorme = _forca("cycle_off_days", ",".join(["1"] * 100000))
        assert enorme["cycle_off_days"] == "", "off_days gigante tinha que cair pro padrão"

        # e um ciclo VÁLIDO continua passando intacto
        conn = db.get_connection()
        conn.execute("UPDATE app_settings SET cycle_enabled = 1, cycle_length = 3, "
                     "cycle_off_days = '2', cycle_anchor_date = '2026-01-01' WHERE id = 1")
        conn.commit()
        conn.close()
        valido = settings.get_settings()
        assert valido["cycle_enabled"] is True and valido["cycle_length"] == 3, valido
        assert valido["cycle_off_days"] == "2" and valido["cycle_anchor_date"] == "2026-01-01"

        # tamanho válido + lixo só em off_days/anchor também desliga o ciclo
        # (antes só trocava pelo padrão e deixava missões follow_cycle escondidas)
        for coluna, lixo in (("cycle_off_days", "x"), ("cycle_anchor_date", "ontem")):
            conn = db.get_connection()
            conn.execute("UPDATE app_settings SET cycle_enabled = 1, cycle_length = 3, "
                         "cycle_off_days = '2', cycle_anchor_date = '2026-01-01' WHERE id = 1")
            conn.execute(f"UPDATE app_settings SET {coluna} = ? WHERE id = 1", (lixo,))
            conn.commit()
            conn.close()
            assert settings.get_settings()["cycle_enabled"] is False, f"lixo em {coluna} tinha que desligar o ciclo"

        # ciclo de tamanho 0 também não pode chegar no "% cycle_length" do chamador
        conn = db.get_connection()
        conn.execute("UPDATE app_settings SET cycle_length = 0 WHERE id = 1")
        conn.commit()
        conn.close()
        assert settings.get_settings()["cycle_length"] > 0

        # Bytes indecodificáveis numa coluna TEXT: o SQLite não valida encoding,
        # então um backup de terceiro pode trazer CAST(x'80' AS TEXT). O driver
        # levantava OperationalError já no fetchone(), ANTES do saneamento do
        # ciclo — e como get_settings() roda no build(), o app não subia mais.
        # Fechado no text_factory de database.get_connection.
        import sqlite3
        conn = sqlite3.connect(db.DB_PATH)
        conn.execute("UPDATE app_settings SET cycle_off_days = CAST(x'80' AS TEXT), "
                     "accent_theme = CAST(x'ff' AS TEXT) WHERE id = 1")
        conn.commit()
        conn.close()
        podre = settings.get_settings()  # não pode levantar
        assert isinstance(podre["accent_theme"], str), type(podre["accent_theme"])
        assert podre["cycle_off_days"] == "", podre["cycle_off_days"]
        settings.set_accent_theme("floresta")  # devolve o banco a um estado são

        # _set() só aceita nome de coluna do allowlist (DEFAULTS) — barra
        # interpolação de identificador arbitrário na SQL
        try:
            settings._set("is_premium = 1; DROP TABLE app_settings; --", 0)
            assert False, "deveria ter recusado a coluna forjada"
        except ValueError:
            pass
        assert settings.get_settings()["is_premium"] is True, "a tabela e o valor continuam intactos"

        # lembretes já disparados: persistem em disco (o app morre e reabre o
        # tempo todo no Android) e só guardam o dia de hoje
        assert settings.get_reminders_fired() == {}, "instalação nova não tem lembrete disparado"
        settings.set_reminder_fired("daily", "2026-09-03")
        settings.set_reminder_fired("m7", "2026-09-03")
        assert settings.get_reminders_fired() == {"daily": "2026-09-03", "m7": "2026-09-03"}
        # virou o dia: as marcas velhas são podadas em vez de acumular pra sempre
        settings.set_reminder_fired("daily", "2026-09-04")
        assert settings.get_reminders_fired() == {"daily": "2026-09-04"}, "devia ter podado o dia anterior"
        # coluna corrompida não pode derrubar o app — vale como "nada disparou"
        settings._set("reminders_fired", "isso não é json {{{")
        assert settings.get_reminders_fired() == {}, "JSON inválido devia virar dict vazio"

        # seção recolhível das recompensas de nível (aba Missões)
        assert settings.get_settings()["level_rewards_open"] is True, "devia começar aberta"
        settings.set_level_rewards_open(False)
        assert settings.get_settings()["level_rewards_open"] is False, "devia persistir recolhida"

        print("OK — todos os checks passaram")


if __name__ == "__main__":
    run()
