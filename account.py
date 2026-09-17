"""Conta do usuário — agora de verdade, via Supabase Auth (supabase_client.py).
Este módulo só guarda um CACHE local da sessão (tabela local_session) pra não
precisar logar de novo a cada abertura do app; quem manda em senha, e-mail e
confirmação é o Supabase.

- "Continuar com Google" segue desabilitado: precisa ativar o provider Google
  no painel do Supabase (Authentication → Providers) com credenciais OAuth do
  Google Cloud Console — configuração externa, não é algo que o código decide.
- Confirmação de CADASTRO é por link (o Supabase manda o e-mail, o link volta
  pro app pelo deep link — ver EMAIL_CONFIRM_DEEPLINK/complete_deeplink_login):
  não precisa mexer no template do painel (o padrão do Supabase já manda
  link), e editar o HTML puro do template ("Source") exige SMTP próprio
  configurado — sem domínio, não vale a complicação só pra trocar link por
  código aqui.
- LOGIN também é por link: depois da senha, `/auth/v1/otp` manda o e-mail
  "Magic Link" com redirect pro mesmo deep link (ver login). O template
  Magic Link precisa ter {{ .ConfirmationURL }} (link do login) e
  {{ .Token }} (código de apagar conta, ver request_delete_code).
"""
import time
import urllib.parse
import webbrowser

import database as db
import settings
import supabase_client as sb

REFRESH_MARGIN_SECONDS = 60  # renova um pouco antes de expirar, não em cima da hora

# Deep link pro qual o e-mail de confirmação de conta leva de volta (Android):
# o Supabase 302 do link de confirmação cai neste scheme, o Android abre o app
# e deeplink.py extrai os tokens do fragmento (#access_token=...&refresh_token=...).
# Precisa estar na allowlist de Redirect URLs do projeto Supabase.
EMAIL_CONFIRM_DEEPLINK = "discipliner://login-callback"

# link do e-mail de senha nova volta pra tela dedicada do app (main._on_reset_deeplink).
# Também precisa estar nas Redirect URLs do painel do Supabase.
RESET_PASSWORD_DEEPLINK = "discipliner://reset-password"

# Payment Link do Stripe pra pagar com cartão (ver README > Monetização).
# PRODUÇÃO (modo Live): RUPDEV / "Discipliner Premium" / US$ 3,00 — sem o
# prefixo "test_" na URL. O modo Live tem catálogo, webhook e chaves próprios;
# ver README > Monetização pros secrets do stripe-webhook (STRIPE_SECRET_KEY
# sk_live_..., STRIPE_WEBHOOK_SECRET whsec_... do endpoint Live).
# Pix NÃO passa por aqui — a conta Stripe usada neste projeto não tem Pix
# liberado (precisa de aprovação específica do Stripe pro método, além da
# conta já ser brasileira); ver open_pix_purchase_page, que usa o Mercado Pago.
STRIPE_PAYMENT_LINK_USD = "https://buy.stripe.com/4gMcN71JWeUJclJaRy7IY00"

# mapeia as mensagens mais comuns da API pra uma chave i18n traduzível; o que
# não estiver aqui cai pra ser mostrado cru mesmo (em inglês, vindo da API)
ERROR_KEY_MAP = {
    "User already registered": "err_email_taken",
    "Invalid login credentials": "err_invalid_credentials",
    "Email not confirmed": "err_email_not_confirmed",
    "network_error": "err_network",
    # ainda alcancavel pelo link de recuperacao de senha / deep link expirado
    "Token has expired or is invalid": "err_link_invalid",
}


def _translate_error(exc):
    key = ERROR_KEY_MAP.get(str(exc))
    return key if key else str(exc)


def _normalize_email(value):
    """Pra comparar e-mail com e-mail (o que a pessoa digitou vs. o que o
    GoTrue devolve) sem tropeçar em espaço/maiúscula."""
    return (value or "").strip().casefold()


def validate_password(password):
    """Retorna (True, "") se válida, ou (False, "chave_i18n") se não — quem chama
    traduz a chave (ver i18n.t) pro idioma atual, aqui não sabemos qual é."""
    import re
    if len(password) < 6:
        return False, "err_min_length"
    if not re.search(r"[a-z]", password):
        return False, "err_lowercase"
    if not re.search(r"[A-Z]", password):
        return False, "err_uppercase"
    if not re.search(r"\d", password):
        return False, "err_number"
    if not re.search(r"[^a-zA-Z0-9]", password):
        return False, "err_symbol"
    return True, ""


def _save_session(auth_response):
    # resposta da API pode vir num formato inesperado (body vazio/null, erro
    # 200 sem tokens, mudança na API). Sem esta checagem, um KeyError/TypeError
    # cru vazava até a UI como "'user'" ou "'NoneType'..." — vira err_network,
    # que os chamadores já traduzem (ver _translate_error / ERROR_KEY_MAP).
    user = auth_response.get("user") if isinstance(auth_response, dict) else None
    if (not isinstance(user, dict)
            or not {"id", "email"} <= user.keys()
            or not {"access_token", "refresh_token", "expires_in"} <= auth_response.keys()):
        raise sb.SupabaseError("network_error")
    conn = db.get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO local_session "
        "(id, user_id, email, name, access_token, refresh_token, expires_at) "
        "VALUES (1, ?, ?, ?, ?, ?, ?)",
        (
            user["id"], user["email"], (user.get("user_metadata") or {}).get("name", ""),
            auth_response["access_token"], auth_response["refresh_token"],
            int(time.time()) + int(auth_response["expires_in"]),  # às vezes vem como string
        ),
    )
    conn.commit()
    conn.close()


def restore_session_row(session):
    """Reescreve local_session com esses valores exatos — usado depois de
    restaurar um backup da nuvem (ver backup.import_from_cloud), que
    sobrescreve o arquivo do banco INTEIRO, essa tabela inclusive, com o
    retrato de outro aparelho. Sem isso, restaurar um backup deslogaria a
    conta atual (ou pior, deixaria o token de sessão de outro aparelho)."""
    conn = db.get_connection()
    conn.execute(
        "INSERT OR REPLACE INTO local_session "
        "(id, user_id, email, name, access_token, refresh_token, expires_at) "
        "VALUES (1, ?, ?, ?, ?, ?, ?)",
        (
            session["user_id"], session["email"], session["name"],
            session["access_token"], session["refresh_token"], session["expires_at"],
        ),
    )
    conn.commit()
    conn.close()


def _clear_session():
    conn = db.get_connection()
    conn.execute("DELETE FROM local_session WHERE id = 1")
    conn.commit()
    conn.close()
    # is_premium é cache LOCAL (device), não por conta — qualquer fim de sessão
    # (logout explícito OU auto-logout quando o refresh_token expira/rotaciona)
    # tem que zerar, senão sobra "Premium sem conta" e o próximo login/visitante
    # herda. sync_premium_status() religa no próximo login se a compra existir.
    settings.set_premium(False)


def _session_row():
    conn = db.get_connection()
    row = conn.execute("SELECT * FROM local_session WHERE id = 1").fetchone()
    conn.close()
    return row


def current_session():
    """Sessão ativa (dict com user_id/email/name/access_token) ou None. Renova
    sozinha via refresh_token quando o access_token tá perto de expirar; se o
    refresh falhar (revogado, expirou de vez), desloga localmente."""
    row = _session_row()
    if row is None or not row["access_token"]:
        return None
    if row["expires_at"] - int(time.time()) < REFRESH_MARGIN_SECONDS:
        try:
            _save_session(sb.refresh_session(row["refresh_token"]))
        except sb.SupabaseError:
            _clear_session()
            return None
        row = _session_row()
    return dict(row)


def sign_up(name, email, password):
    """Levanta ValueError(chave_i18n) se a senha não cumprir os requisitos, ou
    Exception(msg) se a API recusar (e-mail já cadastrado, etc.). Retorna True
    se já logou de cara (confirmação de e-mail desligada no projeto) ou False
    se precisa confirmar o e-mail antes (caso normal)."""
    ok, reason = validate_password(password)
    if not ok:
        raise ValueError(reason)
    try:
        resp = sb.sign_up(email, password, name, redirect_to=EMAIL_CONFIRM_DEEPLINK)
        if isinstance(resp, dict) and "access_token" in resp:
            _save_session(resp)  # _save_session pode levantar SupabaseError
            settings.set_pending_signup_email("")  # já logou, não espera link nenhum
            return True
    except sb.SupabaseError as e:
        raise Exception(_translate_error(e)) from e
    # confirmação pendente: anota QUAL e-mail este aparelho pediu pra
    # confirmar — é o único que complete_deeplink_login vai aceitar depois
    settings.set_pending_signup_email(_normalize_email(email))
    return False  # sem token = confirmação de e-mail pendente (caso normal)


def complete_deeplink_login(access_token, refresh_token, expires_in):
    """Monta e salva a sessão a partir dos tokens que vieram no fragmento do
    deep link de confirmação de e-mail (ver deeplink.py). Levanta Exception se
    falhar.

    O deep link (discipliner://login-callback) é um canal NÃO confiável: o
    intent-filter é BROWSABLE, então qualquer app instalado ou página web pode
    disparar a URI com os tokens que quiser. sb.get_user() só prova que o
    token é válido — não que seja o token DESTA pessoa. Sem mais nada, um
    token da conta do atacante virava a sessão local e o próximo "Backup na
    nuvem" mandava o banco da vítima pra pasta dele.

    Por isso só aceita o link quando o próprio app começou o fluxo: tem que
    existir um cadastro aguardando confirmação (settings.pending_signup_email,
    gravado por sign_up) e o token tem que ser justamente daquele e-mail. O
    marcador é de uso único — some assim que o login acontece."""
    pending = _normalize_email(settings.get_settings()["pending_signup_email"])
    if not pending:
        # ninguém pediu confirmação neste aparelho: link forjado ou já usado
        raise Exception("deep link inesperado: nenhum cadastro aguardando confirmação")
    try:
        user = sb.get_user(access_token)
    except sb.SupabaseError as e:
        raise Exception(_translate_error(e)) from e
    if _normalize_email(user.get("email") if isinstance(user, dict) else None) != pending:
        raise Exception("deep link de outra conta: não é o cadastro aguardando confirmação")
    _save_session({
        "user": user,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": int(expires_in),
    })
    settings.set_pending_signup_email("")  # consumido: o link vale uma vez só


def login(email, password):
    """Confere a senha e manda um link de entrada pro e-mail. Tocar no link
    abre o app (EMAIL_CONFIRM_DEEPLINK) e complete_deeplink_login entra
    sozinho — senha sozinha não loga. Anota o e-mail no mesmo marcador do
    cadastro: é o único cujo link o deep link aceita. Levanta
    Exception(msg_ou_chave) se a senha for inválida."""
    try:
        sb.sign_in(email, password)  # só valida a senha; essa sessão é descartada
        sb.send_email_code(email, redirect_to=EMAIL_CONFIRM_DEEPLINK)
    except sb.SupabaseError as e:
        raise Exception(_translate_error(e)) from e
    settings.set_pending_signup_email(_normalize_email(email))


def logout():
    row = _session_row()
    if row is not None and row["access_token"]:
        try:
            sb.sign_out(row["access_token"])
        except sb.SupabaseError:
            pass  # mesmo se a API falhar (sem internet etc.), desloga local
    _clear_session()  # já zera o cache local de Premium (ver _clear_session)


def request_password_reset(email):
    """Manda o e-mail de senha nova. O link volta pro app
    (RESET_PASSWORD_DEEPLINK), direto na tela de senha nova — e anota qual
    e-mail ESTE aparelho pediu, o único cujo link validar_link_reset aceita."""
    try:
        sb.recover_password(email, redirect_to=RESET_PASSWORD_DEEPLINK)
    except sb.SupabaseError as e:
        raise Exception(_translate_error(e)) from e
    settings.set_pending_reset_email(_normalize_email(email))


def _usuario_do_link_reset(access_token):
    """Usuário dono do token do link de senha nova — só se este aparelho pediu
    a redefinição e o token é daquele e-mail. Mesmo motivo do
    complete_deeplink_login: discipliner://reset-password é BROWSABLE, qualquer
    app ou página dispara a URI com o token que quiser."""
    pending = _normalize_email(settings.get_settings()["pending_reset_email"])
    if not pending:
        raise Exception("reset_link_invalid")
    try:
        user = sb.get_user(access_token)
    except sb.SupabaseError as e:
        raise Exception("reset_link_invalid") from e
    if not isinstance(user, dict) or _normalize_email(user.get("email")) != pending:
        raise Exception("reset_link_invalid")
    return user


def validar_link_reset(access_token):
    """E-mail da conta do link, ou Exception("reset_link_invalid")."""
    return _usuario_do_link_reset(access_token)["email"]


def complete_password_reset(access_token, refresh_token, expires_in, new_password):
    """Grava a senha nova com o token do link. Levanta ValueError(chave) se a
    senha for fraca, Exception(chave) se o link não valer. Quem estava
    deslogado (esqueci a senha na tela de login) sai daqui já logado."""
    ok, reason = validate_password(new_password)
    if not ok:
        raise ValueError(reason)
    user = _usuario_do_link_reset(access_token)
    try:
        sb.update_user(access_token, password=new_password)
    except sb.SupabaseError as e:
        raise Exception(_translate_error(e)) from e
    settings.set_pending_reset_email("")  # o link vale uma vez só
    if current_session() is None:
        _save_session({"user": user, "access_token": access_token,
                       "refresh_token": refresh_token, "expires_in": int(expires_in)})


def update_name(name):
    """Troca o nome de usuário (o e-mail não muda por aqui)."""
    session = current_session()
    if session is None:
        return
    try:
        sb.update_user(session["access_token"], data={"name": name})
    except sb.SupabaseError as e:
        raise Exception(_translate_error(e)) from e
    conn = db.get_connection()
    conn.execute("UPDATE local_session SET name = ? WHERE id = 1", (name,))
    conn.commit()
    conn.close()


def request_delete_code():
    """1º passo de apagar a conta: código de uso único no e-mail da conta
    (template "Magic Link" do painel explica o que vai ser apagado). Devolve o
    e-mail, pra tela mostrar pra onde foi."""
    session = current_session()
    if session is None:
        raise Exception("err_network")
    try:
        sb.send_email_code(session["email"])
    except sb.SupabaseError as e:
        raise Exception(_translate_error(e)) from e
    return session["email"]


def delete_account(code):
    """2º passo: troca o código por uma sessão nova (prova de acesso ao e-mail
    AGORA), pede pra Edge Function delete-account apagar conta + backup +
    compra, e apaga tudo o que está neste aparelho. Código errado/expirado:
    Exception("err_code_invalid") e nada é apagado."""
    session = current_session()
    code = (code or "").strip()
    if session is None or not code.isdigit():
        raise Exception("err_code_invalid")
    try:
        nova = sb.verify_email_code(session["email"], code)
    except sb.SupabaseError as e:
        raise Exception("err_code_invalid") from e
    token = nova.get("access_token") if isinstance(nova, dict) else None
    if not token:
        raise Exception("err_code_invalid")
    try:
        sb.invoke_function("delete-account", token)
    except sb.SupabaseError as e:
        raise Exception(_translate_error(e)) from e
    _apagar_dados_locais()


def _apagar_dados_locais():
    """Some com o banco local inteiro (missões, sequência, pontos, sessão,
    preferências) e a cópia de segurança do restore, e recria vazio — o app
    volta a ser recém-instalado."""
    import missions

    for arquivo in (db.DB_PATH, db.DB_PATH.with_name(db.DB_PATH.name + "-wal"),
                    db.DB_PATH.with_name(db.DB_PATH.name + "-shm"),
                    db.DB_PATH.with_suffix(".antes-da-nuvem.db")):
        arquivo.unlink(missing_ok=True)
    db.init_db()
    missions._invalidate_missions_cache()


# --- Premium via Stripe (ver README > Monetização — sem Google Play Billing
# de propósito, evita a taxa de US$ 25 de cadastro de desenvolvedor) ---

def open_purchase_page():
    """Abre o Payment Link do Stripe (cartão) no navegador do sistema
    (webbrowser é stdlib; no Android o python-for-android traduz isso pra um
    Intent nativo, sem precisar de WebView própria). client_reference_id é
    como a Edge Function do webhook (supabase/functions/stripe-webhook) sabe
    pra quem creditar a compra quando o pagamento confirmar — precisa estar
    logado. Pix é um fluxo separado, ver open_pix_purchase_page.

    PONTO DE TROCA PRA PLAY STORE: quando integrar o Google Play Billing, este
    é o método que muda — em vez de abrir uma URL, chamaria o BillingClient
    nativo. O resto do fluxo (tabela purchases, sync_premium_status) fica
    igual: o webhook novo só grava provider='play'."""
    session = current_session()
    if session is None:
        return False
    # encoda os dois: e-mail com "+"/"&" (RFC-válido) quebrava o parse dos
    # params do Stripe; user_id é UUID mas encodar não custa nada
    params = urllib.parse.urlencode({
        "client_reference_id": session["user_id"],
        "prefilled_email": session["email"],
    })
    webbrowser.open(f"{STRIPE_PAYMENT_LINK_USD}?{params}")
    return True


def open_pix_purchase_page():
    """Pede uma preferência de Checkout Pro nova pro Premium via Mercado Pago
    (Edge Function create-pix-payment, que tem o access token secreto do MP —
    nunca aqui) e abre no navegador do sistema — mesmo padrão de
    open_purchase_page (Stripe). Devolve True se abriu, False se não tiver
    sessão. Levanta Exception(msg) se a API recusar."""
    session = current_session()
    if session is None:
        return False
    try:
        resp = sb.invoke_function("create-pix-payment", session["access_token"])
    except sb.SupabaseError as e:
        raise Exception(str(e)) from e
    url = resp.get("checkout_url") if isinstance(resp, dict) else None
    if not url:
        raise Exception("network_error")  # resposta sem a URL de checkout
    webbrowser.open(url)
    return True


def sync_premium_status():
    """Confere no Supabase se já existe uma compra Premium validada pra essa
    conta (tabela purchases — só a Edge Function do webhook escreve nela, o
    app nunca escreve "comprei" sozinho). Só liga o cache local; nunca desliga
    sozinho (sem fluxo de reembolso ainda — ver README)."""
    session = current_session()
    if session is None:
        print("[premium] sync abortado: sem sessão ativa (current_session() = None)")
        return
    try:
        row = sb.select_own_row("purchases", session["access_token"])
    except sb.SupabaseError as e:
        print(f"[premium] sync falhou (rede/API): {e}")
        return  # sem internet ou API fora do ar — mantém o que já tinha em cache
    # Só o resultado, nunca o e-mail nem a linha de purchases: no Android o
    # stdout vai pro logcat, que qualquer app com READ_LOGS (e qualquer um com
    # o aparelho na mão via adb) lê. A linha inteira trazia junto o
    # purchase_token — o id do pagamento no Stripe/Mercado Pago — e o e-mail
    # da conta, que permite correlacionar/enumerar usuário.
    print(f"[premium] sync: compra {'encontrada' if row is not None else 'não encontrada'}")
    if row is not None:
        settings.set_premium(True)
