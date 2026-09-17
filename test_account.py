"""Self-check: python test_account.py (não precisa do Kivy, só sqlite).

Troca as funções de rede de supabase_client por respostas falsas — testa a
lógica local (cache de sessão, expiração/renovação, tradução de erro) sem
depender de internet nem do projeto Supabase de verdade."""
import tempfile
import time
from pathlib import Path


def _session_payload(user_id="u1", email="eric@teste.com", name="Eric", expires_in=3600):
    return {
        "access_token": f"tok-{user_id}",
        "refresh_token": f"ref-{user_id}",
        "expires_in": expires_in,
        "user": {"id": user_id, "email": email, "user_metadata": {"name": name}},
    }


def _login(account, sb, email, password, user_id, name):
    """login() manda um link por e-mail; quem grava a sessão é o deep link
    (complete_deeplink_login). Testes que só querem uma sessão pronta passam
    pelos dois."""
    sb.sign_in = lambda e, p: {}
    sb.send_email_code = lambda e, redirect_to=None: None
    account.login(email, password)
    sb.get_user = lambda token, _uid=user_id, _e=email, _n=name: {"id": _uid, "email": _e, "user_metadata": {"name": _n}}
    account.complete_deeplink_login(f"tok-{user_id}", f"ref-{user_id}", "3600")


def run():
    with tempfile.TemporaryDirectory() as tmp:
        import database as db
        db.DB_PATH = Path(tmp) / "test.db"
        db.init_db()
        import account
        import supabase_client as sb

        # validação de senha: precisa de tudo (6+, minúscula, maiúscula, número, símbolo)
        casos_invalidos = ["abc12", "abcdef", "ABCDEF1!", "abcdef1!", "ABCDEF1!", "abcDEF1"]
        for senha in casos_invalidos:
            ok, motivo = account.validate_password(senha)
            assert ok is False, f"'{senha}' deveria ser inválida"
            assert motivo, "deveria explicar o motivo"
        ok, _ = account.validate_password("Abc123!@")
        assert ok is True, "essa senha cumpre todos os requisitos"

        # sign_up rejeita senha fraca antes de bater na rede
        sb.sign_up = lambda *a, **k: (_ for _ in ()).throw(AssertionError("não deveria chamar a rede"))
        try:
            account.sign_up("Eric", "eric@teste.com", "fraca")
            assert False, "deveria ter levantado ValueError"
        except ValueError:
            pass
        assert account.current_session() is None, "não deveria ter sessão nenhuma ainda"

        # sign_up com confirmação de e-mail pendente (comportamento padrão do projeto)
        sb.sign_up = lambda email, password, name, **k: {"id": "u1", "email": email, "aud": "authenticated"}
        confirmed = account.sign_up("Eric", "eric@teste.com", "Abc123!@")
        assert confirmed is False, "sem access_token na resposta = aguardando confirmação"
        assert account.current_session() is None, "não loga sozinho enquanto não confirmar"

        # sign_up já confirmado de cara (ex.: projeto com autoconfirm ligado)
        sb.sign_up = lambda email, password, name, **k: _session_payload(email=email, name=name)
        confirmed = account.sign_up("Eric", "eric2@teste.com", "Abc123!@")
        assert confirmed is True
        session = account.current_session()
        assert session is not None and session["email"] == "eric2@teste.com"

        # e-mail duplicado vira mensagem traduzível (err_email_taken)
        sb.sign_up = lambda *a, **k: (_ for _ in ()).throw(sb.SupabaseError("User already registered"))
        try:
            account.sign_up("Eric", "eric2@teste.com", "Abc123!@")
            assert False, "deveria ter levantado"
        except Exception as e:
            assert str(e) == "err_email_taken", str(e)

        # login: senha certa só manda o link (com redirect pro deep link do
        # app) e anota o e-mail — não loga sozinha
        account._clear_session()  # zera a sessão do eric2 (autoconfirm) acima, de propósito
        settings = account.settings
        settings.set_pending_signup_email("")
        enviado = {}
        sb.sign_in = lambda email, password: _session_payload(user_id="u2", email=email)
        sb.send_email_code = lambda email, redirect_to=None: enviado.update(email=email, redirect=redirect_to)
        account.login("Outro@teste.com", "Abc123!@")
        assert account.current_session() is None, "senha sozinha não pode logar — falta o link"
        assert enviado == {"email": "Outro@teste.com", "redirect": "discipliner://login-callback"}, enviado
        assert settings.get_settings()["pending_signup_email"] == "outro@teste.com"

        # link com token de OUTRA conta não entra
        sb.get_user = lambda token: {"id": "atk", "email": "atacante@evil.com", "user_metadata": {}}
        assert _falha(account.complete_deeplink_login, "ATK", "REF", "3600")
        assert account.current_session() is None

        # usuário da API num formato inesperado NÃO pode vazar KeyError cru
        sb.get_user = lambda token: {"email": "outro@teste.com"}  # sem id
        assert _falha(account.complete_deeplink_login, "X", "Y", "3600") == "network_error"
        assert account.current_session() is None

        # login grava sessão nova só depois do link certo
        _login(account, sb, "outro@teste.com", "Abc123!@", "u2", "Outro")
        session = account.current_session()
        assert session["user_id"] == "u2" and session["email"] == "outro@teste.com"

        # credenciais erradas (1º passo) viram mensagem traduzível e nem chegam a mandar código
        sb.sign_in = lambda *a, **k: (_ for _ in ()).throw(sb.SupabaseError("Invalid login credentials"))
        sb.send_email_code = lambda *a, **k: (_ for _ in ()).throw(AssertionError("senha errada não pode mandar código"))
        try:
            account.login("outro@teste.com", "errada")
            assert False, "deveria ter levantado"
        except Exception as e:
            assert str(e) == "err_invalid_credentials", str(e)
        # sessão anterior (login bem-sucedido) continua valendo, não foi apagada
        assert account.current_session() is not None

        # access_token perto de expirar: renova sozinho via refresh_token
        conn = db.get_connection()
        conn.execute("UPDATE local_session SET expires_at = ? WHERE id = 1", (int(time.time()) - 10,))
        conn.commit()
        conn.close()
        sb.refresh_session = lambda refresh_token: _session_payload(user_id="u2", email="outro@teste.com", name="Renovado")
        session = account.current_session()
        assert session["name"] == "Renovado", "deveria ter renovado sozinho"

        # refresh falhando (token revogado) desloga local — E zera o Premium
        # local (senão sobra "Premium sem conta"; auto-logout tem que se
        # comportar igual ao logout() explícito)
        import settings as _settings
        _settings.set_premium(True)
        conn = db.get_connection()
        conn.execute("UPDATE local_session SET expires_at = ? WHERE id = 1", (int(time.time()) - 10,))
        conn.commit()
        conn.close()
        sb.refresh_session = lambda *a, **k: (_ for _ in ()).throw(sb.SupabaseError("invalid refresh token"))
        assert account.current_session() is None
        assert _settings.get_settings()["is_premium"] is False, "auto-logout deveria zerar o cache local de Premium"

        # update_name só funciona com sessão ativa, e o e-mail não muda por aqui
        _login(account, sb, "perfil@teste.com", "Abc123!@", "u3", "Nome")
        sb.update_user = lambda access_token, **fields: {}
        account.update_name("Nome Novo")
        session = account.current_session()
        assert session["name"] == "Nome Novo" and session["email"] == "perfil@teste.com"

        # Premium via Stripe (ver README > Monetização) — precisa de sessão ativa
        import settings
        account._clear_session()  # zera a sessão do bloco de update_profile acima, de propósito
        assert account.open_purchase_page() is False, "sem sessão, não deveria nem tentar abrir o navegador"
        assert account.open_pix_purchase_page() is False, "sem sessão, nem deveria tentar chamar a function"
        account.sync_premium_status()  # também não deveria fazer nada (nem chamar a rede)
        assert settings.get_settings()["is_premium"] is False

        _login(account, sb, "comprador@teste.com", "Abc123!@", "u4", "Comprador")

        opened = {}
        account.webbrowser.open = lambda url: opened.setdefault("url", url)
        assert account.open_purchase_page() is True
        # e-mail vai URL-encodado (@ -> %40) — decodifica pra conferir o valor
        from urllib.parse import parse_qs, urlparse
        q = parse_qs(urlparse(opened["url"]).query)
        assert q["client_reference_id"] == ["u4"] and q["prefilled_email"] == ["comprador@teste.com"], opened

        # Pix (Mercado Pago, via Edge Function create-pix-payment) — Checkout
        # Pro, mesmo padrão do Stripe: abre uma URL de checkout no navegador
        # (ver account.open_pix_purchase_page)
        opened.clear()  # senão o setdefault acima mantinha a URL do Stripe
        sb.invoke_function = lambda name, access_token, body=None: {
            "checkout_url": "https://mercadopago.com.br/checkout/fake-pref-id",
        }
        assert account.open_pix_purchase_page() is True
        assert opened["url"] == "https://mercadopago.com.br/checkout/fake-pref-id", opened

        sb.invoke_function = lambda *a, **k: (_ for _ in ()).throw(sb.SupabaseError("falha no Mercado Pago"))
        try:
            account.open_pix_purchase_page()
            assert False, "deveria propagar o erro"
        except Exception as e:
            assert str(e) == "falha no Mercado Pago", str(e)

        # ainda não comprou (Edge Function não gravou nada em "purchases")
        sb.select_own_row = lambda table, access_token, columns="*": None
        account.sync_premium_status()
        assert settings.get_settings()["is_premium"] is False

        # comprou: a tabela "purchases" tem a linha (Edge Function do webhook gravou)
        sb.select_own_row = lambda table, access_token, columns="*": {"user_id": "u4", "entitlement": "premium"}
        account.sync_premium_status()
        assert settings.get_settings()["is_premium"] is True

        # backup na nuvem (ver backup.py) — sessão de "u4" (comprador) já está ativa
        import backup
        sb.upload_backup = lambda access_token, user_id, file_bytes: None
        backup.export_to_cloud("tok-u4", "u4")  # não deveria levantar nada

        sb.download_backup = lambda access_token, user_id: None
        assert backup.import_from_cloud("tok-u4", "u4") is False, "sem backup ainda -> False, não erro"

        # "backup de outro aparelho": um banco de verdade (senão sqlite3
        # recusa o arquivo depois), só que SEM sessão nenhuma gravada nele
        other_device_db = Path(tmp) / "other_device.db"
        real_db_path = db.DB_PATH
        db.DB_PATH = other_device_db
        db.init_db()
        db.DB_PATH = real_db_path
        fake_backup_bytes = other_device_db.read_bytes()

        import missions
        missions.add_mission("Só existe neste aparelho", "diaria", "facil")

        sb.download_backup = lambda access_token, user_id: fake_backup_bytes
        assert backup.import_from_cloud("tok-u4", "u4") is True
        # sobrescreveu o banco local pelo do outro aparelho (que está vazio);
        # byte a byte não dá mais pra comparar — o import regrava a sessão
        # deste aparelho dentro do arquivo, ver backup._replace_db
        assert missions.list_missions() == [], "deveria ter sobrescrito o banco local"

        # restaurar um backup sobrescreve local_session também (é o MESMO
        # arquivo), mas o import preserva a sessão DESTE aparelho — a que
        # estiver dentro do arquivo é sempre descartada
        session = account.current_session()
        assert session is not None and session["user_id"] == "u4", "sessão deste aparelho deveria sobreviver ao restore"

        # main.restore_from_cloud regrava a sessão por cima mesmo assim
        account.restore_session_row({
            "user_id": "u4", "email": "comprador@teste.com", "name": "Comprador",
            "access_token": "tok-u4", "refresh_token": "ref-u4", "expires_at": int(time.time()) + 3600,
        })
        session = account.current_session()
        assert session is not None and session["user_id"] == "u4", "sessão restaurada de volta"

        sb.upload_backup = lambda *a, **k: (_ for _ in ()).throw(sb.SupabaseError("network_error"))
        try:
            backup.export_to_cloud("tok-u4", "u4")
            assert False, "deveria propagar o erro (backup_to_cloud, em main.py, mostra pro usuário)"
        except Exception as e:
            assert str(e) == "network_error", str(e)

        # logout limpa a sessão local mesmo se a chamada de rede falhar, e
        # zera o cache local de Premium — sem isso, era por dispositivo, não
        # por conta: deslogar e outra conta entrar no mesmo aparelho herdava
        # o Premium de "u4" (comprador) sem nunca ter comprado nada
        #
        # (o restore de backup "de outro aparelho" logo acima já tinha zerado
        # is_premium sem querer — sync de novo pra ter uma pré-condição real)
        account.sync_premium_status()
        assert settings.get_settings()["is_premium"] is True, "pré-condição: 'u4' está premium antes do logout"
        sb.sign_out = lambda *a, **k: (_ for _ in ()).throw(sb.SupabaseError("network_error"))
        account.logout()
        assert account.current_session() is None
        assert settings.get_settings()["is_premium"] is False, "premium é cache local, não pode sobreviver ao logout"

        # --- deep link do e-mail de confirmação (ver deeplink.py) ---
        import deeplink
        pairs = deeplink._parse_pairs("access_token=AAA&refresh_token=RRR&expires_in=3600&type=signup")
        assert pairs == {"access_token": "AAA", "refresh_token": "RRR", "expires_in": "3600", "type": "signup"}
        assert deeplink._parse_pairs("") == {} and deeplink._parse_pairs(None) == {}

        # sem cadastro aguardando confirmação, o deep link não loga NINGUÉM —
        # qualquer app/página pode disparar a URI com um token válido da conta
        # DELE (o intent-filter é BROWSABLE), e antes isso virava a sessão
        # local: o próximo "Backup na nuvem" subia o banco da vítima pra pasta
        # do atacante
        settings.set_pending_signup_email("")
        sb.get_user = lambda access_token: {"id": "atk", "email": "atacante@evil.com", "user_metadata": {}}
        try:
            account.complete_deeplink_login("TOKEN-DO-ATACANTE", "REF", "3600")
            assert False, "deveria ter recusado deep link sem cadastro pendente"
        except Exception:
            pass
        assert account.current_session() is None, "não pode ter adotado a sessão do atacante"

        # sign_up passa o redirect_to (deep link) pro supabase_client e anota
        # o e-mail que está esperando confirmação
        captured = {}
        def _fake_signup(email, password, name, redirect_to=None):
            captured["redirect_to"] = redirect_to
            return {"id": "u9", "email": email}
        sb.sign_up = _fake_signup
        account.sign_up("Zé", "ze@teste.com", "Abc123!@")
        assert captured["redirect_to"] == account.EMAIL_CONFIRM_DEEPLINK == "discipliner://login-callback"
        assert settings.get_settings()["pending_signup_email"] == "ze@teste.com"

        # com cadastro pendente, ainda assim só passa token DAQUELE e-mail
        try:
            account.complete_deeplink_login("TOKEN-DO-ATACANTE", "REF", "3600")
            assert False, "deveria ter recusado token de outra conta"
        except Exception:
            pass
        assert account.current_session() is None, "não pode ter adotado a sessão do atacante"

        # complete_deeplink_login: monta a sessão a partir só dos tokens
        sb.get_user = lambda access_token: {"id": "u9", "email": "Ze@Teste.com", "user_metadata": {"name": "Zé"}}
        account.complete_deeplink_login("AAA", "RRR", "3600")
        s = account.current_session()
        assert s is not None and s["user_id"] == "u9" and s["email"] == "Ze@Teste.com" and s["access_token"] == "AAA"

        # e o marcador é de uso único: replay do mesmo link não passa de novo
        assert settings.get_settings()["pending_signup_email"] == ""
        try:
            account.complete_deeplink_login("AAA", "RRR", "3600")
            assert False, "deveria ter recusado o replay do deep link"
        except Exception:
            pass

        print("OK — todos os checks passaram")

        run_trocar_senha_e_apagar(account, sb, settings)


def _falha(fn, *args):
    """Mensagem da exceção (ou True) se fn levantar, False se não levantar.
    Não dá pra usar `try: ...; assert False` com `except Exception`: o
    AssertionError também é Exception e o teste passaria calado."""
    try:
        fn(*args)
    except Exception as e:
        return str(e) or True
    return False


def run_trocar_senha_e_apagar(account, sb, settings):
    """Trocar senha pelo link do e-mail e apagar a conta com código.

    Os dois caminhos mexem em algo sem volta (a senha, a conta inteira), então
    o que importa é: link de OUTRA conta não abre a tela de senha, código
    errado não apaga nada, e apagar some com o progresso local também."""
    import missions

    # --- trocar senha: o link volta pro app e só vale pra quem pediu ---
    pedido = {}
    sb.recover_password = lambda email, redirect_to=None: pedido.update(email=email, redirect=redirect_to)
    account.request_password_reset("Ze@Teste.com")
    assert pedido["redirect"] == account.RESET_PASSWORD_DEEPLINK == "discipliner://reset-password"
    assert settings.get_settings()["pending_reset_email"] == "ze@teste.com"

    contas = {"RESET": {"id": "u9", "email": "ze@teste.com", "user_metadata": {"name": "Zé"}},
              "OUTRO": {"id": "x", "email": "atacante@mal.com", "user_metadata": {}}}
    sb.get_user = lambda token: contas[token]
    assert _falha(account.validar_link_reset, "OUTRO") == "reset_link_invalid", \
        "link com token de outra conta não pode abrir a tela de senha"
    assert account.validar_link_reset("RESET") == "ze@teste.com"

    gravou = {}
    sb.update_user = lambda token, **campos: gravou.update(token=token, **campos) or contas["RESET"]
    assert _falha(account.complete_password_reset, "RESET", "R", "3600", "fraca"), "senha fraca não passa"
    assert not gravou, "senha fraca não pode chegar no servidor"
    account.complete_password_reset("RESET", "R", "3600", "Nova123!@")
    assert gravou == {"token": "RESET", "password": "Nova123!@"}, gravou
    assert settings.get_settings()["pending_reset_email"] == ""
    assert _falha(account.validar_link_reset, "RESET"), "o link de senha nova vale uma vez só"

    # --- trocar só o nome ---
    nomes = []
    sb.update_user = lambda token, **campos: nomes.append(campos) or {}
    account.update_name("Zé Novo")
    assert nomes == [{"data": {"name": "Zé Novo"}}], "trocar nome não pode mandar e-mail junto"
    assert account.current_session()["name"] == "Zé Novo"

    # --- apagar conta: código por e-mail -> função -> dados locais somem ---
    missions.add_mission("Ler", "diaria", "facil")
    ordem = []
    sb.send_email_code = lambda email: ordem.append(("codigo", email))
    email = account.request_delete_code()
    assert ordem == [("codigo", email)] and email == account.current_session()["email"]

    def codigo_errado(email, code):
        raise sb.SupabaseError("Token has expired or is invalid")

    sb.verify_email_code = codigo_errado
    sb.invoke_function = lambda name, token, body=None: ordem.append((name, token)) or {"ok": True}
    assert _falha(account.delete_account, "123456") == "err_code_invalid"
    assert _falha(account.delete_account, "abc") == "err_code_invalid"
    assert account.current_session() is not None and missions.list_missions(), "código errado não apaga nada"
    assert ("delete-account", "NOVO") not in ordem

    sb.verify_email_code = lambda email, code: ordem.append(("verifica", code)) or {
        "access_token": "NOVO", "refresh_token": "r", "expires_in": 3600, "user": {"id": "u9", "email": email}}
    account.delete_account("654321")
    assert ordem[-2:] == [("verifica", "654321"), ("delete-account", "NOVO")], \
        f"a função tem que ser chamada com a sessão NOVA do código: {ordem}"
    assert account.current_session() is None, "sessão local tem que sumir"
    assert missions.list_missions() == [], "progresso local tem que sumir junto"
    assert not settings.get_settings()["onboarding_done"], "o app volta ao primeiro acesso"

    print("OK — trocar senha só pelo link de quem pediu; apagar conta só com código e some com tudo")


if __name__ == "__main__":
    run()
