"""Deep link do e-mail de confirmação de conta: discipliner://login-callback.

O Supabase, ao confirmar o e-mail, faz um 302 pro `redirect_to`
(account.EMAIL_CONFIRM_DEEPLINK). No Android, esse scheme está no
<intent-filter> da PythonActivity (android_intent_filters.xml) — o Android
abre o app e este módulo extrai os tokens do fragmento da URI
(#access_token=...&refresh_token=...&expires_in=...) e chama o handler.

Android-only. Fora do Android, init() é no-op (o link cai na página estática
do GitHub Pages, e o usuário usa o botão "Já confirmei, entrar")."""
from kivy.clock import Clock
from kivy.utils import platform

SCHEME = "discipliner"

# host -> func(dict), chamada na thread da UI com os pares do fragmento:
#   login-callback  = confirmação de cadastro
#   reset-password  = link do e-mail de senha nova
_handlers = {}


def init(handlers):
    """handlers: {host: func(params)} — roda na thread da UI quando o app abre
    por um link discipliner://<host>."""
    global _handlers
    _handlers = dict(handlers)
    if platform != "android":
        return
    try:
        from android import activity as _android_activity  # p4a
        from jnius import autoclass

        _android_activity.bind(on_new_intent=_on_new_intent)
        # cold start: o app pode ter sido aberto PELO link
        launch_intent = autoclass("org.kivy.android.PythonActivity").mActivity.getIntent()
        _handle_intent(launch_intent)
    except Exception as e:
        print(f"[deeplink] init falhou: {e!r}")


def _on_new_intent(intent):
    _handle_intent(intent)


def _parse_pairs(raw):
    pairs = {}
    for part in (raw or "").split("&"):
        if "=" in part:
            key, _, value = part.partition("=")
            pairs[key] = value
    return pairs


def _handle_intent(intent):
    try:
        if intent is None:
            return
        data = intent.getData()
        if data is None:
            return
        handler = _handlers.get(data.getHost())
        if data.getScheme() != SCHEME or handler is None:
            return
        # fluxo implícito: tokens no fragmento; alguns fluxos mandam na query
        pairs = _parse_pairs(data.getFragment()) or _parse_pairs(data.getQuery())
        if pairs:
            Clock.schedule_once(lambda _dt: handler(pairs), 0)
    except Exception as e:
        print(f"[deeplink] _handle_intent falhou: {e!r}")
