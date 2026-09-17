"""Self-check: python test_missions.py (não precisa do Kivy, só sqlite)."""
import tempfile
from datetime import date, timedelta
from pathlib import Path

import database as db


class _FixedToday(date):
    """date.today() preso a um dia no MEIO do mês. O cenário de congelamento
    do run() ("1 por mês perdoa today-1; today-2 quebra") só vale se today-1 e
    today-2 caem no MESMO mês-calendário — com a data real, o teste quebrava
    todo dia 1/2 do mês (cada mês tem sua própria cota de congelamento).
    complete_mission usa date.today() por dentro, então tem que ser o módulo,
    não só a variável local."""
    @classmethod
    def today(cls):
        return date(2024, 5, 15)


def run():
    with tempfile.TemporaryDirectory() as tmp:
        db.DB_PATH = Path(tmp) / "test.db"
        db.init_db()
        import missions
        # date.today() fixo durante run() (ver _FixedToday) — restaurado no fim.
        # Se um assert falhar antes disso, o processo morre e as outras funções
        # (que querem a data real) nem chegam a rodar, então não precisa finally.
        missions.date = _FixedToday

        # tabela de pontos fixa: periodicidade x dificuldade
        assert missions.points_for("diaria", "facil") == 1
        assert missions.points_for("semanal", "media") == 7
        assert missions.points_for("mensal", "dificil") == 25

        missions.add_mission("Ler 10 páginas", "diaria", "media")
        m = missions.list_missions()[0]
        assert m["points"] == 2, "diária média deveria valer 2 pontos, e não ser editável"
        assert missions.is_done_this_period(m) is False, "missão nova não deveria estar concluída"
        assert missions.pending_today() == ["Ler 10 páginas"], "missão não concluída deveria aparecer como pendente"

        missions.complete_mission(m["id"], obs="primeira tentativa")
        m2 = missions.list_missions()[0]
        assert missions.is_done_this_period(m2) is True, "deveria estar concluída após complete_mission"
        assert missions.progress_today() == 1.0, "progresso deveria ser 100% com 1/1 concluída"
        assert missions.pending_today() == [], "nada deveria estar pendente com tudo concluído"

        h = db.history()
        assert len(h) == 1 and h[0]["points"] == 2, "histórico deveria ter 1 entrada de 2 pts"
        assert h[0]["obs"] == "primeira tentativa", "obs deveria ser gravada na conclusão, não na criação"

        missions.complete_mission(m["id"])  # idempotente: não deve duplicar no mesmo período
        assert len(db.history()) == 1, "completar 2x no mesmo período não deveria duplicar histórico"

        missions.uncomplete_mission(m["id"])
        m3 = missions.list_missions()[0]
        assert missions.is_done_this_period(m3) is False, "uncomplete deveria desfazer a conclusão"
        assert len(db.history()) == 0, "uncomplete deveria remover do histórico"

        # persiste mesmo "fechando o app": nova conexão no mesmo arquivo de banco
        assert len(missions.list_missions()) == 1, "missão deveria continuar existindo em uma nova conexão"

        # progresso reseta no limite de cada periodicidade
        today = missions.date.today()  # _FixedToday: bate com o que complete_mission grava
        missions.add_mission("Treino", "diaria", "facil")
        missions.add_mission("Revisão semanal", "semanal", "facil")
        missions.add_mission("Planejamento mensal", "mensal", "facil")
        diaria, semanal, mensal = missions.list_missions()[-3:]
        missions.complete_mission(diaria["id"])
        missions.complete_mission(semanal["id"])
        missions.complete_mission(mensal["id"])
        diaria, semanal, mensal = missions.list_missions()[-3:]

        assert missions.is_done_this_period(diaria, today=today + timedelta(days=1)) is False, \
            "diária deveria resetar no dia seguinte"
        assert missions.is_done_this_period(semanal, today=today + timedelta(weeks=1)) is False, \
            "semanal deveria resetar na semana seguinte"
        next_month = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
        assert missions.is_done_this_period(mensal, today=next_month) is False, \
            "mensal deveria resetar no mês seguinte"
        assert missions.is_done_this_period(diaria, today=today) is True, \
            "diária ainda deve valer no mesmo dia"

        # editar missão: nome (primeira maiúscula), periodicidade e dificuldade mudam; pontos recalculam
        missions.update_mission(diaria["id"], "corrida", "semanal", "dificil")
        editada = next(m for m in missions.list_missions() if m["id"] == diaria["id"])
        assert editada["name"] == "Corrida", "update_mission também deveria capitalizar a primeira letra"
        assert editada["periodicity"] == "semanal" and editada["difficulty"] == "dificil"
        assert editada["points"] == 10, "pontos deveriam recalcular pra semanal/difícil (10)"

        # nível/xp: soma de TODOS os pontos já ganhos (histórico completo, inclui as 3 missões
        # de teste do bloco de periodicidade acima: 1 + 5 + 12 = 18 — a mensal
        # (10) já sai com 1.25x, porque 1 mês de sequência é o 1º degrau dela:
        # round(12.5) = 12)
        info = missions.level_info()
        assert info["total_xp"] == 18, info
        assert info["level"] == 1

        # "Corrida" (ex-"Treino") já cumpriu seu papel no CRUD acima — remove
        # antes da seção de sequência: ela virou "semanal" mas nunca foi
        # concluída como semanal (só como diária, antes do rename), então
        # ficaria pesando contra o % de "Revisão semanal" lá embaixo à toa
        missions.remove_mission(editada["id"])

        # a "Ler 10 páginas" já cumpriu seu papel no CRUD acima — remove antes
        # da seção de sequência, senão ela entra sem querer no denominador do
        # % (sequência só conta um dia/período com pelo menos 65% das missões
        # daquela periodicidade concluídas — ver missions.COMPLETION_THRESHOLD).
        # "Treino" virou "corrida"/semanal duas linhas acima, então cria uma
        # missão diária nova só pra essa seção.
        missions.remove_mission(m["id"])
        missions.add_mission("Correr", "diaria", "facil")
        correr = missions.list_missions()[-1]
        missions.complete_mission(correr["id"])

        # sequência: 1ª conclusão de sempre da diária mostra sequência 1, e não
        # deveria consumir nenhum congelamento — não tem o que perdoar num dia
        # anterior à missão sequer existir (ver comentário em current_streak)
        assert missions.streak_freeze_available(today=today) is True, \
            "1ª conclusão de sempre não deveria ter consumido nenhum congelamento"
        assert missions.current_streak(today=today) == 1, missions.current_streak(today=today)

        # buraco de verdade DEPOIS de já existir uma conclusão anterior é
        # perdoado pelo congelamento do mês (sobe de 1 pra 2, today-1 perdoado),
        # mas um SEGUNDO buraco não é (só 1 congelamento por mês no grátis)
        conn = db.get_connection()
        conn.execute(
            "INSERT INTO completions (mission_id, mission_name, date, points, obs) VALUES (?, ?, ?, ?, ?)",
            (correr["id"], "Correr", (today - timedelta(days=3)).isoformat(), 5, ""),
        )
        conn.commit()
        conn.close()
        assert missions.current_streak(today=today) == 2, \
            "congelamento do mês perdoa today-1; sem mais congelamento sobrando, today-2 trava a sequência em 2"

        # semanal + mensal + correr(hoje) + correr(inserida) + treino/diaria (histórico, antes do rename)
        assert missions.total_completions() == 5, missions.total_completions()

        # missão diária com dias específicos da semana
        missions.add_mission("Ioga", "diaria", "facil", custom_days=str(today.weekday()))
        ioga = missions.list_missions()[-1]
        assert missions.is_scheduled_today(ioga, today=today) is True, "hoje é um dos dias marcados"
        missions.complete_mission(ioga["id"])
        ioga = next(m for m in missions.list_missions() if m["id"] == ioga["id"])
        assert missions.is_done_this_period(ioga, today=today) is True, "deveria completar num dia agendado"

        outro_weekday = (today.weekday() + 1) % 7
        missions.add_mission("Corrida", "diaria", "facil", custom_days=str(outro_weekday))
        corrida = missions.list_missions()[-1]
        assert missions.is_scheduled_today(corrida, today=today) is False, "hoje não é o dia marcado dessa"
        missions.complete_mission(corrida["id"])
        corrida = next(m for m in missions.list_missions() if m["id"] == corrida["id"])
        assert missions.is_done_this_period(corrida, today=today) is False, \
            "complete_mission não deveria ter efeito fora do dia agendado"

        # missões sem dias específicos (custom_days="") continuam valendo todo dia, como sempre
        assert missions.is_scheduled_today(diaria, today=today) is True

        # multiplicador de pontos por sequência — tabela de degraus
        assert missions.streak_multiplier(0) == 1.0
        assert missions.streak_multiplier(4) == 1.0
        assert missions.streak_multiplier(5) == 1.25, "5 dias de sequência deveria garantir 1.25x"
        assert missions.streak_multiplier(9) == 1.25
        assert missions.streak_multiplier(10) == 1.5
        assert missions.streak_multiplier(20) == 1.75
        assert missions.streak_multiplier(30) == 2.0
        assert missions.streak_multiplier(99) == 2.0

        assert missions.streak_next_tier(0) == (5, 1.25)
        assert missions.streak_next_tier(4) == (1, 1.25)
        assert missions.streak_next_tier(5) == (5, 1.5)
        assert missions.streak_next_tier(30) is None, "no degrau máximo não tem próximo bônus"

        # semanal sobe a cada 2 semanas; mensal a cada mês
        assert missions.streak_multiplier(1, "semanal") == 1.0
        assert missions.streak_multiplier(2, "semanal") == 1.25, "2 semanas deveriam garantir 1.25x"
        assert missions.streak_multiplier(4, "semanal") == 1.5
        assert missions.streak_multiplier(8, "semanal") == 2.0
        assert missions.streak_next_tier(0, "semanal") == (2, 1.25)
        assert missions.streak_next_tier(3, "semanal") == (1, 1.5)
        assert missions.streak_multiplier(0, "mensal") == 1.0
        assert missions.streak_multiplier(1, "mensal") == 1.25, "1 mês deveria garantir 1.25x"
        assert missions.streak_multiplier(3, "mensal") == 1.75
        assert missions.streak_multiplier(12, "mensal") == 2.0
        assert missions.streak_next_tier(1, "mensal") == (1, 1.5)
        assert missions.streak_next_tier(4, "mensal") is None

        # sequência por periodicidade: "Revisão semanal" e "Planejamento mensal" (lá de cima)
        # já foram concluídas hoje, então cada sequência própria já está em 1 —
        # e são independentes uma da outra e da diária (que está em 2, com congelamento)
        assert missions.current_streak(today=today, periodicity="semanal") == 1
        assert missions.current_streak(today=today, periodicity="mensal") == 1

        # "Correr"/"Ioga"/"Corrida" já cumpriram seu papel acima (congelamento,
        # agendamento por dia) — remove antes da sequência longa abaixo, senão
        # entram no denominador do % também (nenhuma delas foi concluída nos
        # dias que a gente vai inserir manualmente a seguir)
        missions.remove_mission(correr["id"])
        missions.remove_mission(ioga["id"])
        missions.remove_mission(corrida["id"])

        # a sequência diária já está em 2 (hoje + ontem congelado, lá de cima).
        # completa mais 3 dias direto no banco (today-2, today-3 já tinha 1 real,
        # today-4) pra ela chegar em 5 sem esperar 5 dias de verdade
        missions.add_mission("Prancha", "diaria", "dificil")  # 3 pontos base
        prancha = missions.list_missions()[-1]
        conn = db.get_connection()
        for i in range(2, 5):  # today-2, today-3, today-4
            conn.execute(
                "INSERT INTO completions (mission_id, mission_name, date, points, obs, periodicity) "
                "VALUES (?, ?, ?, ?, ?, 'diaria')",
                (prancha["id"], "Prancha", (today - timedelta(days=i)).isoformat(), 3, ""),
            )
        conn.commit()
        conn.close()
        assert missions.current_streak(today=today, periodicity="diaria") == 5, \
            "hoje + ontem (congelado) + today-2/3/4 recém-inseridos — sequência de 5"

        missions.complete_mission(prancha["id"])  # sequência diária já está em 5 -> multiplicador 1.25x
        hoje_prancha = [c for c in db.history() if c["mission_id"] == prancha["id"] and c["date"] == today.isoformat()]
        assert len(hoje_prancha) == 1
        assert hoje_prancha[0]["points"] == round(3 * 1.25) == 4, \
            "3 pontos base * 1.25x (5º dia de sequência) deveria virar 4"

        missions.date = date  # restaura pras outras funções (querem a data real)
        print("OK — todos os checks passaram")


def run_premium_freeze_cap():
    """Congelamento com teto configurável (Premium ganha mais por mês — ver
    README > Monetização) — cenário isolado, tempdir/datas próprias."""
    with tempfile.TemporaryDirectory() as tmp:
        db.DB_PATH = Path(tmp) / "test_premium.db"
        db.init_db()
        import missions

        today = date(2024, 3, 15)  # fixo e no meio do mês: today-1..4 caem no mesmo mês
        missions.add_mission("Meditar", "diaria", "facil")
        m = missions.list_missions()[0]

        # 3 buracos no mesmo mês: today-1, today-2, today-3 (nenhuma conclusão real)
        # só a partir de today-4 tem conclusão de verdade
        conn = db.get_connection()
        conn.execute(
            "INSERT INTO completions (mission_id, mission_name, date, points, obs, periodicity) "
            "VALUES (?, ?, ?, ?, ?, 'diaria')",
            (m["id"], "Meditar", (today - timedelta(days=4)).isoformat(), 1, ""),
        )
        conn.commit()
        conn.close()

        # grátis (teto 1): só perdoa today-1, trava em today-2 -> sequência = 1
        assert missions.current_streak(today=today, periodicity="diaria", max_freezes_per_month=1) == 1

        # premium (teto 3): perdoa today-1/2/3, alcança o today-4 real -> sequência = 4
        db.DB_PATH = Path(tmp) / "test_premium2.db"  # instância nova: freezes já gravados no teste acima não interferem
        db.init_db()
        missions.add_mission("Meditar", "diaria", "facil")
        m2 = missions.list_missions()[0]
        conn = db.get_connection()
        conn.execute(
            "INSERT INTO completions (mission_id, mission_name, date, points, obs, periodicity) "
            "VALUES (?, ?, ?, ?, ?, 'diaria')",
            (m2["id"], "Meditar", (today - timedelta(days=4)).isoformat(), 1, ""),
        )
        conn.commit()
        conn.close()
        assert missions.current_streak(today=today, periodicity="diaria", max_freezes_per_month=missions.PREMIUM_FREEZE_CAP) == 4, \
            "teto de 3 congelamentos deveria perdoar today-1/2/3 e alcançar a conclusão real em today-4"
        assert missions.streak_freeze_available(today=today, max_freezes_per_month=missions.PREMIUM_FREEZE_CAP) is False, \
            "os 3 congelamentos do mês já foram todos usados"

        # Modo Sem Penalidade (max_freezes_per_month=None): nunca quebra, mesmo com buraco enorme
        db.DB_PATH = Path(tmp) / "test_no_penalty.db"
        db.init_db()
        missions.add_mission("Meditar", "diaria", "facil")
        m3 = missions.list_missions()[0]
        conn = db.get_connection()
        conn.execute(
            "INSERT INTO completions (mission_id, mission_name, date, points, obs, periodicity) "
            "VALUES (?, ?, ?, ?, ?, 'diaria')",
            (m3["id"], "Meditar", (today - timedelta(days=10)).isoformat(), 1, ""),
        )
        conn.commit()
        conn.close()
        assert missions.current_streak(today=today, periodicity="diaria", max_freezes_per_month=None) == 10, \
            "sem limite, todo o buraco de 9 dias é perdoado até a conclusão real em today-10 (today-1..today-10)"
        assert missions.streak_freeze_available(today=today, max_freezes_per_month=None) is True, \
            "sem limite, sempre 'disponível'"

        print("OK — congelamentos premium/sem-penalidade passaram")


def run_level_and_mission_limit():
    """Progressão de XP por nível (25, 56, 89... composta) e limite de missões
    (7 grátis +1/nível, 15 Premium +2/nível) — cenário isolado."""
    with tempfile.TemporaryDirectory() as tmp:
        db.DB_PATH = Path(tmp) / "test_level.db"
        db.init_db()
        import missions

        assert missions._xp_needed_for_level(1) == 25
        assert missions._xp_needed_for_level(2) == 56, "25*2 + 25% de 25 = 56.25 -> 56"
        assert missions._xp_needed_for_level(3) == 89, "25*3 + 25% de 56.25 = 89.0625 -> 89"

        missions.add_mission("Pontuar", "diaria", "media")  # 2 pontos por conclusão
        m = missions.list_missions()[0]
        conn = db.get_connection()

        def set_total_xp(total):
            conn.execute("DELETE FROM completions")
            if total:
                conn.execute(
                    "INSERT INTO completions (mission_id, mission_name, date, points, obs, periodicity) "
                    "VALUES (?, ?, ?, ?, ?, 'diaria')",
                    (m["id"], "Pontuar", date.today().isoformat(), total, ""),
                )
            conn.commit()

        set_total_xp(0)
        assert missions.level_info()["level"] == 1
        set_total_xp(24)
        assert missions.level_info()["level"] == 1, "24 XP ainda não fecha o nível 1 (precisa de 25)"
        set_total_xp(25)
        info = missions.level_info()
        assert info["level"] == 2 and info["xp_in_level"] == 0, "25 XP fecha o nível 1 -> nível 2, 0 XP nele ainda"
        assert info["xp_for_next"] == 56, "nível 2 pede 56 XP pra fechar"
        set_total_xp(80)  # 25 (nível 1) + 55 (quase os 56 do nível 2)
        assert missions.level_info()["level"] == 2
        set_total_xp(81)  # 25 + 56 = fecha o nível 2 -> nível 3
        assert missions.level_info()["level"] == 3

        # limite de missões: 7 grátis (+1/nível) / 15 Premium (+2/nível), nível 1
        set_total_xp(0)
        assert missions.mission_limit(is_premium=False) == 7
        assert missions.mission_limit(is_premium=True) == 15
        set_total_xp(81)  # nível 3 (ver acima) -> +2 níveis sobre o nível 1
        assert missions.mission_limit(is_premium=False) == 9, "grátis: +1/nível x 2 níveis"
        assert missions.mission_limit(is_premium=True) == 19, "premium: +2/nível x 2 níveis"
        conn.close()

        print("OK — nível/XP e limite de missões passaram")


def run_challenge_multiplier():
    """Missão que veio de um Desafio ganha CHALLENGE_MULTIPLIER (1.5x) nos
    pontos ao concluir, combinado (multiplicado) com o bônus de sequência."""
    with tempfile.TemporaryDirectory() as tmp:
        db.DB_PATH = Path(tmp) / "test_challenge.db"
        db.init_db()
        import missions

        missions.add_mission("Normal", "diaria", "media")  # 2 pontos, sem desafio
        missions.add_mission("Do desafio", "diaria", "media", challenge_id="fitness")  # 2 pontos, com desafio
        normal_id = missions.list_missions()[0]["id"]
        challenge_id = missions.list_missions()[1]["id"]

        missions.complete_mission(normal_id)
        missions.complete_mission(challenge_id)

        today = date.today().isoformat()
        conn = db.get_connection()
        normal_points = conn.execute(
            "SELECT points FROM completions WHERE mission_id = ? AND date = ?", (normal_id, today),
        ).fetchone()["points"]
        challenge_points = conn.execute(
            "SELECT points FROM completions WHERE mission_id = ? AND date = ?", (challenge_id, today),
        ).fetchone()["points"]
        conn.close()

        assert normal_points == 2, "sem desafio, sem sequência ainda -> pontos crus"
        assert challenge_points == 3, "2 pontos x 1.5 (CHALLENGE_MULTIPLIER) = 3"

        # "+"/"X" nos popups de sugestão/desafio (ver main.py > open_suggestions_popup)
        assert missions.added_suggestion_ids() == set(), "nenhuma missão veio de sugestão ainda"
        assert missions.added_challenge_ids() == {"fitness"}
        missions.add_mission("Outra", "diaria", "facil", suggestion_id="water")
        assert missions.added_suggestion_ids() == {"water"}

        print("OK — multiplicador de desafio passou")


def run_permanent_bonus():
    """Bônus permanente (ver missions.permanent_bonus): some com marco nenhum
    batido, soma 5% por marco batido, NUNCA desconta, e entra multiplicado
    com o bônus de sequência na hora de gravar os pontos."""
    with tempfile.TemporaryDirectory() as tmp:
        db.DB_PATH = Path(tmp) / "test_permanent_bonus.db"
        db.init_db()
        import missions
        import settings

        assert missions.permanent_bonus() == 0.0, "sem marco nenhum batido, sem bônus"

        # bate só o marco de sequência (best_streak >= 100)
        settings.set_best_streak("diaria", 100)
        assert missions.permanent_bonus() == 0.05

        # bate também o de nível (level_info deriva de total_xp — soma pontos
        # crus direto no histórico, sem precisar completar 100+ missões de verdade)
        conn = db.get_connection()
        conn.execute(
            "INSERT INTO completions (mission_id, mission_name, date, points, obs, periodicity) "
            "VALUES (0, 'xp falso', '2024-01-01', 3500, '', 'diaria')"
        )
        conn.commit()
        conn.close()
        assert missions.level_info()["level"] >= 15, "3500 XP deveria bastar pro nível 15"
        assert missions.permanent_bonus() == 0.10, "dois marcos batidos: 5% + 5%"

        # o bônus permanente combina (multiplica) com o de sequência. Missão
        # mensal/difícil (25 pontos base): concluir já dá 1 mês de sequência,
        # que é o 1º degrau da mensal (1.25x) -> 25 * 1.25 * 1.10 = 34.375 -> 34
        missions.add_mission("Revisão mensal", "mensal", "dificil")
        m = missions.list_missions()[0]
        missions.complete_mission(m["id"])
        hoje = date.today().isoformat()
        conn = db.get_connection()
        pontos = conn.execute(
            "SELECT points FROM completions WHERE mission_id = ? AND date = ?", (m["id"], hoje),
        ).fetchone()["points"]
        conn.close()
        assert pontos == round(25 * 1.25 * 1.10) == 34, \
            f"25 pontos x 1.25 (sequência mensal) x 1.10 (bônus permanente) deveria virar 34, veio {pontos}"

        print("OK — bônus permanente passou")


def run_complete_mission_freeze_cap():
    """complete_mission tem que enxergar a MESMA sequência que a tela de stats
    pra multiplicar os pontos — ou seja, respeitar o teto de congelamentos do
    usuário (Premium / Modo Sem Penalidade), não o teto grátis fixo. Regressão
    de um bug onde o multiplicador aplicado ficava abaixo do degrau exibido."""
    def _cenario(nome, cap, pontos_esperados):
        with tempfile.TemporaryDirectory() as tmp:
            db.DB_PATH = Path(tmp) / f"{nome}.db"
            db.init_db()
            import missions

            # today fixo no meio do mês (ver _FixedToday): o cenário grátis
            # ("perdoa today-1, trava em today-2") precisa dos dois no mesmo
            # mês. complete_mission usa date.today() por dentro -> patch o módulo.
            missions.date = _FixedToday
            today = missions.date.today()
            missions.add_mission("Meditar", "diaria", "media")  # 2 pontos base
            m = missions.list_missions()[0]
            conn = db.get_connection()
            # conclusões reais de today-3 até today-12 (10 dias seguidos)
            for i in range(3, 13):
                conn.execute(
                    "INSERT INTO completions (mission_id, mission_name, date, points, obs, periodicity) "
                    "VALUES (?, ?, ?, ?, ?, 'diaria')",
                    (m["id"], "Meditar", (today - timedelta(days=i)).isoformat(), 2, ""),
                )
            conn.commit()
            conn.close()
            # buracos em today-1 e today-2, ainda NÃO congelados (nenhuma
            # chamada a current_streak antes desta)
            missions.complete_mission(m["id"], max_freezes_per_month=cap)
            conn = db.get_connection()
            row = conn.execute(
                "SELECT points FROM completions WHERE mission_id = ? AND date = ?",
                (m["id"], today.isoformat()),
            ).fetchone()
            conn.close()
            assert row["points"] == pontos_esperados, \
                f"{nome}: esperava {pontos_esperados} pts, veio {row['points']}"

    # teto grátis (1): só perdoa today-1, trava em today-2 -> sequência 2 -> mult 1.0 -> 2 pts crus
    _cenario("free", 1, 2)
    # sem limite (Modo Sem Penalidade): perdoa today-1/2, alcança os 10 dias reais
    # -> sequência 13 -> mult 1.5 -> round(2 * 1.5) = 3
    _cenario("no_penalty", None, 3)

    import missions
    missions.date = date  # restaura (as próximas funções usam datas explícitas, mas fica limpo)
    print("OK — complete_mission respeita o teto de congelamentos do usuário")


def run_work_cycle():
    """Missão "nos meus dias de folga" (ciclo pessoal, ver missions._cycle_off_today)
    — escalas rotativas tipo 12x36 (ciclo de 2, 1 dia de folga)."""
    with tempfile.TemporaryDirectory() as tmp:
        db.DB_PATH = Path(tmp) / "test_cycle.db"
        db.init_db()
        import missions
        import settings

        anchor = date(2026, 1, 1)  # 1/jan = dia 0 do ciclo (trabalho); 2/jan = dia 1 (folga)

        # sem ciclo configurado: _cycle_off_today sempre False (nunca esconde a missão sozinho)
        assert missions._cycle_off_today(today=anchor) is False

        settings.set_work_cycle(enabled=True, length=2, off_days="1", today_cycle_day=1)
        conn = db.get_connection()
        conn.execute("UPDATE app_settings SET cycle_anchor_date = ? WHERE id = 1", (anchor.isoformat(),))
        conn.commit()
        conn.close()

        assert missions._cycle_off_today(today=anchor) is False, "dia 0 do ciclo é trabalho"
        assert missions._cycle_off_today(today=date(2026, 1, 2)) is True, "dia 1 do ciclo é folga"
        assert missions._cycle_off_today(today=date(2026, 1, 3)) is False, "dia 2 = dia 0 de novo (ciclo de 2)"
        assert missions._cycle_off_today(today=date(2026, 1, 4)) is True, "dia 3 = dia 1 de novo"

        missions.add_mission("Academia", "diaria", "media", follow_cycle=True)
        m = missions.list_missions()[0]
        assert missions.is_scheduled_today(m, today=anchor) is False
        assert missions.is_scheduled_today(m, today=date(2026, 1, 2)) is True

        # ciclo com lixo no banco (backup de terceiro restaurado) não pode
        # derrubar o app: settings.get_settings sanea, aqui vira "sem ciclo"
        conn = db.get_connection()
        conn.execute(
            "UPDATE app_settings SET cycle_length = ?, cycle_off_days = ?, cycle_anchor_date = ? WHERE id = 1",
            ("x", "x", "x"),
        )
        conn.commit()
        conn.close()
        assert missions._cycle_off_today(today=anchor) is False, "valor inválido não pode estourar ValueError"
        # Aqui o TAMANHO é inválido, e é só nesse caso que o ciclo é desligado
        # (settings._cycle_values): a missão volta a valer todo dia em vez de
        # sumir. Deliberado — deixar o ciclo ligado com um tamanho inventado
        # faria um backup hostil esconder missões por um ciclo que o usuário
        # nunca escolheu.
        #
        # ATENÇÃO: isso NÃO vale pra corrupção em geral. Com tamanho VÁLIDO e
        # lixo só em off_days/anchor, o ciclo continua ligado e as missões
        # "follow_cycle" ficam escondidas (fail-closed). Não é regressão nem
        # brecha nova: quem escreve no banco chega no mesmo estado com valores
        # perfeitamente válidos — a corrupção cai em cycle_off_days vazio, que
        # é exatamente o que Ajustes grava quando nenhum dia é marcado
        # (main._selected_cycle_off_days devolve ""). E dá pra desfazer lá.
        assert settings.get_settings()["cycle_enabled"] is False
        assert missions.is_scheduled_today(m, today=anchor) is True

        # desligando o ciclo, a missão passa a valer todo dia (fail-open)
        settings.set_work_cycle(enabled=False, length=2, off_days="1", today_cycle_day=1)
        assert missions.is_scheduled_today(m, today=anchor) is True

        print("OK — ciclo pessoal (escala rotativa) passou")


def run_streak_survives_deleted_missions():
    """Apagar TODAS as missões diárias não pode travar current_streak com
    OverflowError — bug real reportado: sem missão diária nenhuma,
    scheduled=0 todo dia faz day_ok() sempre True (ver _period_ok), e o
    piso de earliest_done só era checado no ramo "dia não bateu" — o laço
    nunca chegava lá e decrementava o dia pra sempre até estourar date.min."""
    with tempfile.TemporaryDirectory() as tmp:
        db.DB_PATH = Path(tmp) / "test.db"
        db.init_db()
        import missions

        today = date(2024, 3, 10)
        missions.add_mission("Beber água", "diaria", "facil")
        m = missions.list_missions()[0]

        conn = db.get_connection()
        conn.execute(
            "INSERT INTO completions (mission_id, mission_name, date, points, obs) VALUES (?, ?, ?, ?, ?)",
            (m["id"], "Beber água", (today - timedelta(days=5)).isoformat(), 1, ""),
        )
        conn.commit()
        conn.close()

        missions.remove_mission(m["id"])

        streak = missions.current_streak(today=today)
        assert streak == 6, streak  # today..today-5 inclusive, sem missão ativa "ok" todo dia

        print("OK — sequência sobrevive a apagar todas as missões diárias")


if __name__ == "__main__":
    run()
    run_premium_freeze_cap()
    run_complete_mission_freeze_cap()
    run_level_and_mission_limit()
    run_challenge_multiplier()
    run_permanent_bonus()
    run_work_cycle()
    run_streak_survives_deleted_missions()
