"""Backup — copia o arquivo daily_quest.db inteiro, local (usuário escolhe o
arquivo, sem rede) ou na nuvem (presa à conta logada, ver README > Backup na
Nuvem). O banco local continua sendo a fonte da verdade nos dois casos — a
nuvem é só uma cópia de segurança, nunca sincroniza sozinha (sempre uma ação
explícita do usuário, pra nunca sobrescrever dado sem querer)."""
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

import account
import database as db
import missions
import supabase_client as sb


class InvalidBackupError(Exception):
    """Arquivo escolhido não é um backup válido do Discipliner — o banco atual
    NÃO foi tocado, quem chama só precisa avisar o usuário."""


def _checkpoint():
    """Com WAL (ver database.get_connection), escritas recentes podem estar só
    no -wal, não no arquivo .db principal — que é o que o backup copia. Um
    checkpoint TRUNCATE joga tudo pro .db e zera o -wal antes de copiar."""
    conn = db.get_connection()
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()


def _session_row():
    """A linha de local_session do banco ATUAL (dict) ou None se deslogado —
    também None se ainda não existe banco nenhum, ou se ele é de uma versão
    velha demais pra ter a tabela (get_connection criaria o arquivo à toa)."""
    if not db.DB_PATH.exists():
        return None
    conn = db.get_connection()
    try:
        row = conn.execute("SELECT * FROM local_session WHERE id = 1").fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    return dict(row) if row is not None else None


def _scrubbed_copy(dest_path):
    """Escreve em `dest_path` uma cópia do banco SEM a tabela local_session.
    Ela guarda o access_token e o refresh_token do Supabase em texto puro
    (ver account._save_session), e um backup vai parar em lugar que o banco
    do app não vai: pasta escolhida pelo usuário (às vezes sincronizada com
    alguma nuvem), armazenamento compartilhado do Android, ou o bucket do
    Supabase Storage. Sessão não é dado de backup — depois de restaurar,
    quem manda é a sessão do próprio aparelho (ver _replace_db).

    DROP + VACUUM em vez de DELETE: o VACUUM reescreve o arquivo inteiro, se
    não os bytes dos tokens continuariam lá nas páginas livres."""
    try:
        _checkpoint()
        shutil.copy(db.DB_PATH, dest_path)
        # isolation_level=None: sem transação implícita por baixo, se não o
        # VACUUM recusa ("cannot VACUUM from within a transaction")
        conn = sqlite3.connect(dest_path, isolation_level=None)
        try:
            # journal_mode=DELETE: o backup é UM arquivo só — em WAL sobraria
            # um -wal irmão do arquivo exportado, que ninguém copia junto.
            # temp_store=MEMORY: o VACUUM não precisa de diretório temporário
            # gravável (no Android não dá pra contar com um).
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("PRAGMA temp_store=MEMORY")
            conn.execute("DROP TABLE IF EXISTS local_session")
            conn.execute("VACUUM")
        finally:
            conn.close()  # fecha antes de qualquer limpeza, pra sumir o journal
    except BaseException:
        # nunca deixar pra trás um arquivo pela metade que ainda tenha token
        Path(dest_path).unlink(missing_ok=True)
        raise


def export_to(dest_path):
    """Levanta OSError se não der pra escrever no destino — nesse caso nada é
    criado lá."""
    # monta a cópia limpa num diretório temporário e só move pro destino
    # quando ela está pronta: nenhum byte com token chega a existir no
    # caminho que o usuário escolheu, nem por um instante, nem se a cópia
    # morrer no meio (disco cheio)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp) / "backup.db"
            _scrubbed_copy(staged)
            shutil.move(str(staged), str(dest_path))
    except sqlite3.Error as e:
        # quem chama (main.export_backup) trata OSError; falha do sqlite ao
        # montar a cópia é a mesma coisa pro usuário: não deu pra gerar o
        # arquivo. Sem isso, seria um tipo de erro novo escapando pra UI.
        raise OSError(str(e)) from e


def _is_valid_db(path):
    """True se `path` é um SQLite abrível com as tabelas essenciais do app.
    Barra tanto arquivo que não é banco quanto banco de outro app."""
    try:
        conn = sqlite3.connect(path)
        try:
            names = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
    except sqlite3.Error:
        return False
    return {"missions", "completions", "app_settings"} <= names


def _replace_db(fill_incoming):
    """Troca daily_quest.db pelo conteúdo que `fill_incoming(tmp_path)` escrever,
    só se o novo for válido. Guarda o anterior em .prev pra rollback, e roda
    db.init_db() depois (um backup de versão mais antiga do app pode não ter
    colunas novas — as migrações preenchem). Levanta InvalidBackupError sem
    tocar no banco atual se o novo não passar na validação."""
    incoming = db.DB_PATH.with_suffix(".incoming")
    prev = db.DB_PATH.with_suffix(".prev")
    session = _session_row()  # a sessão DESTE aparelho, antes da troca
    fill_incoming(incoming)
    if not _is_valid_db(incoming):
        incoming.unlink(missing_ok=True)
        raise InvalidBackupError()
    if db.DB_PATH.exists():
        _checkpoint()  # esvazia o -wal antigo antes de trocar o .db por baixo dele
        shutil.copy(db.DB_PATH, prev)
    os.replace(incoming, db.DB_PATH)
    # -wal/-shm que sobraram são do banco ANTIGO; deixá-los faria o SQLite
    # tentar aplicar num arquivo que não é mais o deles
    for suffix in ("-wal", "-shm"):
        db.DB_PATH.with_name(db.DB_PATH.name + suffix).unlink(missing_ok=True)
    try:
        db.init_db()
    except Exception:
        if prev.exists():
            os.replace(prev, db.DB_PATH)  # migração explodiu -> desfaz
        raise
    prev.unlink(missing_ok=True)
    # O arquivo importado traz a local_session DELE junto (backups feitos por
    # versões anteriores do app levavam os tokens do Supabase dentro; ver
    # _scrubbed_copy). Descarta sempre essa sessão e regrava só a que ESTE
    # aparelho já tinha — nunca a que veio no arquivo, que pode ser de outra
    # pessoa. MUDANÇA DE COMPORTAMENTO: restaurar um backup feito antes desta
    # atualização não loga mais na conta gravada dentro dele — um aparelho
    # deslogado continua deslogado, é só entrar na conta normalmente.
    # (db.init_db() acima sempre recria local_session, então a tabela existe.)
    conn = db.get_connection()
    conn.execute("DELETE FROM local_session")
    conn.commit()
    conn.close()
    if session is not None:
        account.restore_session_row(session)
    missions._invalidate_missions_cache()  # o .db inteiro trocou por baixo do cache


def import_from(src_path):
    """Levanta InvalidBackupError se `src_path` não for um backup válido — nesse
    caso o banco atual continua intacto."""
    _replace_db(lambda dest: shutil.copy(src_path, dest))


def export_to_cloud(access_token, user_id):
    """Levanta Exception(msg) se a API recusar."""
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / "backup.db"
        _scrubbed_copy(staged)
        data = staged.read_bytes()
    try:
        sb.upload_backup(access_token, user_id, data)
    except sb.SupabaseError as e:
        raise Exception(str(e)) from e


def import_from_cloud(access_token, user_id):
    """Levanta Exception(msg) se a API recusar, ou InvalidBackupError se o que
    veio da nuvem não for um banco válido (banco atual fica intacto). Retorna
    False (sem levantar nada) se essa conta ainda não tiver backup na nuvem."""
    try:
        data = sb.download_backup(access_token, user_id)
    except sb.SupabaseError as e:
        raise Exception(str(e)) from e
    if data is None:
        return False
    _replace_db(lambda dest: dest.write_bytes(data))
    return True
