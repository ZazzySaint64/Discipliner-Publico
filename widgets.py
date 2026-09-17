"""Widgets clay reutilizáveis. Propriedades declaradas em Python (não via classe
dinâmica do kv com '@') de propósito: quando uma propriedade só existe pela sintaxe
dinâmica do kv, referenciá-la dentro do canvas.before da MESMA regra tem timing
ambíguo (o kv tenta montar o canvas antes da propriedade ganhar seu valor padrão) e
quebra com "NoneType is not iterable". Declarando em Python, a propriedade já existe
de verdade antes do Builder.load_file processar o kv.
"""
import os

from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Ellipse, Line, Rectangle, StencilPop, StencilPush, StencilUnUse, StencilUse
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.image import Image
from kivy.uix.spinner import Spinner
from kivy.uix.widget import Widget

_NAV_ICON_DIR = os.path.join(os.path.dirname(__file__), "assets", "nav")


def _luminancia(cor):
    """Luminância relativa (WCAG) de uma cor RGB(A) em 0-1."""
    def canal(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(c) for c in cor[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def texto_legivel(bg, cor):
    """`cor` se ela já contrasta com `bg`; senão, quase-preto ou branco — o que
    contrastar mais.

    A cor personalizada deixa escolher QUALQUER destaque, inclusive um verde
    bem claro, e aí o texto branco dos botões sumia. Contraste 3:1 é o mínimo
    da WCAG pra texto grande/negrito, que é o caso dos botões."""
    def contraste(a, b):
        claro, escuro = sorted((_luminancia(a), _luminancia(b)), reverse=True)
        return (claro + 0.05) / (escuro + 0.05)

    if contraste(bg, cor) >= 3:
        return cor
    escuro = [0.10, 0.10, 0.10, cor[3] if len(cor) > 3 else 1]
    branco = [1, 1, 1, cor[3] if len(cor) > 3 else 1]
    return escuro if contraste(bg, escuro) >= contraste(bg, branco) else branco


def lip(bg, text):
    """Cor do "lábio" 3D (a faixa grossa embaixo) e da borda, estilo Duolingo.

    Fundo claro/colorido: um tom mais ESCURO do próprio fundo (botão verde,
    lábio verde-escuro). Fundo escuro (cards e botões secundários no modo
    escuro): escurecer some contra o fundo do app, então puxa em direção à cor
    do texto — sai um cinza mais claro, como a borda dos cards do Duolingo."""
    r, g, b, a = bg
    if r + g + b > 0.9:
        return [r * 0.72, g * 0.72, b * 0.72, a]
    return [r + (text[0] - r) * 0.2, g + (text[1] - g) * 0.2, b + (text[2] - b) * 0.2, a]


class ClayCard(BoxLayout):
    bg_color = ListProperty([0.90, 0.91, 0.97, 1])


class ClayButton(ButtonBehavior, BoxLayout):
    text = StringProperty("")
    bg_color = ListProperty([0.95, 0.55, 0.30, 1])  # mesma cor ACCENT do ui.kv — manter em sincronia
    text_color = ListProperty([1, 1, 1, 1])
    font_size = NumericProperty(sp(15))  # padrão; encolhe sozinho se o texto não couber (fit_font_size)

    def fit_font_size(self, label_width):
        """Encolhe a fonte quando o texto (nome/idioma variam de tamanho) não
        cabe na largura disponível do botão — antes estourava a borda porque
        o Label não sabia o próprio limite. Nunca passa do padrão de 15sp."""
        base = sp(15)
        if not self.text or label_width <= 0:
            self.font_size = base
            return
        # mede em MAIÚSCULAS: é assim que o kv desenha (estilo Duolingo)
        probe = CoreLabel(text=self.text.upper(), font_size=base, bold=True)
        probe.refresh()
        natural_width = probe.texture.size[0]
        if natural_width > label_width:
            self.font_size = max(sp(10), base * label_width / natural_width)
        else:
            self.font_size = base


class TapArea(ButtonBehavior, BoxLayout):
    """Área clicável sem nenhum visual próprio (sem fundo, sem borda) — pra
    quando o filho já se vira sozinho visualmente e só falta o toque abrir
    algo (ex.: avatar do cabeçalho)."""
    pass


class ClayCardButton(ButtonBehavior, BoxLayout):
    """Igual ao ClayCard visualmente, mas clicável — só pra cards sem filho
    interativo dentro (TextInput etc.), porque ButtonBehavior consome o touch
    antes dele chegar nos filhos (já vimos esse tipo de bug com campo de senha)."""
    bg_color = ListProperty([0.90, 0.91, 0.97, 1])


class ClayCheck(ButtonBehavior, BoxLayout):
    checked = BooleanProperty(False)
    mission_id = NumericProperty(0)

    def on_release(self):
        self.checked = not self.checked
        from kivy.app import App
        App.get_running_app().on_toggle_mission(self.mission_id, self.checked, self)


class ClayProgressBar(Widget):
    value = NumericProperty(0.0)


class ClaySpinner(Spinner):
    """Mesmo pill arredondado dos botões, mais uma seta pra deixar óbvio que é
    uma opção clicável (o Spinner de fábrica do Kivy já tinha essa seta, mas
    sumiu quando zeramos background_normal/down pra tirar a textura padrão)."""
    pass


class DayToggle(ButtonBehavior, BoxLayout):
    """Bolinha de dia da semana (S/T/Q...), pra marcar em quais dias uma missão
    diária vale. Só liga/desliga a própria aparência — quem lê o estado final
    (pra montar o custom_days) é o popup dono, via seus ids."""
    day_index = NumericProperty(0)
    label_text = StringProperty("")
    active = BooleanProperty(False)

    def on_release(self):
        self.active = not self.active


class AvatarThumb(ButtonBehavior, BoxLayout):
    """Miniatura clicável de uma pose do Focum, pra escolher como foto de perfil."""
    avatar_id = StringProperty("")
    img_path = StringProperty("")
    unlocked = BooleanProperty(True)

    def on_release(self):
        if self.unlocked:
            from kivy.app import App
            App.get_running_app().set_profile_avatar(self.avatar_id)


class FrameThumb(ButtonBehavior, BoxLayout):
    """Miniatura clicável de uma moldura decorativa pro avatar OU de um ícone
    alternativo do app (mesmos tiers, ver mascot.FRAMES) — action decide qual
    dos dois essa miniatura representa."""
    frame_id = StringProperty("")
    frame_color = ListProperty([0, 0, 0, 0])
    unlocked = BooleanProperty(True)
    action = StringProperty("frame")  # "frame" ou "icon"

    def on_release(self):
        if not self.unlocked:
            return
        from kivy.app import App
        app = App.get_running_app()
        if self.action == "icon":
            app.set_app_icon(self.frame_id)
        else:
            app.set_profile_frame(self.frame_id)


class TutorialOverlay(FloatLayout):
    """Camada de destaque do tutorial guiado (ver main.TUTORIAL_STEPS). Fica no
    Window por cima de tudo: escurece a tela com 4 retângulos em volta de um
    "buraco" no widget-alvo, contorna o buraco de verde e liga uma seta até o
    card de texto (título + corpo + Voltar/Pular/Próximo).

    Coordenadas do buraco são em espaço de janela — como o overlay ocupa o
    Window inteiro a partir de (0,0), janela == local aqui."""
    hole = ListProperty([0, 0, 0, 0])          # x, y, w, h (origem embaixo-esquerda)
    has_hole = BooleanProperty(False)
    arrow = ListProperty([0, 0, 0, 0])          # x1, y1, x2, y2 (vazio = sem seta)
    title_text = StringProperty("")
    body_text = StringProperty("")
    progress_text = StringProperty("")
    is_first = BooleanProperty(True)
    is_last = BooleanProperty(False)
    card_x = NumericProperty(0)
    card_y = NumericProperty(0)

    _RING = (0.29, 0.87, 0.5, 1)                # verde de contraste (pop no tema vermelho)
    _SCRIM = (0, 0, 0, 0.72)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(hole=self._redraw, size=self._redraw, pos=self._redraw,
                  has_hole=self._redraw, arrow=self._redraw, disabled=self._redraw)
        self.bind(hole=self._place_card, size=self._place_card)

    # --- API chamada pelo App ---
    def show(self):
        self.opacity = 1
        self.disabled = False  # dispara _redraw (ver __init__)

    def hide(self):
        self.opacity = 0
        self.has_hole = False
        self.arrow = [0, 0, 0, 0]
        self.disabled = True   # dispara _redraw, que agora limpa o scrim e sai
        self.canvas.before.clear()  # e não confia só no opacity/_redraw

    def set_step(self, title, body, progress, is_first, is_last):
        self.title_text = title
        self.body_text = body
        self.progress_text = progress
        self.is_first = is_first
        self.is_last = is_last

    def spotlight(self, x, y, w, h):
        pad = dp(6)
        self.has_hole = True
        self.hole = [x - pad, y - pad, w + 2 * pad, h + 2 * pad]

    def show_centered(self):
        self.has_hole = False
        self.arrow = [0, 0, 0, 0]
        # buraco de tamanho 0 no centro: os 4 retângulos cobrem a tela toda
        self.hole = [self.center_x, self.center_y, 0, 0]

    # --- posicionamento do card ---
    def _card(self):
        return self.ids.get("tut_card")

    def _place_card(self, *_):
        card = self._card()
        if card is None:
            return
        cw = card.width
        ch = card.height
        if not self.has_hole:
            self.card_x = self.center_x - cw / 2
            self.card_y = self.center_y - ch / 2
            self.arrow = [0, 0, 0, 0]
            return
        hx, hy, hw, hh = self.hole
        hcx = hx + hw / 2
        gap = dp(18)
        self.card_x = max(dp(16), min(hcx - cw / 2, self.width - cw - dp(16)))
        if hy + hh / 2 > self.center_y:
            # buraco na metade de cima -> card embaixo dele
            self.card_y = hy - gap - ch
            ax2, ay2 = self.card_x + cw / 2, self.card_y + ch
            ay1 = hy
        else:
            self.card_y = hy + hh + gap
            ax2, ay2 = self.card_x + cw / 2, self.card_y
            ay1 = hy + hh
        ax2 = max(self.card_x + dp(20), min(ax2, self.card_x + cw - dp(20)))
        self.arrow = [hcx, ay1, ax2, ay2]

    def _redraw(self, *_):
        self.canvas.before.clear()
        if self.disabled:  # escondido (ver hide()) — não desenha scrim nenhum
            return
        w, h = self.width, self.height
        if w <= 0 or h <= 0:
            return
        x, y, hw, hh = self.hole
        top = y + hh
        with self.canvas.before:
            Color(rgba=self._SCRIM)
            Rectangle(pos=(0, top), size=(w, max(0, h - top)))       # acima
            Rectangle(pos=(0, 0), size=(w, max(0, y)))               # abaixo
            Rectangle(pos=(0, y), size=(max(0, x), max(0, hh)))      # esquerda
            Rectangle(pos=(x + hw, y), size=(max(0, w - (x + hw)), max(0, hh)))  # direita
            if self.has_hole:
                Color(rgba=self._RING)
                Line(rounded_rectangle=(x, y, hw, hh, dp(10)), width=dp(2.5))
                if any(self.arrow):
                    Line(points=self.arrow, width=dp(2))

    # --- bloqueia o app por baixo enquanto o tutorial roda ---
    def on_touch_down(self, touch):
        if self.disabled:
            return False
        super().on_touch_down(touch)   # botões do card respondem primeiro
        return True                    # o resto morre aqui

    def on_touch_move(self, touch):
        if self.disabled:
            return False
        super().on_touch_move(touch)
        return True

    def on_touch_up(self, touch):
        if self.disabled:
            return False
        super().on_touch_up(touch)
        return True


class NavIcon(Image):
    """Ícone da barra de abas — PNG de silhueta branca em assets/nav/,
    pintado pela cor da aba via `Image.color` (accent quando ativa, muted
    quando não). Era desenhado no canvas; virou imagem quando passou a
    existir a arte pronta (ver scripts/gen_nav_icons.py).

    NÃO é ButtonBehavior de propósito: quem trata o toque é o NavTab que o
    contém — se este ícone consumisse o touch, tocar nele (a maior parte da
    aba) não trocaria de tela.

    kind: "missions" | "history" | "chart" | "badges" | "settings"
    """
    KINDS = ("missions", "history", "chart", "badges", "settings")
    kind = StringProperty("missions")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.allow_stretch = True
        self.keep_ratio = True
        self.mipmap = True   # ícone grande reduzido pra dp(24): sem mipmap serrilha
        self.bind(kind=self._set_source)
        self._set_source()

    def _set_source(self, *args):
        kind = self.kind if self.kind in self.KINDS else "missions"
        self.source = os.path.join(_NAV_ICON_DIR, f"nav_{kind}.png")


class NavTab(ButtonBehavior, BoxLayout):
    """Uma aba da barra inferior: NavIcon em cima, rótulo embaixo. Ativa =
    accent + rótulo bold; inativa = muted. Sem fundo/pílula (ver ui.kv).
    O visual (children) fica na regra <NavTab> do ui.kv, igual ClayButton."""
    kind = StringProperty("missions")
    label = StringProperty("")
    active = BooleanProperty(False)


class BannerArt(Widget):
    """Banner de fundo do cabeçalho (ver banners.py). Desenha um PADRÃO
    paramétrico no canvas — mesma filosofia dos ícones: nada de imagem, então o
    'personalizado' é o mesmo desenho com outra cor. Redesenha no bind de
    pos/size/pattern/color.

    pattern: none | solid | gradient | stripes | dots | grid | chevron
    color:   rgba base (alfa 0 => não desenha nada = cabeçalho igual a antes)
    """
    pattern = StringProperty("none")
    color = ListProperty([0, 0, 0, 0])
    edge_divider = BooleanProperty(False)  # barra na base (só o do cabeçalho)
    # cor da barra da base. Vem do kv amarrada ao tema (um tom abaixo do
    # destaque): antes o _redraw lia app.accent na hora e não escutava troca de
    # tema, então a barra ficava presa na cor com que o app abriu
    divider_color = ListProperty([0, 0, 0, 0])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self._redraw, size=self._redraw, pattern=self._redraw,
                  color=self._redraw, edge_divider=self._redraw, divider_color=self._redraw)
        self._redraw()

    def _redraw(self, *args):
        self.canvas.before.clear()
        x, y, w, h = self.x, self.y, self.width, self.height
        if w <= 0 or h <= 0 or self.pattern == "none" or self.color[3] == 0:
            return
        r, g, b, _ = self.color
        tint = (min(1.0, r * 1.35 + 0.06), min(1.0, g * 1.35 + 0.06), min(1.0, b * 1.35 + 0.06))

        from kivy.app import App
        _app = App.get_running_app()
        bg = getattr(_app, "bg_app", (0.07, 0.07, 0.07, 1))

        with self.canvas.before:
            # recorta tudo no retângulo do widget (padrões passam da borda)
            StencilPush()
            Rectangle(pos=(x, y), size=(w, h))
            StencilUse()

            Color(rgba=(r, g, b, 1))
            Rectangle(pos=(x, y), size=(w, h))

            if self.pattern == "gradient":
                # fade vertical fake: bandas de bg_app subindo, alfa 0.5 -> 0.
                # nº de bandas proporcional à altura pra não escadear na
                # miniatura pequena nem no cabeçalho baixo
                bands = max(16, int(h / 2))
                for i in range(bands):
                    Color(rgba=(bg[0], bg[1], bg[2], 0.5 * (1 - i / bands)))
                    Rectangle(pos=(x, y + h * i / bands), size=(w, h / bands + 1))
            elif self.pattern == "stripes":
                Color(rgba=(*tint, 0.5))
                step = dp(22)
                off = -h
                while off < w:
                    Line(points=[x + off, y, x + off + h, y + h], width=dp(6))
                    off += step
            elif self.pattern == "dots":
                Color(rgba=(*tint, 0.55))
                rad = dp(3)
                step = dp(18)
                gy = y + step / 2
                row = 0
                while gy < y + h:
                    gx = x + step / 2 + (step / 2 if row % 2 else 0)
                    while gx < x + w:
                        Ellipse(pos=(gx - rad, gy - rad), size=(rad * 2, rad * 2))
                        gx += step
                    gy += step
                    row += 1
            elif self.pattern == "grid":
                Color(rgba=(*tint, 0.4))
                step = dp(20)
                gx = x + step
                while gx < x + w:
                    Line(points=[gx, y, gx, y + h], width=dp(1))
                    gx += step
                gy = y + step
                while gy < y + h:
                    Line(points=[x, gy, x + w, gy], width=dp(1))
                    gy += step
            elif self.pattern == "chevron":
                Color(rgba=(*tint, 0.5))
                step = dp(26)
                amp = dp(9)
                cyc = y - amp
                while cyc < y + h + amp:
                    gx = x
                    while gx < x + w:
                        Line(points=[gx, cyc, gx + step / 2, cyc + amp, gx + step, cyc], width=dp(3))
                        gx += step
                    cyc += step

            # veuzinho por cima pra garantir contraste do texto do cabeçalho
            Color(rgba=(bg[0], bg[1], bg[2], 0.28))
            Rectangle(pos=(x, y), size=(w, h))

            StencilUnUse()
            Rectangle(pos=(x, y), size=(w, h))
            StencilPop()

            # divisória na base: separa o banner do fundo do conteúdo pra não
            # ficarem colados (só o banner do cabeçalho, não as miniaturas).
            if self.edge_divider and self.divider_color[3] > 0:
                Color(rgba=self.divider_color)
                Rectangle(pos=(x, y), size=(w, dp(2)))


class BannerThumb(ButtonBehavior, Widget):
    """Miniatura clicável de um banner (preset ou 'custom') na tela de perfil —
    mostra o padrão em pequeno e um anel quando é o escolhido. Espelha o
    FrameThumb, mas o desenho é um BannerArt embutido."""
    banner_id = StringProperty("")
    pattern = StringProperty("none")
    color = ListProperty([0, 0, 0, 0])
    selected = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self._redraw, size=self._redraw, pattern=self._redraw,
                  color=self._redraw, selected=self._redraw)
        self._redraw()

    def on_release(self):
        from kivy.app import App
        App.get_running_app().set_profile_banner(self.banner_id)

    def _redraw(self, *args):
        self.canvas.after.clear()
        x, y, w, h = self.x, self.y, self.width, self.height
        if w <= 0 or h <= 0:
            return
        with self.canvas.after:
            if self.pattern == "none" or self.color[3] == 0:
                # "sem banner": só um contorno tracejado leve
                Color(rgba=(0.6, 0.6, 0.6, 0.7))
                Line(rounded_rectangle=(x, y, w, h, dp(6)), width=dp(1), dash_offset=4, dash_length=4)
            if self.selected:
                from kivy.app import App
                Color(rgba=getattr(App.get_running_app(), "accent", (1, 1, 1, 1)))
                Line(rounded_rectangle=(x - dp(2), y - dp(2), w + dp(4), h + dp(4), dp(8)), width=dp(2))


class AccentColorWheel(Widget):
    """Roda de cores HSV — o padrão da indústria pra escolher cor: o ÂNGULO é a
    matiz e o RAIO é a saturação (centro branco = sem cor, borda = cor pura).

    Encaixa exatamente no modelo que o app já usa: o tema personalizado é
    gerado de matiz + saturação (main.custom_accent_variants), com o brilho
    fixado por variante pra continuar legível no claro e no escuro. Por isso
    NÃO usa o kivy.uix.colorpicker.ColorWheel: aquele devolve RGBA completo,
    incluindo brilho, que o app descartaria — a pessoa mexeria num controle
    que não faz efeito.

    Emite on_pick(matiz, saturacao) enquanto arrasta.

    O nome NÃO é ColorWheel de propósito: o Kivy já registra uma classe com
    esse nome no Factory (kivy.uix.colorpicker), e o kv resolveria pra ela
    em vez desta — o sintoma é um "AttributeError: pick" ao carregar o kv.
    """
    hue = NumericProperty(0)     # 0-359
    sat = NumericProperty(100)   # 0-100

    _textura = None  # gerada uma vez e reaproveitada por todas as instâncias

    __events__ = ("on_pick",)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(pos=self._redesenhar, size=self._redesenhar,
                  hue=self._redesenhar, sat=self._redesenhar)
        self._redesenhar()

    def on_pick(self, hue, sat):
        pass  # só existe pro bind do kv; quem escuta é o app

    # --- desenho ---
    @classmethod
    def _pegar_textura(cls, lado=128):
        """Gradiente HSV circular, em Python puro mesmo (uma vez só, ~16k
        pixels): é um custo de milissegundos que só acontece quando alguém abre
        a cor personalizada, e evita depender de shader/numpy."""
        if cls._textura is not None:
            return cls._textura

        import colorsys
        import math

        from kivy.graphics.texture import Texture

        raio = lado / 2
        buf = bytearray(lado * lado * 4)
        for py in range(lado):
            dy = py - raio + 0.5
            for px in range(lado):
                dx = px - raio + 0.5
                dist = (dx * dx + dy * dy) ** 0.5 / raio
                i = (py * lado + px) * 4
                if dist > 1.0:
                    continue  # fora do círculo: fica transparente (buf já é 0)
                ang = math.degrees(math.atan2(dy, dx)) % 360
                r, g, b = colorsys.hsv_to_rgb(ang / 360, min(1.0, dist), 1.0)
                buf[i] = int(r * 255)
                buf[i + 1] = int(g * 255)
                buf[i + 2] = int(b * 255)
                # borda suavizada: sem isso o círculo fica serrilhado
                buf[i + 3] = 255 if dist < 0.97 else int(255 * (1 - (dist - 0.97) / 0.03))

        tex = Texture.create(size=(lado, lado), colorfmt="rgba")
        tex.blit_buffer(bytes(buf), colorfmt="rgba", bufferfmt="ubyte")
        cls._textura = tex
        return tex

    def _geometria(self):
        """Círculo centralizado e do maior tamanho que couber no widget."""
        lado = min(self.width, self.height)
        return self.center_x - lado / 2, self.center_y - lado / 2, lado

    def _redesenhar(self, *_):
        import math

        self.canvas.clear()
        x, y, lado = self._geometria()
        if lado <= 1:
            return
        with self.canvas:
            Color(1, 1, 1, 1)
            Rectangle(texture=self._pegar_textura(), pos=(x, y), size=(lado, lado))

            # marcador na posição escolhida: anel branco com contorno escuro,
            # pra continuar visível tanto sobre amarelo quanto sobre azul
            raio = lado / 2
            ang = math.radians(self.hue)
            dist = max(0.0, min(1.0, self.sat / 100)) * raio
            mx = x + raio + math.cos(ang) * dist
            my = y + raio + math.sin(ang) * dist
            Color(0, 0, 0, 0.55)
            Line(circle=(mx, my, dp(9)), width=dp(3))
            Color(1, 1, 1, 1)
            Line(circle=(mx, my, dp(9)), width=dp(1.6))

    # --- toque ---
    def _escolher(self, touch):
        import math

        x, y, lado = self._geometria()
        raio = lado / 2
        dx, dy = touch.x - (x + raio), touch.y - (y + raio)
        dist = (dx * dx + dy * dy) ** 0.5 / raio
        if dist > 1.05:
            return False  # tocou fora da roda (o widget é quadrado, a roda não)
        self.hue = math.degrees(math.atan2(dy, dx)) % 360
        # arrastar pra fora satura no máximo em vez de parar de responder
        self.sat = max(0.0, min(1.0, dist)) * 100
        self.dispatch("on_pick", self.hue, self.sat)
        return True

    def _inerte(self):
        """A seção da cor personalizada colapsa pra height 0 quando não está
        selecionada (ou sem Premium), mas ESTA roda tem size fixo e não encolhe
        junto — a caixa dela continuava cobrindo os botões de tema logo acima e
        engolia o toque deles, porque Widget.on_touch_down não respeita
        `disabled` sozinho (só ButtonBehavior faz isso)."""
        return self.disabled or self.opacity == 0 or self.height <= 1

    def on_touch_down(self, touch):
        if not self._inerte() and self.collide_point(*touch.pos) and self._escolher(touch):
            touch.grab(self)
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            self._escolher(touch)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            return True
        return super().on_touch_up(touch)
