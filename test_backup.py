"""Self-check: python test_backup.py (não precisa do Kivy)."""
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path

import database as db


def _tables(path):
    conn = sqlite3.connect(path)
    try:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def run():
    with tempfile.TemporaryDirectory() as tmp:
        db.DB_PATH = Path(tmp) / "test.db"
        db.init_db()
        import backup
        import missions

        missions.add_mission("Original", "diaria", "facil")
        backup_path = Path(tmp) / "backup.db"
        backup.export_to(backup_path)
        assert backup_path.exists(), "export_to deveria criar o arquivo de backup"

        # muda o banco atual — a restauração deve trazer de volta o estado do backup
        missions.add_mission("Só depois do backup", "diaria", "facil")
        assert len(missions.list_missions()) == 2

        backup.import_from(backup_path)
        assert len(missions.list_missions()) == 1, "restaurar deveria voltar pro estado do backup"
        assert missions.list_missions()[0]["name"] == "Original"

        # arquivo que não é um SQLite válido: rejeita e NÃO toca no banco atual
        junk = Path(tmp) / "junk.db"
        junk.write_bytes(b"isto nao e um banco sqlite\n" * 40)
        try:
            backup.import_from(junk)
            assert False, "import de lixo deveria levantar InvalidBackupError"
        except backup.InvalidBackupError:
            pass
        assert len(missions.list_missions()) == 1, "banco atual deveria continuar intacto após import inválido"
        assert missions.list_missions()[0]["name"] == "Original"

        # SQLite válido mas de outro app (sem as tabelas do Discipliner): rejeita
        import sqlite3
        alien = Path(tmp) / "alien.db"
        c = sqlite3.connect(alien); c.execute("CREATE TABLE foo (x)"); c.commit(); c.close()
        try:
            backup.import_from(alien)
            assert False, "import de banco alheio deveria levantar InvalidBackupError"
        except backup.InvalidBackupError:
            pass
        assert missions.list_missions()[0]["name"] == "Original"

        # backup de uma versão ANTIGA (faltando coluna nova): importa e migra
        old = Path(tmp) / "old.db"
        c = sqlite3.connect(old)
        c.execute("CREATE TABLE missions (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, "
                  "periodicity TEXT NOT NULL, difficulty TEXT NOT NULL, points INTEGER NOT NULL)")
        c.execute("CREATE TABLE completions (id INTEGER PRIMARY KEY AUTOINCREMENT, mission_id INTEGER, "
                  "mission_name TEXT, date TEXT, points INTEGER)")
        c.execute("CREATE TABLE app_settings (id INTEGER PRIMARY KEY CHECK (id = 1))")
        c.execute("INSERT INTO missions (name, periodicity, difficulty, points) VALUES ('Legado','diaria','facil',1)")
        c.commit(); c.close()
        backup.import_from(old)
        restored = missions.list_missions()
        assert len(restored) == 1 and restored[0]["name"] == "Legado"
        assert "follow_cycle" in restored[0].keys(), "db.init_db() deveria ter rodado as migrações no import"

        # --- backup NUNCA leva os tokens da sessão junto (CWE-312) ---
        # local_session guarda access_token/refresh_token do Supabase em texto
        # puro; o arquivo de backup vai pra pasta escolhida pelo usuário e pro
        # Supabase Storage, onde esses tokens não podem chegar.
        import account
        import supabase_client as sb
        TOKEN = "canario-access-token-nao-pode-vazar"
        REFRESH = "canario-refresh-token-nao-pode-vazar"
        account.restore_session_row({
            "user_id": "u1", "email": "eric@teste.com", "name": "Eric",
            "access_token": TOKEN, "refresh_token": REFRESH,
            "expires_at": int(time.time()) + 3600,
        })
        # sessão gravada ANTES de encher o banco: a página dela fica no meio do
        # arquivo, então só apagar a tabela não encolheria o arquivo nem sumiria
        # com os bytes — é o VACUUM que reescreve (o check abaixo falha sem ele)
        for i in range(200):
            missions.add_mission(f"Enchendo {i}", "diaria", "facil")

        exported = Path(tmp) / "exportado.db"
        backup.export_to(exported)
        blob = exported.read_bytes()
        assert "local_session" not in _tables(exported), "tabela de sessão não pode ir no backup"
        assert TOKEN.encode() not in blob, "access_token vazou no backup local"
        assert REFRESH.encode() not in blob, "refresh_token vazou no backup local"
        assert not Path(str(exported) + "-wal").exists(), "não pode sobrar -wal ao lado do backup"
        assert len(missions.list_missions()) == 201, "export não mexe no banco atual"
        assert account.current_session()["access_token"] == TOKEN, "export não desloga ninguém"

        uploaded = {}
        sb.upload_backup = lambda access_token, user_id, file_bytes: uploaded.update(b=file_bytes)
        backup.export_to_cloud("tok-u1", "u1")
        cloud_file = Path(tmp) / "nuvem.db"
        cloud_file.write_bytes(uploaded["b"])
        assert "local_session" not in _tables(cloud_file), "tabela de sessão não pode ir pra nuvem"
        assert TOKEN.encode() not in uploaded["b"], "access_token vazou no backup da nuvem"
        assert REFRESH.encode() not in uploaded["b"], "refresh_token vazou no backup da nuvem"
        conn = sqlite3.connect(cloud_file)
        assert conn.execute("SELECT COUNT(*) FROM missions").fetchone()[0] == 201, "o resto do backup continua lá"
        conn.close()

        # --- sessão que vem DENTRO de um arquivo importado é sempre descartada ---
        # backup feito por uma versão anterior do app (cópia crua, com a
        # local_session de OUTRA pessoa dentro)
        pre_patch = Path(tmp) / "pre_patch.db"
        backup._checkpoint()
        shutil.copy(db.DB_PATH, pre_patch)
        conn = sqlite3.connect(pre_patch, isolation_level=None)
        conn.execute("PRAGMA journal_mode=DELETE")  # senão a troca ficaria só no -wal
        conn.execute("UPDATE local_session SET user_id = 'invasor', access_token = ?, "
                     "refresh_token = ? WHERE id = 1", ("tok-invasor", "ref-invasor"))
        conn.close()
        assert b"tok-invasor" in pre_patch.read_bytes(), "pré-condição: o token alheio está no arquivo"

        # aparelho LOGADO: fica com a sessão dele, nunca com a do arquivo
        backup.import_from(pre_patch)
        conn = db.get_connection()
        tokens = [r[0] for r in conn.execute("SELECT access_token FROM local_session")]
        conn.close()
        assert tokens == [TOKEN], f"sessão do arquivo não pode entrar: {tokens}"

        # aparelho DESLOGADO: continua deslogado — restaurar um backup antigo
        # não loga mais na conta que estava gravada dentro dele
        conn = db.get_connection()
        conn.execute("DELETE FROM local_session")
        conn.commit()
        conn.close()
        backup.import_from(pre_patch)
        assert account.current_session() is None, "backup não pode logar a conta que veio dentro dele"

        print("OK — todos os checks passaram")


if __name__ == "__main__":
    run()
