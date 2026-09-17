"""Loja de Recompensas: o usuário define suas próprias recompensas (ex.:
"Assistir um filme", 20 pontos) e troca pontos ganhos por elas — recompensa
autodefinida/tangível retém mais gente que só XP virtual (ver README).

Pontos disponíveis = todos os pontos já ganhos (completions, o mesmo total
que já alimenta o nível) MENOS o que já foi gasto em resgates. Não é uma
coluna própria — sempre calculado na hora, então nunca some dessincronizado
do histórico real."""
from datetime import date

import database as db


def add_reward(name, cost):
    name = name[:1].upper() + name[1:]
    conn = db.get_connection()
    conn.execute("INSERT INTO custom_rewards (name, cost) VALUES (?, ?)", (name, cost))
    conn.commit()
    conn.close()


def update_reward(reward_id, name, cost):
    name = name[:1].upper() + name[1:]
    conn = db.get_connection()
    conn.execute("UPDATE custom_rewards SET name = ?, cost = ? WHERE id = ?", (name, cost, reward_id))
    conn.commit()
    conn.close()


def remove_reward(reward_id):
    conn = db.get_connection()
    conn.execute("DELETE FROM custom_rewards WHERE id = ?", (reward_id,))
    conn.commit()
    conn.close()


def list_rewards():
    conn = db.get_connection()
    rows = conn.execute("SELECT * FROM custom_rewards ORDER BY cost").fetchall()
    conn.close()
    return rows


def available_points():
    conn = db.get_connection()
    earned = conn.execute("SELECT COALESCE(SUM(points), 0) FROM completions").fetchone()[0]
    spent = conn.execute("SELECT COALESCE(SUM(cost), 0) FROM reward_redemptions").fetchone()[0]
    conn.close()
    return earned - spent


class NotEnoughPointsError(Exception):
    pass


def redeem(reward_id):
    """Levanta NotEnoughPointsError se não tiver pontos suficientes — quem
    chama não precisa reconferir available_points() antes, só tratar o erro."""
    conn = db.get_connection()
    reward = conn.execute("SELECT * FROM custom_rewards WHERE id = ?", (reward_id,)).fetchone()
    if reward is None:
        conn.close()
        return
    if available_points() < reward["cost"]:
        conn.close()
        raise NotEnoughPointsError()
    conn.execute(
        "INSERT INTO reward_redemptions (reward_id, reward_name, cost, redeemed_at) VALUES (?, ?, ?, ?)",
        (reward["id"], reward["name"], reward["cost"], date.today().isoformat()),
    )
    conn.commit()
    conn.close()


def redemption_history(limit=20):
    conn = db.get_connection()
    rows = conn.execute("SELECT * FROM reward_redemptions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return rows
