"""Detecção de Android SEM importar o Kivy.

`kivy.utils.platform` resolveria, mas importar `kivy` puxa configuração,
logging e providers inteiros — e o serviço de lembrete (service_reminder.py)
roda num processo separado, sem interface nenhuma. Pagar o Kivy ali seria
desperdício, e em processo de serviço o import pode até falhar.

O p4a define ANDROID_ARGUMENT para os dois processos, o do app e o do serviço,
antes do Python subir — é o mesmo sinal que o próprio `kivy.utils` usa.
"""
import os

IS_ANDROID = "ANDROID_ARGUMENT" in os.environ


def android_context():
    """Um android.content.Context válido NOS DOIS processos: o do app e o do
    serviço de lembrete.

    `PythonActivity.mActivity` só existe no processo do app — num processo de
    serviço é `None`, e usá-lo ali estoura
    `AttributeError: 'NoneType' object has no attribute 'getSystemService'`
    (era o motivo de o serviço nunca conseguir notificar com o app fechado).
    `PythonService.mService` é o Service (que também é Context) e existe no
    processo do serviço. Um dos dois está setado; devolve o que houver, ou
    `None` fora do Android — o caller trata.
    """
    if not IS_ANDROID:
        return None
    from jnius import autoclass

    ctx = autoclass("org.kivy.android.PythonActivity").mActivity
    if ctx is None:
        ctx = autoclass("org.kivy.android.PythonService").mService
    return ctx
