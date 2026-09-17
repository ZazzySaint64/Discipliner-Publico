"""Hook do python-for-android (ligado via `p4a.hook` no buildozer.spec).

android.extra_manifest_application_arguments injeta o valor DENTRO da tag de
abertura <application ...>, entre atributos (é pra "android:foo=bar" extra,
não pra elementos filhos) — ver AndroidManifest.tmpl.xml do p4a
(_sdl_common/build/templates). Usar essa chave pra colocar <activity-alias>
gera XML inválido (elemento no meio de uma lista de atributos) e derruba o
manifest merger do Gradle com "Error parsing AndroidManifest.xml", sem mais
detalhe do que isso.

Não existe hoje (checado no código-fonte do p4a) nenhuma chave do buildozer
pra injetar elementos filhos de <application> diretamente — só atributos, ou
conteúdo no nível de <manifest> (onde <activity-alias> também não é válido,
tem que ser filho de <application>). Esse hook cobre essa lacuna: roda
DEPOIS que o p4a já escreveu o AndroidManifest.xml final, e ANTES do Gradle
montar o APK (evento before_apk_assemble), e insere android_manifest_extra.xml
(os <activity-alias> dos ícones alternativos) logo antes de </application>.

O mesmo hook copia android_java/*.java (a ponte do intersticial do AdMob, ver
ads.py) pra src/main/java/<pacote>/ — o Gradle só varre esse diretório na hora
de compilar, que roda DEPOIS deste hook.
"""
import re
import shutil
from pathlib import Path

MANIFEST = Path("src/main/AndroidManifest.xml")
EXTRA = Path(__file__).resolve().parent / "android_manifest_extra.xml"
MARKER = "</application>"

JAVA_SRC_DIR = Path(__file__).resolve().parent / "android_java"
JAVA_DEST_DIR = Path("src/main/java/com/zazzysaint/dailyquest")  # = package.domain + package.name


SERVICO = "ServiceReminder"
TIPO_SERVICO = 'android:foregroundServiceType="shortService"'


def _tipar_servico(manifest):
    """Declara o <service> do lembrete como foreground de trabalho CURTO.

    O p4a gera o <service> só com android:name e android:process — não há chave
    no buildozer.spec pra tipo de serviço. E a partir do Android 14 (API 34, o
    nosso target) chamar startForeground() sem tipo declarado lança
    MissingForegroundServiceTypeException: o serviço subiria e morreria na hora.

    "shortService" é a categoria pra trabalho breve disparado por alarme — que
    é exatamente o que este serviço faz: acorda no horário, notifica, reagenda
    e sai. Diferente de "specialUse" (usado enquanto o serviço era permanente),
    NÃO pede justificativa na revisão da Play Console.
    """
    if TIPO_SERVICO in manifest:
        return manifest
    padrao = re.compile(
        r'(<service\b[^>]*android:name="[^"]*\.' + re.escape(SERVICO) + r'"[^>]*?)(\s*/?>)')
    novo, n = padrao.subn(rf"\1 {TIPO_SERVICO}\2", manifest, count=1)
    if not n:
        raise RuntimeError(
            f"{MANIFEST}: não achei o <service> do {SERVICO} pra declarar o "
            "foregroundServiceType — sem isso o serviço do lembrete morre no "
            "startForeground() do Android 14")
    return novo


def before_apk_assemble(build):
    manifest = MANIFEST.read_text(encoding="utf-8")
    extra = EXTRA.read_text(encoding="utf-8")
    if extra not in manifest:
        if MARKER not in manifest:
            raise RuntimeError(f"{MANIFEST}: não achei {MARKER!r} pra injetar o extra")
        manifest = manifest.replace(MARKER, extra + "\n" + MARKER, 1)
    manifest = _tipar_servico(manifest)
    MANIFEST.write_text(manifest, encoding="utf-8")

    if JAVA_SRC_DIR.is_dir():
        JAVA_DEST_DIR.mkdir(parents=True, exist_ok=True)
        for java_file in JAVA_SRC_DIR.glob("*.java"):
            shutil.copy(java_file, JAVA_DEST_DIR / java_file.name)
