"""Self-check da reconquista: python test_reconquista.py (sem Kivy, só sqlite).

Avisa com 2, 5 e 14 dias sem missão e para; concluir zera; quem some muito
tempo recebe 1 aviso, não uma rajada; falha de notificação não gasta o aviso."""
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path


def run():
    with tempfile.TemporaryDirectory() as tmp:
        import database as db
        db.DB_PATH = Path(tmp) / "r.db"
        db.init_db()
        import i18n
        import notify
        import reconquista
        import settings

        def concluir(dia):
            conn = db.get_connection()
            conn.execute("INSERT INTO completions (mission_id, mission_name, date, points) "
                         "VALUES (1, 'Ler', ?, 10)", (dia.isoformat(),))
            conn.commit()
            conn.close()

        hoje = date.today()
        assert reconquista.aviso_devido(hoje) is None, "quem nunca concluiu não recebe aviso"
        assert reconquista.proximo_aviso(hoje) is None

        base = hoje - timedelta(days=30)
        concluir(base)
        assert reconquista.aviso_devido(base + timedelta(days=1)) is None, "1 dia ainda não é sumir"
        assert reconquista.proximo_aviso(base).date() == base + timedelta(days=2)

        # as 3 etapas, e depois para
        for dias, etapa in ((2, 0), (5, 1), (14, 2)):
            dia = base + timedelta(days=dias)
            assert reconquista.aviso_devido(dia - timedelta(days=1)) is None
            assert reconquista.aviso_devido(dia) == (dias, etapa), (dias, reconquista.aviso_devido(dia))
            reconquista.marcar_enviado(dias)
            assert reconquista.aviso_devido(dia) is None, "mesmo dia não repete"
        assert reconquista.aviso_devido(base + timedelta(days=60)) is None, "depois de 3 avisos, para"
        assert reconquista.proximo_aviso(base + timedelta(days=15)) is None

        # concluir de novo começa outra ausência
        volta = base + timedelta(days=20)
        concluir(volta)
        assert reconquista.aviso_devido(volta + timedelta(days=1)) is None
        assert reconquista.aviso_devido(volta + timedelta(days=2)) == (2, 0)

        # sumiu muito com o celular desligado: 1 aviso só, não 3 em dias seguidos
        longe = volta + timedelta(days=20)
        assert reconquista.aviso_devido(longe) == (20, 0)
        reconquista.marcar_enviado(20)
        assert reconquista.aviso_devido(longe + timedelta(days=1)) is None

        # checar(): hora certa, texto traduzido, id do lembrete diário, falha não marca
        settings.set_winback_state("")
        concluir(hoje - timedelta(days=5))  # a mais recente agora é de 5 dias atrás
        enviados = []
        notify.send = lambda t, c, notification_id=2, **k: enviados.append((t, c, notification_id)) or True
        cedo = datetime.combine(hoje, datetime.min.time()).replace(hour=6)
        assert not reconquista.checar(cedo), "antes do horário não avisa"
        noite = cedo.replace(hour=23)
        notify.send = lambda *a, **k: False
        assert not reconquista.checar(noite) and reconquista.aviso_devido(hoje), "notificação falhou: aviso não pode sumir"
        notify.send = lambda t, c, notification_id=2, **k: enviados.append((t, c, notification_id)) or True
        assert reconquista.checar(noite)
        assert not reconquista.checar(noite), "segundo acordar no mesmo dia não repete"
        assert len(enviados) == 1, enviados
        titulo, corpo, nid = enviados[0]
        assert nid == 2 and "5" in corpo and corpo == i18n.t("winback_body_0", "pt").format(dias=5), enviados[0]

        # textos existem em todos os idiomas e aceitam {dias}
        for lang in i18n.TRANSLATIONS:
            for etapa in range(len(reconquista.DIAS)):
                assert "9" in reconquista.texto(9, etapa, lang)[1], (lang, etapa)

        # estado corrompido (backup de terceiro) não quebra
        settings.set_winback_state("{lixo")
        reconquista.aviso_devido(hoje)
        reconquista.proximo_aviso(hoje)

    print("OK — reconquista: 2/5/14 dias e para, concluir zera, sem rajada, falha não gasta o aviso")


if __name__ == "__main__":
    run()
