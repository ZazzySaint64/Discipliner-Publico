"""Texto do lembrete diário — fonte única, compartilhada entre o app
(`main.App._reminder_body`) e o serviço (`service_reminder._corpo`).

Antes cada um tinha a própria cópia da lógica e do número de mensagens
(`REMINDER_MESSAGE_COUNT` escrito nos dois, "espelha main" num comentário):
mexer num e esquecer o outro fazia app e serviço mandarem textos diferentes no
mesmo dia. Agora os dois chamam daqui.

Sem Kivy de propósito: o serviço roda num processo sem interface e não pode
importar Kivy (ver service_reminder.py).
"""
from datetime import date

import i18n

# quantas mensagens reminder_msg_01..NN existem em i18n (frases curtas e
# diretas, sem referência a filme/jogo). Mexeu aqui, tem que existir a chave nos 5 idiomas —
# test_confirm_delete.run_pool cobra.
MESSAGE_COUNT = 25


def daily_body(pending, streak, lang, today=None):
    """Corpo do lembrete diário.

    A mensagem é escolhida PELO DIA (não sorteada): assim o app pode ser morto e
    reaberto que a do dia é a mesma, e ela troca sozinha a cada dia. Com
    sequência em andamento, lista o que falta — é o que faz a pessoa abrir o app.

    `pending`: lista de nomes de missões pendentes. `today`: só pros testes.
    """
    dia = today or date.today()
    i = dia.toordinal() % MESSAGE_COUNT + 1
    body = i18n.t(f"reminder_msg_{i:02d}", lang)
    if streak > 0 and pending:
        body += " " + i18n.t("reminder_streak_risk_body", lang) + " " + ", ".join(pending)
    return body


def demo():
    from datetime import date as _d

    a = daily_body(["Ler"], 3, "pt", today=_d(2026, 9, 8))
    b = daily_body(["Ler"], 3, "pt", today=_d(2026, 9, 8))
    assert a == b, "mesma data tem que dar a mesma mensagem"
    c = daily_body(["Ler"], 3, "pt", today=_d(2026, 9, 9))
    assert c != a or MESSAGE_COUNT == 1, "dia seguinte deveria trocar a mensagem"
    # sem sequência: só a frase, sem a lista de pendências
    d = daily_body(["Ler", "Correr"], 0, "pt", today=_d(2026, 9, 8))
    assert "Ler" not in d and "Correr" not in d
    # com sequência mas nada pendente: idem
    e = daily_body([], 5, "pt", today=_d(2026, 9, 8))
    assert i18n.t("reminder_streak_risk_body", "pt") not in e
    print("OK — reminder_text.daily_body")


if __name__ == "__main__":
    demo()
