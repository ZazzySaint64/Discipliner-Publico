"""Anúncios (AdMob) — só Android, só pra usuário grátis. Premium remove tudo.

- Banner fixo no rodapé da tela de Missões.
- Intersticial a cada INTERSTITIAL_EVERY conclusões, no máx. INTERSTITIAL_DAILY_CAP
  por dia (teto persistido em app_settings, não reseta reabrindo o app).
- Consentimento (UMP) roda antes de qualquer request — exigência da Play.

Banner e UMP são pyjnius puro (listeners do UMP são interfaces). O intersticial
passa por android_java/AdMobBridge.java: o callback de load do SDK atual é uma
CLASSE ABSTRATA e o pyjnius só implementa interfaces.

Fora do Android, ou com is_premium, TUDO aqui é no-op. Qualquer erro no lado
jnius é engolido — o app nunca quebra por causa de anúncio.

O código jnius/Java só roda no device; a lógica pura (contador -> gatilho,
teto diário) é o que test_ads.py cobre.
"""
from datetime import date

from kivy.clock import Clock
from kivy.utils import platform

import settings

INTERSTITIAL_EVERY = 5        # conclusões entre intersticiais
INTERSTITIAL_DAILY_CAP = 3    # máximo de intersticiais por dia

# IDs de TESTE públicos do Google (https://developers.google.com/admob/android/test-ads).
# Trocar pelos reais e virar USE_TEST_ADS = False antes de publicar.
USE_TEST_ADS = True
_TEST_APP_ID = "ca-app-pub-3940256099942544~3347511713"
_TEST_BANNER_ID = "ca-app-pub-3940256099942544/6300978111"
_TEST_INTERSTITIAL_ID = "ca-app-pub-3940256099942544/1033173712"

REAL_APP_ID = ""            # ca-app-pub-XXXX~XXXX  (vai também no buildozer.spec)
REAL_BANNER_ID = ""        # ca-app-pub-XXXX/XXXX
REAL_INTERSTITIAL_ID = ""  # ca-app-pub-XXXX/XXXX


def _banner_id():
    return _TEST_BANNER_ID if USE_TEST_ADS else REAL_BANNER_ID


def _interstitial_id():
    return _TEST_INTERSTITIAL_ID if USE_TEST_ADS else REAL_INTERSTITIAL_ID


_app = None
_ready = False               # consentimento resolvido + MobileAds init + banner criado
_banner_should_show = False
_session_completions = 0
_ad_view = None              # com.google.android.gms.ads.AdView (Android)


def _enabled():
    return platform == "android" and _app is not None and not _app.is_premium


# --- lógica pura (testável) -------------------------------------------------

def record_completion(today=None):
    """Conta uma conclusão. Devolve True se É hora de mostrar o intersticial:
    múltiplo de INTERSTITIAL_EVERY na sessão E ainda não bateu o teto do dia.
    Grava o teto em app_settings (reseta sozinho quando o dia vira)."""
    global _session_completions
    _session_completions += 1
    if _session_completions % INTERSTITIAL_EVERY != 0:
        return False
    today = today or date.today()
    prefs = settings.get_settings()
    shown = prefs["ad_interstitial_count"] if prefs["ad_interstitial_date"] == today.isoformat() else 0
    if shown >= INTERSTITIAL_DAILY_CAP:
        return False
    settings.set_ad_interstitial(shown + 1, today.isoformat())
    return True


# --- API chamada pelo main.py --------------------------------------------------

def init(app):
    """Guarda o app e, no Android grátis, dispara consentimento + init numa
    thread (nunca segura o boot)."""
    global _app
    _app = app
    if not _enabled():
        return
    import threading
    threading.Thread(target=_android_init, daemon=True).start()


def on_completion(today=None):
    """Uma missão foi concluída (ver main.refresh_after_complete)."""
    if not _enabled() or not _ready:
        return
    if record_completion(today):
        _show_interstitial()


def set_banner_visible(visible):
    """main.py chama com True ao entrar na tela de Missões, False fora dela."""
    global _banner_should_show
    _banner_should_show = bool(visible)
    if _enabled() and _ready:
        _apply_banner()


def disable():
    """Premium comprado no meio da sessão: esconde o banner que já estiver na
    tela (o gate _enabled() sozinho não desfaz um banner já visível)."""
    global _banner_should_show
    _banner_should_show = False
    if _ad_view is not None:
        _apply_banner()
    _set_app_flag(False)


# --- Android (pyjnius + bridge Java) — só roda no device ---------------------

def _run_on_ui(func):
    from jnius import PythonJavaClass, autoclass, java_method

    class _Runnable(PythonJavaClass):
        __javainterfaces__ = ["java/lang/Runnable"]

        @java_method("()V")
        def run(self):
            try:
                func()
            except Exception as e:
                print(f"[ads] erro na UI thread: {e!r}")

    autoclass("org.kivy.android.PythonActivity").mActivity.runOnUiThread(_Runnable())


def _android_init():
    try:
        from jnius import PythonJavaClass, autoclass, java_method

        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        UMP = autoclass("com.google.android.ump.UserMessagingPlatform")
        ConsentRequestParameters = autoclass("com.google.android.ump.ConsentRequestParameters$Builder")
        consent_info = UMP.getConsentInformation(activity)

        params = ConsentRequestParameters().build()

        class _OnUpdated(PythonJavaClass):
            __javainterfaces__ = ["com/google/android/ump/ConsentInformation$OnConsentInfoUpdateSuccessListener"]

            @java_method("()V")
            def onConsentInfoUpdateSuccess(self):
                def after_form(*_):
                    _start_ads(activity)
                try:
                    class _Dismissed(PythonJavaClass):
                        __javainterfaces__ = ["com/google/android/ump/ConsentForm$OnConsentFormDismissedListener"]

                        @java_method("(Lcom/google/android/ump/FormError;)V")
                        def onConsentFormDismissed(self, error):
                            after_form()

                    UMP.loadAndShowConsentFormIfRequired(activity, _Dismissed())
                except Exception as e:
                    print(f"[ads] consent form: {e!r}")
                    after_form()

        class _OnFailed(PythonJavaClass):
            __javainterfaces__ = ["com/google/android/ump/ConsentInformation$OnConsentInfoUpdateFailureListener"]

            @java_method("(Lcom/google/android/ump/FormError;)V")
            def onConsentInfoUpdateFailure(self, error):
                # sem rede pra checar consentimento — segue com o que o SDK
                # tiver em cache (não-personalizado no pior caso)
                _start_ads(activity)

        consent_info.requestConsentInfoUpdate(activity, params, _OnUpdated(), _OnFailed())
    except Exception as e:
        print(f"[ads] _android_init falhou: {e!r}")


def _start_ads(activity):
    global _ready, _ad_view
    try:
        from jnius import autoclass

        MobileAds = autoclass("com.google.android.gms.ads.MobileAds")
        MobileAds.initialize(activity, None)

        AdView = autoclass("com.google.android.gms.ads.AdView")
        AdSize = autoclass("com.google.android.gms.ads.AdSize")
        AdRequestBuilder = autoclass("com.google.android.gms.ads.AdRequest$Builder")
        FrameLayoutParams = autoclass("android.widget.FrameLayout$LayoutParams")
        Gravity = autoclass("android.view.Gravity")
        View = autoclass("android.view.View")

        def build_banner():
            global _ad_view
            _ad_view = AdView(activity)
            _ad_view.setAdUnitId(_banner_id())
            _ad_view.setAdSize(AdSize.BANNER)
            lp = FrameLayoutParams(-2, -2)  # WRAP_CONTENT, WRAP_CONTENT
            lp.gravity = Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL
            activity.addContentView(_ad_view, lp)
            _ad_view.setVisibility(View.GONE)
            _ad_view.loadAd(AdRequestBuilder().build())

        _run_on_ui(build_banner)

        Bridge = autoclass("com.zazzysaint.dailyquest.AdMobBridge")
        Bridge.loadInterstitial(activity, _interstitial_id())

        _ready = True
        _apply_banner()
    except Exception as e:
        print(f"[ads] _start_ads falhou: {e!r}")


def _apply_banner():
    if _ad_view is None:
        return

    def go():
        from jnius import autoclass
        View = autoclass("android.view.View")
        _ad_view.setVisibility(View.VISIBLE if _banner_should_show else View.GONE)
        Clock.schedule_once(lambda _dt: _set_app_flag(_banner_should_show), 0)

    _run_on_ui(go)


def _set_app_flag(value):
    if _app is not None:
        _app.ad_banner_visible = bool(value)


def _show_interstitial():
    try:
        from jnius import autoclass
        activity = autoclass("org.kivy.android.PythonActivity").mActivity
        Bridge = autoclass("com.zazzysaint.dailyquest.AdMobBridge")
        _run_on_ui(lambda: Bridge.showInterstitial(activity, _interstitial_id()))
    except Exception as e:
        print(f"[ads] _show_interstitial falhou: {e!r}")
