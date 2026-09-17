"""Cliente HTTP fino pro Supabase (Auth + REST), só com urllib da stdlib —
sem SDK novo pro python-for-android ter que compilar/empacotar pro Android.

SUPABASE_URL/SUPABASE_ANON_KEY são valores PÚBLICOS de propósito: quem
protege os dados não é o sigilo da anon key, é o RLS configurado no banco
(ver supabase_schema.sql) — é assim que o Supabase foi desenhado pra
funcionar embutido num app cliente. A "service_role" key (essa sim secreta)
nunca entra aqui.
"""
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

import certifi

SUPABASE_URL = "https://cjpqgwfwhucmqwokpqom.supabase.co"
SUPABASE_ANON_KEY = "sb_publishable_Ks7U18SvJtS5v1SNPB7KTA_OTlCf4Pd"

# ponytail: mapeados aqui pra account.py poder traduzir os mais comuns (ver
# ERROR_KEY_MAP em account.py); mensagem crua da API é o fallback pras outras.
_TIMEOUT = 10

# Python compilado pro Android (python-for-android) geralmente não acha o
# repositório de certificados raiz do sistema operacional, então o "ssl"
# padrão falha a validação de QUALQUER https:// — e isso cai no mesmo
# except URLError lá embaixo, virando "sem conexão com a internet" mesmo
# com rede normal. Usa o bundle da lib certifi explicitamente em vez de
# depender do que o SO consegue achar sozinho.
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


class SupabaseError(Exception):
    """Erro devolvido pela API do Supabase — args[0] já é uma mensagem (em
    inglês, como a API manda) pronta pra mostrar se não houver tradução.
    status_code (None se não veio de um HTTPError, ex.: falha de rede) deixa
    quem chama distinguir "404 = ainda não existe" de erro de verdade."""

    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def _request(method, url, body=None, access_token=None, extra_headers=None, raw_response=False):
    """body: dict vira JSON; bytes/bytearray vai cru (ver upload_backup, que
    manda o .db inteiro). raw_response=True devolve os bytes crus da resposta
    em vez de tentar decodificar como JSON (ver download_backup)."""
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {access_token or SUPABASE_ANON_KEY}",
    }
    if isinstance(body, (bytes, bytearray)):
        data = bytes(body)
        headers["Content-Type"] = "application/octet-stream"
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    else:
        data = None
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT, context=_SSL_CONTEXT) as resp:
            raw = resp.read()
            if raw_response:
                return raw
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = {}
        msg = (
            payload.get("error_description") or payload.get("msg")
            or payload.get("message") or payload.get("error")
            or raw.decode("utf-8", "ignore") or str(e)
        )
        raise SupabaseError(msg, status_code=e.code) from e
    except urllib.error.URLError as e:
        # motivo cru só no log (ex.: "adb logcat"/log do Kivy) — a mensagem
        # pro usuário continua a genérica traduzida (ver ERROR_KEY_MAP)
        print(f"[supabase] falha de rede em {url}: {e.reason!r}")
        raise SupabaseError("network_error") from e


# --- Auth (GoTrue) ---

def sign_up(email, password, name, redirect_to=None):
    """redirect_to: pra onde o link de confirmação de e-mail leva de volta.
    No Android é o deep link do app (discipliner://login-callback, ver
    account.EMAIL_CONFIRM_DEEPLINK); sem ele o GoTrue usa a "Site URL" do
    projeto. Precisa estar na allowlist de Redirect URLs do Supabase."""
    url = f"{SUPABASE_URL}/auth/v1/signup"
    if redirect_to:
        url += "?redirect_to=" + urllib.parse.quote(redirect_to, safe="")
    return _request("POST", url, {"email": email, "password": password, "data": {"name": name}})


def get_user(access_token):
    """Dados do usuário logado (GoTrue /user) — usado pra montar a sessão a
    partir só dos tokens do deep link (ver account.complete_deeplink_login)."""
    return _request("GET", f"{SUPABASE_URL}/auth/v1/user", access_token=access_token)


def sign_in(email, password):
    return _request(
        "POST", f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        {"email": email, "password": password},
    )


def refresh_session(refresh_token):
    return _request(
        "POST", f"{SUPABASE_URL}/auth/v1/token?grant_type=refresh_token",
        {"refresh_token": refresh_token},
    )


def sign_out(access_token):
    _request("POST", f"{SUPABASE_URL}/auth/v1/logout", {}, access_token=access_token)


def recover_password(email, redirect_to=None):
    """E-mail de redefinição de senha. redirect_to: pra onde o link leva depois
    de validado (no Android, o deep link da tela de senha nova — ver
    account.RESET_PASSWORD_DEEPLINK). Precisa estar na allowlist de Redirect URLs."""
    url = f"{SUPABASE_URL}/auth/v1/recover"
    if redirect_to:
        url += "?redirect_to=" + urllib.parse.quote(redirect_to, safe="")
    _request("POST", url, {"email": email})


def send_email_code(email, redirect_to=None):
    """E-mail "Magic Link" (link + código de uso único) pra uma conta que JÁ
    existe (create_user=False: nunca cadastra ninguém por aqui). O link
    (redirect_to) é o login; o código ({{ .Token }}) confirma apagar a conta."""
    url = f"{SUPABASE_URL}/auth/v1/otp"
    if redirect_to:
        url += "?redirect_to=" + urllib.parse.quote(redirect_to, safe="")
    _request("POST", url, {"email": email, "create_user": False})


def verify_email_code(email, code):
    """Troca o código por uma sessão NOVA — cujo JWT carrega amr=otp, a prova
    que a Edge Function delete-account exige."""
    return _request("POST", f"{SUPABASE_URL}/auth/v1/verify",
                    {"type": "email", "email": email, "token": code})


def update_user(access_token, **fields):
    """fields: email=, password=, data={"name": ...} — só manda o que vier."""
    return _request("PUT", f"{SUPABASE_URL}/auth/v1/user", fields, access_token=access_token)


# --- Edge Functions ---

def invoke_function(name, access_token, body=None):
    """Chama uma Edge Function do projeto (ex.: create-pix-payment) usando o
    JWT de QUEM está chamando (não a anon key) — assim a function sabe de
    quem é o pedido sozinha, sem precisar confiar em nada que o app mande."""
    return _request("POST", f"{SUPABASE_URL}/functions/v1/{name}", body=body or {}, access_token=access_token)


# --- REST (PostgREST) ---

# tabelas que o app pode ler via select_own_row — o nome entra cru na URL
# (PostgREST usa o path como nome da tabela), então fica preso a um allowlist
# pra nunca virar um "table" arbitrário vindo de fora. O RLS ainda barra
# tudo que não for do próprio usuário, isso é só defesa em profundidade.
_READABLE_TABLES = {"purchases"}


def report_crash(payload):
    """INSERT anônimo em crash_reports (ver supabase_schema.sql / crash_reporter.py).
    Só a anon key — o RLS deixa QUALQUER um inserir e NINGUÉM ler por ela.
    Levanta SupabaseError como qualquer _request; quem chama já está tratando
    um crash e engole isso."""
    _request(
        "POST", f"{SUPABASE_URL}/rest/v1/crash_reports",
        body=payload, extra_headers={"Prefer": "return=minimal"},
    )


def report_activity(payload):
    """INSERT anônimo em app_activity (ver telemetry.py). Mesmo modelo do
    crash_reports: só INSERT, ninguém lê pela anon key.

    INSERT simples, não upsert: `on_conflict` do PostgREST exige policy de
    SELECT, que abriria a tabela pra leitura. Duplicado do mesmo
    aparelho/dia/tipo volta 409 (chave primária) — isso é "já registrado", não
    erro."""
    try:
        _request("POST", f"{SUPABASE_URL}/rest/v1/app_activity", body=payload,
                 extra_headers={"Prefer": "return=minimal"})
    except SupabaseError as e:
        if e.status_code != 409:
            raise


def select_own_row(table, access_token, columns="*"):
    """SELECT * FROM <table> WHERE user_id = auth.uid() LIMIT 1 — o RLS de
    supabase_schema.sql já filtra pra só a própria linha, então não precisa
    (nem dá, com a anon key) passar um WHERE explícito. Devolve o dict da
    linha, ou None se não existir (ex.: ainda não comprou o Premium)."""
    if table not in _READABLE_TABLES:
        raise ValueError(f"tabela não permitida em select_own_row: {table!r}")
    rows = _request(
        "GET", f"{SUPABASE_URL}/rest/v1/{table}?select={columns}&limit=1",
        access_token=access_token,
    )
    return rows[0] if rows else None


# --- Storage (backup na nuvem — ver backup.py) ---
# bucket "backups", 1 arquivo por conta em backups/<user_id>/daily_quest.db —
# path prefixado com o user_id bate com a política de RLS do bucket
# (supabase_schema.sql), que só deixa cada um mexer na própria pasta.

def _backup_path(user_id):
    # user_id sempre é o UUID da própria sessão (vem do JWT, não do input do
    # app), e o RLS do bucket ainda exige que o 1º segmento == auth.uid(). O
    # quote() é só pra garantir que nada no id escape do segmento de path.
    return f"{SUPABASE_URL}/storage/v1/object/backups/{urllib.parse.quote(str(user_id), safe='')}/daily_quest.db"


def upload_backup(access_token, user_id, file_bytes):
    """Sobrescreve o backup na nuvem dessa conta (PUT = upsert, cria ou
    substitui). Levanta SupabaseError se a API recusar."""
    _request(
        "PUT", _backup_path(user_id),
        body=file_bytes, access_token=access_token, extra_headers={"x-upsert": "true"},
    )


def download_backup(access_token, user_id):
    """Bytes do backup na nuvem dessa conta, ou None se ainda não existir
    nenhum (não é erro — conta nova, ou nunca fez backup na nuvem antes)."""
    try:
        return _request(
            "GET", _backup_path(user_id),
            access_token=access_token, raw_response=True,
        )
    except SupabaseError as e:
        if e.status_code in (400, 404):
            return None
        raise
