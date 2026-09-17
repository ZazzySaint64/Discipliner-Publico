"""Self-check da foto de perfil: python test_photo.py

Regressão do "não dá pra colocar foto personalizada, fica preto" — uma imagem
com transparência (PNG/WEBP/GIF) virava um retângulo preto porque converter
direto pra RGB descarta o alfa e mantém o RGB de baixo, que nos pixels
transparentes costuma ser (0,0,0). Não abre janela."""
import os

os.environ.setdefault("KIVY_NO_ARGS", "1")


def run():
    from PIL import Image

    import main

    # 1) PNG transparente com RGB preto por baixo — o caso que ficava preto
    png = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
    achatada = main._flatten_to_rgb(png)
    assert achatada.mode == "RGB", achatada.mode
    assert achatada.getpixel((0, 0)) == (255, 255, 255), \
        f"transparente tinha que virar branco, veio {achatada.getpixel((0, 0))}"

    # 2) o que era opaco continua com a cor certa (não lava a imagem toda)
    meio = Image.new("RGBA", (2, 1), (255, 0, 0, 255))
    meio.putpixel((1, 0), (0, 0, 0, 0))
    achatada = main._flatten_to_rgb(meio)
    assert achatada.getpixel((0, 0)) == (255, 0, 0), achatada.getpixel((0, 0))
    assert achatada.getpixel((1, 0)) == (255, 255, 255), achatada.getpixel((1, 0))

    # 3) modo P com transparência (GIF) — passa por RGBA antes, senão satura
    p = Image.new("P", (4, 4), 0)
    achatada = main._flatten_to_rgb(p)
    assert achatada.mode == "RGB", achatada.mode

    # 4) JPEG comum (sem alfa) segue intacto
    rgb = Image.new("RGB", (4, 4), (12, 34, 56))
    achatada = main._flatten_to_rgb(rgb)
    assert achatada.getpixel((0, 0)) == (12, 34, 56), achatada.getpixel((0, 0))

    # 5) a legenda de formatos não pode discordar do filtro do seletor
    assert ".webp" in main.PHOTO_EXTS, "webp é comum em foto salva do navegador"
    for ext in main.PHOTO_EXTS:
        assert ext.startswith("."), ext
        assert Image.registered_extensions().get(ext), f"Pillow não lê {ext} — tirar da legenda"

    # 6) a gravada é SEMPRE quadrada — a moldura do cabeçalho é um quadrado
    # fixo, e foto retangular escapava dela (ver print do "moldura + foto")
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as tmp:
        for tamanho in [(1200, 300), (300, 1200), (700, 700), (40, 90)]:
            origem = Path(tmp) / "src.png"
            destino = Path(tmp) / "dest.png"
            Image.new("RGB", tamanho, (10, 200, 30)).save(origem)
            main._prepare_photo(origem, destino)
            with Image.open(destino) as saida:
                assert saida.size == (main.PHOTO_SIZE, main.PHOTO_SIZE), \
                    f"{tamanho} devia virar quadrada, veio {saida.size}"
                assert saida.mode == "RGB", saida.mode

        # arquivo que não é imagem tem que estourar (upload_profile_photo
        # depende disso pra mostrar o aviso em vez de gravar lixo)
        ruim = Path(tmp) / "ruim.png"
        ruim.write_bytes(b"nao sou imagem")
        try:
            main._prepare_photo(ruim, Path(tmp) / "x.png")
            assert False, "devia ter recusado um arquivo que não é imagem"
        except Exception:
            pass

    print(f"OK — foto achatada sobre branco e quadrada, {len(main.PHOTO_EXTS)} formatos aceitos")


class _FakeStream:
    """Imita java.io.InputStream.read(byte[]) como o pyjnius o expõe: escreve
    DENTRO do buffer recebido e devolve quantos bytes leu (-1 no fim). É o
    contrato do qual android_picker._ler_para_temporario depende."""

    def __init__(self, dados):
        self.dados = dados
        self.pos = 0
        self.fechado = False

    def read(self, buf):
        n = min(len(buf), len(self.dados) - self.pos)
        if n <= 0:
            return -1
        buf[:n] = self.dados[self.pos:self.pos + n]
        self.pos += n
        return n

    def close(self):
        self.fechado = True


class _FakeActivity:
    def __init__(self, stream, escrita=False):
        self._stream = stream
        self._escrita = escrita

    def getContentResolver(self):
        return self

    def openInputStream(self, _uri):
        return self._stream

    def openOutputStream(self, _uri):
        return self._stream


def run_picker():
    """O seletor do Android: cópia do content:// pro temporário, e degradação
    segura fora do Android. Regressão do "não dá pra colocar foto
    personalizada" — o caminho que o plyer devolvia era ilegível."""
    import tempfile
    from pathlib import Path

    from kivy.clock import Clock

    import android_picker

    assert android_picker.disponivel() is False, "fora do Android tem que devolver False"

    # a cópia preserva os bytes exatos (uma imagem corrompida aqui viraria
    # "arquivo inválido" na cara do usuário)
    dados = bytes(range(256)) * 500  # 128000 bytes, > 1 buffer de 64KB
    stream = _FakeStream(dados)
    destino = android_picker._ler_para_temporario(_FakeActivity(stream), object())
    try:
        assert Path(destino).read_bytes() == dados, "a cópia saiu diferente do original"
        assert stream.fechado, "o InputStream do Android tem que ser fechado"
    finally:
        Path(destino).unlink(missing_ok=True)

    # stream nulo (provider recusou) não pode explodir
    assert android_picker._ler_para_temporario(_FakeActivity(None), object()) is None

    # e o caminho de ESCRITA (backup/cartão de sequência), que antes ia pelo
    # plyer e não funcionava no Android moderno: o conteúdo gravado no
    # temporário tem que chegar inteiro no content:// escolhido
    class _FakeOutput:
        def __init__(self):
            self.buf = bytearray()
            self.fechado = False

        def write(self, dados):
            self.buf.extend(dados)

        def flush(self):
            pass

        def close(self):
            self.fechado = True

    saida = _FakeOutput()
    origem = Path(tempfile.mkdtemp()) / "origem.bin"
    conteudo = bytes(range(256)) * 700  # 179200 bytes, > 2 buffers de 64KB
    origem.write_bytes(conteudo)
    android_picker._despejar_no_uri(_FakeActivity(saida, escrita=True), object(), origem)
    assert bytes(saida.buf) == conteudo, "o arquivo chegou diferente no destino"
    assert saida.fechado, "o OutputStream do Android tem que ser fechado"

    # provedor que recusa escrita não pode passar batido em silêncio
    try:
        android_picker._despejar_no_uri(_FakeActivity(None, escrita=True), object(), origem)
        assert False, "destino nulo tinha que levantar"
    except OSError:
        pass

    # sem o módulo `android` (ou seja, fora do device) o callback ainda é
    # chamado, com None — senão o botão de enviar foto ficaria mudo pra sempre
    resposta = []
    android_picker.escolher_imagem(resposta.append)
    Clock.tick()
    assert resposta == [None], f"esperava callback com None, veio {resposta}"

    print("OK — seletor do Android copia o content:// certo e degrada sem device")


if __name__ == "__main__":
    run()
    run_picker()
