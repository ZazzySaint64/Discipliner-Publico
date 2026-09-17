"""Seletor de arquivos no Android pelo Storage Access Framework (SAF).

Por que não usar o plyer (que o app usava em tudo antes):
o plyer dispara ACTION_GET_CONTENT e depois tenta converter o content:// num
CAMINHO de arquivo (`_resolve_uri` consulta a coluna `_data` do MediaStore, ou
monta "/storage/emulated/0/<nome>"). Isso não funciona mais:

* sob scoped storage (Android 10+) a coluna `_data` não é confiável e várias
  vezes nem existe;
* ler "/storage/emulated/0/..." exigiria READ_MEDIA_IMAGES / permissão de
  armazenamento, que este app não declara (e que puxa declaração extra na
  Play Console);
* arquivo vindo do Google Fotos/Drive não tem caminho nenhum — só o content://.

Resultado: o caminho voltava nulo ou ilegível. Era o bug de "não dá pra colocar
foto personalizada", e o backup tinha exatamente o mesmo defeito.

O SAF resolve sem permissão alguma: ACTION_OPEN_DOCUMENT / ACTION_CREATE_DOCUMENT
devolvem um content:// que o app já tem direito de ler ou escrever, e o acesso
vai pelo ContentResolver, não pelo sistema de arquivos.

Pra não obrigar o resto do app a entender content://, tudo aqui trabalha com
ARQUIVO TEMPORÁRIO: na leitura, o stream é copiado pra um temporário e o
caminho dele sobe pro chamador; na escrita, o chamador grava num temporário
normalmente e o conteúdo é despejado no content:// depois. Assim `backup.py`,
`share_card.py` e o Pillow continuam vendo caminhos comuns.

Fora do Android `disponivel()` devolve False e quem chama segue com o seletor
de desktop (main._pick_file).
"""
import os
import tempfile
import traceback

from kivy.clock import Clock
from kivy.utils import platform

# códigos arbitrários, só pra reconhecer a resposta DESTA Activity entre outras.
# Abrir e salvar precisam ser diferentes: as duas respostas chegam no mesmo
# callback e seriam indistinguíveis com o mesmo código.
_REQ_ABRIR = 0xF070
_REQ_SALVAR = 0xF071

_RESULT_OK = -1  # android.app.Activity.RESULT_OK


def disponivel():
    return platform == "android"


def escolher_imagem(callback):
    """Atalho histórico pra foto de perfil — ver escolher_arquivo."""
    escolher_arquivo(callback, mime="image/*")


def escolher_arquivo(callback, mime="*/*"):
    """Abre o seletor do sistema e chama callback(caminho_temporario_ou_None).

    O callback SEMPRE roda na thread da UI (via Clock): o resultado da Activity
    chega na thread do Android, e mexer em widget/property do Kivy de fora da
    thread dele corrompe o estado interno.
    """
    def ao_responder(atividade, data, responder):
        uri = data.getData() if data is not None else None
        if uri is None:
            responder(None)
            return
        responder(_ler_para_temporario(atividade, uri))

    _abrir_activity("android.intent.action.OPEN_DOCUMENT", mime, None,
                    _REQ_ABRIR, callback, ao_responder)


def salvar_arquivo(callback, mime="application/octet-stream", nome_sugerido="arquivo"):
    """Pede ao sistema ONDE salvar e chama callback(caminho_temporario_ou_None).

    O chamador grava nesse temporário como faria em qualquer arquivo; quando
    ele devolve, o conteúdo é copiado pro content:// escolhido. Ou seja, a
    assinatura continua igual à do seletor de desktop."""
    def ao_responder(atividade, data, responder):
        uri = data.getData() if data is not None else None
        if uri is None:
            responder(None)
            return
        fd, temporario = tempfile.mkstemp(prefix="discipliner_saida_")
        os.close(fd)

        def depois_de_gravar(_dt):
            try:
                callback(temporario)          # o chamador escreve no temporário
                _despejar_no_uri(atividade, uri, temporario)
            except Exception:
                print(f"[seletor] falha gravando no destino escolhido:\n{traceback.format_exc()}")
            finally:
                try:
                    os.unlink(temporario)
                except OSError:
                    pass

        # o callback do chamador mexe em property do Kivy (backup_status,
        # share_status) — tem que rodar na thread da UI, igual ao caminho de leitura
        Clock.schedule_once(depois_de_gravar, 0)

    _abrir_activity("android.intent.action.CREATE_DOCUMENT", mime, nome_sugerido,
                    _REQ_SALVAR, callback, ao_responder)


def _abrir_activity(acao, mime, nome_sugerido, codigo, callback, ao_responder):
    def responder(caminho):
        Clock.schedule_once(lambda _dt: callback(caminho), 0)

    try:
        from android import activity as android_activity
        from jnius import autoclass

        Intent = autoclass("android.content.Intent")
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        atividade = PythonActivity.mActivity

        def resultado(request_code, result_code, data):
            if request_code != codigo:
                return  # resposta de outra Activity (o outro modo, um anúncio...)
            android_activity.unbind(on_activity_result=resultado)
            try:
                if result_code != _RESULT_OK:
                    responder(None)  # o usuário cancelou
                    return
                ao_responder(atividade, data, responder)
            except Exception:
                print(f"[seletor] falha tratando o content:// escolhido:\n{traceback.format_exc()}")
                responder(None)

        android_activity.bind(on_activity_result=resultado)

        intent = Intent(acao)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType(mime)
        if nome_sugerido:
            intent.putExtra(Intent.EXTRA_TITLE, nome_sugerido)
        atividade.startActivityForResult(intent, codigo)
    except Exception:
        # sem seletor não dá pra escolher nada, mas o app não pode cair por isso
        if disponivel():  # fora do Android cair aqui é o esperado (não tem `android`)
            print(f"[seletor] não consegui abrir o seletor do Android:\n{traceback.format_exc()}")
        responder(None)


def _ler_para_temporario(atividade, uri):
    """Lê o content:// pelo ContentResolver e grava num arquivo temporário.

    Sem extensão de propósito: o Pillow identifica o formato pelo conteúdo
    (magic bytes), não pelo nome, e o content:// muitas vezes nem tem nome de
    arquivo pra copiar."""
    entrada = atividade.getContentResolver().openInputStream(uri)
    if entrada is None:
        return None
    fd, destino = tempfile.mkstemp(prefix="discipliner_entrada_")
    try:
        with os.fdopen(fd, "wb") as saida:
            buffer_ = bytearray(64 * 1024)
            while True:
                lidos = entrada.read(buffer_)
                if lidos <= 0:
                    break
                saida.write(bytes(buffer_[:lidos]))
    finally:
        entrada.close()
    return destino


def _despejar_no_uri(atividade, uri, origem):
    """Copia o arquivo local pro content:// escolhido pelo usuário."""
    saida = atividade.getContentResolver().openOutputStream(uri)
    if saida is None:
        raise OSError("o provedor não abriu o destino para escrita")
    try:
        with open(origem, "rb") as entrada:
            while True:
                pedaco = entrada.read(64 * 1024)
                if not pedaco:
                    break
                saida.write(bytearray(pedaco))
        saida.flush()
    finally:
        saida.close()
