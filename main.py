"""Entrypoint do app. Rodar com: python main.py (dentro da venv do projeto)."""
import colorsys
import functools
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from kivy.animation import Animation
from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import DEFAULT_FONT, LabelBase
from kivy.core.window import Window
from kivy.factory import Factory
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, ObjectProperty, StringProperty
from kivy.uix.modalview import ModalView
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.utils import platform

import account
import achievements
import ads
import android_alarm
import android_picker
import backup
import banners
import challenges
import crash_reporter
import telemetry
import reconquista
# share_card importado sob demanda (dentro de share_streak_card/
# share_milestone_certificate): ele puxa PIL (~110ms) e só serve pra quem
# toca em "compartilhar". Ver comentário no topo de share_card.py.
import charts  # noqa: F401 — registra BarChart/LineChart pro kv achar via <Classe>: (mesmo motivo do widgets.py)
import database as db
import deeplink
import heatmap  # noqa: F401 — registra HeatmapCalendar pro kv achar via <HeatmapCalendar>: (mesmo motivo do widgets.py)
import i18n
import mascot
import mission_suggestions
import missions
import notify
import progress
import reminder_text
import rewards
import settings
import widgets  # noqa: F401 — import só pelo efeito colateral: registra ClayCard/ClayButton/etc pro kv achar via <Classe>:

APP_DIR = Path(__file__).parent

# versão do app pro relato de crash (crash_reporter.py) — manter em sincronia
# com "version" no buildozer.spec a cada release
APP_VERSION = "2.3"  # beta; igual ao version do buildozer.spec, sobe a cada build

# Reregistra a fonte padrão do Kivy (Roboto) pra Candara — tem letras arredondadas
# que combinam com o resto do visual clay. Só existe pré-instalada no Windows; em
# qualquer outra plataforma (Android, Linux, Mac) o arquivo não existe nesse caminho
# — nesse caso mantém o Roboto padrão do Kivy em vez de quebrar a inicialização.
# Como usa o mesmo nome (DEFAULT_FONT), todo widget que não define font_name próprio
# já herda a troca automaticamente.
_CANDARA_REGULAR = r"C:\Windows\Fonts\Candara.ttf"
_CANDARA_BOLD = r"C:\Windows\Fonts\Candarab.ttf"
if platform == "win" and Path(_CANDARA_REGULAR).exists():
    LabelBase.register(DEFAULT_FONT, fn_regular=_CANDARA_REGULAR, fn_bold=_CANDARA_BOLD)

# Fonte só pro título "Discipliner" no cabeçalho — diferente da fonte do resto
# do app (Candara) de propósito, pra dar peso de marca/logo. Trebuchet é
# pré-instalada no Windows; mesmo fallback de plataforma que a Candara acima.
TITLE_FONT = "TrebuchetTitle"
_TREBUCHET_BOLD = r"C:\Windows\Fonts\trebucbd.ttf"
if platform == "win" and Path(_TREBUCHET_BOLD).exists():
    LabelBase.register(TITLE_FONT, fn_regular=_TREBUCHET_BOLD)
else:
    TITLE_FONT = DEFAULT_FONT

# Fonte do "Discipliner" da tela de abertura: Lilita One (Google Fonts, licença
# OFL em assets/fonts/LilitaOne-OFL.txt). Diferente das duas de cima, vem
# EMBUTIDA no app — então aparece igual no celular, não só no Windows.
SPLASH_FONT = "LilitaOne"
_LILITA = APP_DIR / "assets" / "fonts" / "LilitaOne-Regular.ttf"
if _LILITA.exists():
    LabelBase.register(SPLASH_FONT, fn_regular=str(_LILITA))
else:
    SPLASH_FONT = TITLE_FONT

# Paleta clara/escura (fundo, texto) x tema de cor (destaque) são dois eixos
# independentes — dá pra ter "escuro + oceano", "claro + ameixa", etc. As cores
# viram Properties do App (não #:set do kv) de propósito: só assim dá pra trocar
# tudo em tempo real — #:set é uma constante fixa, calculada uma vez só no load do kv.
BASE_THEMES = {
    "light": {
        "bg_app": (0.94, 0.94, 0.98, 1),
        "bg_card": (0.90, 0.91, 0.97, 1),
        "bg_card_soft": (0.97, 0.97, 1.0, 1),
        "danger": (0.90, 0.42, 0.48, 1),
        "success": (0.42, 0.78, 0.62, 1),
        "text_dark": (0.20, 0.20, 0.32, 1),
        "text_light": (1, 1, 1, 1),
        "muted": (0.52, 0.52, 0.66, 1),
    },
    "dark": {
        # preto neutro de verdade (estilo Spotify: #121212/#181818/#282828),
        # sem tingimento azulado — a versão antiga (0.11,0.11,0.15) media só
        # 28/28/38 em 0-255 e puxava pra roxo, não lia como "escuro" de verdade
        "bg_app": (0.071, 0.071, 0.071, 1),
        "bg_card": (0.094, 0.094, 0.094, 1),
        "bg_card_soft": (0.157, 0.157, 0.157, 1),
        "danger": (0.85, 0.40, 0.46, 1),
        "success": (0.45, 0.80, 0.64, 1),
        "text_dark": (0.95, 0.95, 0.95, 1),  # nome ficou do modo claro, mas aqui é "texto principal" = quase branco
        "text_light": (1, 1, 1, 1),
        "muted": (0.70, 0.70, 0.70, 1),
    },
}

# só accent/accent_soft mudam por tema de cor — danger/success ficam fixos de
# propósito (semântica de erro/sucesso não deveria depender do gosto de cor do usuário).
# Cada tema tem par claro/escuro — accent_soft do modo claro é um pastel CLARO pensado
# pra texto escuro em cima; se usasse esse mesmo tom no modo escuro (onde o texto vira
# quase branco), ficaria texto claro sobre fundo claro, ilegível. Por isso cada tema
# também define uma variante escura de verdade (fundo escuro saturado, não só um pastel).
ACCENT_THEMES = {
    "coral": {
        "light": {"accent": (0.95, 0.55, 0.30, 1), "accent_soft": (0.99, 0.85, 0.72, 1)},
        # accent do escuro com a MESMA saturação do claro (mesmo valor/brilho de antes,
        # só sobe a saturação — antes ficava mais "lavado" que o claro sem motivo)
        "dark": {"accent": (0.97, 0.55, 0.31, 1), "accent_soft": (0.34, 0.27, 0.22, 1)},
    },
    "oceano": {
        "light": {"accent": (0.20, 0.55, 0.75, 1), "accent_soft": (0.72, 0.87, 0.94, 1)},
        "dark": {"accent": (0.23, 0.60, 0.85, 1), "accent_soft": (0.16, 0.28, 0.36, 1)},
    },
    "floresta": {
        # verde do mascote Focum (folha/capuz) — amostrado direto de assets/focum/focum_idle.png
        "light": {"accent": (0.53, 0.62, 0.30, 1), "accent_soft": (0.88, 0.92, 0.78, 1)},
        "dark": {"accent": (0.62, 0.72, 0.35, 1), "accent_soft": (0.27, 0.30, 0.18, 1)},
    },
    "ameixa": {
        "light": {"accent": (0.58, 0.36, 0.68, 1), "accent_soft": (0.87, 0.78, 0.91, 1)},
        "dark": {"accent": (0.66, 0.41, 0.78, 1), "accent_soft": (0.30, 0.22, 0.34, 1)},
    },
}


def custom_accent_variants(hue_deg, sat_pct):
    """Gera um tema de cor completo (igual aos 4 fixos de ACCENT_THEMES) a
    partir de só matiz (0-360) e saturação (0-100) — recurso Premium ("Cor
    Personalizada"). Value/luminosidade de cada variante é fixo, escolhido
    pra sempre ficar legível, seguindo a mesma relação dos 4 temas prontos:
    accent do escuro é mais claro/saturado que o do claro (pop no fundo preto),
    accent_soft é sempre um tom bem mais suave que o accent da própria variante."""
    h, s = (hue_deg % 360) / 360, max(0.0, min(1.0, sat_pct / 100))
    return {
        "light": {
            "accent": (*colorsys.hsv_to_rgb(h, s, 0.80), 1),
            "accent_soft": (*colorsys.hsv_to_rgb(h, s * 0.30, 0.94), 1),
        },
        "dark": {
            "accent": (*colorsys.hsv_to_rgb(h, s, 0.90), 1),
            "accent_soft": (*colorsys.hsv_to_rgb(h, s * 0.55, 0.24), 1),
        },
    }

# passos do tutorial guiado — cada um destaca um widget REAL da tela (por id,
# ver ui.kv) com o TutorialOverlay por cima. "target" None = card centralizado
# (boas-vindas / fim). "key" casa com "tutorial_<key>_title/_body" em i18n.py.
# Roda no fim do onboarding e de novo pelo botão "Rever tutorial" em Ajustes.
TUTORIAL_STEPS = [
    {"key": "welcome",     "screen": "missions", "target": None},
    {"key": "add_mission", "screen": "missions", "target": "tut_add_mission"},
    {"key": "suggestions", "screen": "missions", "target": "tut_suggestions"},
    {"key": "complete",    "screen": "missions", "target": "tut_missions_list"},
    {"key": "progress",    "screen": "missions", "target": "tut_progress_bar"},
    {"key": "streak",      "screen": "missions", "target": "tut_streak_card"},
    {"key": "freeze",      "screen": "missions", "target": "tut_freeze_label"},
    {"key": "level",       "screen": "missions", "target": "tut_level_card"},
    {"key": "rewards",     "screen": "missions", "target": "tut_rewards_btn"},
    {"key": "focum",       "screen": "missions", "target": "tut_avatar"},
    {"key": "settings",    "screen": "missions", "target": "tut_settings_tab"},
    {"key": "work_cycle",  "screen": "settings", "target": "tut_cycle_card"},
    {"key": "reminder",    "screen": "settings", "target": "tut_reminder_card"},
    {"key": "backup",      "screen": "settings", "target": "tut_backup_card"},
    {"key": "done",        "screen": "missions", "target": "tut_nav_bar"},
]

# formatos aceitos na foto de perfil (Premium, ver upload_profile_photo) — o
# Pillow lê todos. Também é o texto da legenda embaixo do botão: PHOTO_EXTS é
# a fonte única, o kv monta a legenda a partir dela (ver photo_formats_text).
PHOTO_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif")

# tipo MIME por extensão, pro seletor do Android (o SAF filtra por MIME, não
# por extensão — ver android_picker). O .db não tem MIME registrado, e usar
# "application/octet-stream" é justamente o que deixa QUALQUER arquivo
# selecionável, que é o desejado pra restaurar um backup.
_MIME_POR_EXT = {
    ".db": "application/octet-stream",
    ".png": "image/png",
}

# lado do quadrado em que a foto de perfil é gravada — a moldura do cabeçalho
# é quadrada, então a foto também é (recorte pelo centro, ver upload_profile_photo)
PHOTO_SIZE = 512


def _flatten_to_rgb(img):
    """Achata a imagem em RGB puro sobre fundo branco.

    Sem isso a foto podia aparecer PRETA: converter direto pra RGB descarta o
    canal alfa mantendo o RGB de baixo, que em PNG/WEBP transparente costuma
    ser (0,0,0) — ou seja, todo pedaço transparente vira preto sólido. E modos
    exóticos (P com transparência, LA, CMYK, I;16 de PNG 16-bit) precisam
    passar por RGBA antes, senão a conversão satura e devolve quase tudo preto."""
    from PIL import Image  # import tardio de propósito — o Pillow custa ~110ms no boot
    if img.mode in ("RGBA", "LA", "P", "PA"):
        img = img.convert("RGBA")
        fundo = Image.new("RGB", img.size, (255, 255, 255))
        fundo.paste(img, mask=img.getchannel("A"))
        return fundo
    return img.convert("RGB")


# fonte única em reminder_text.py (o serviço, que não pode importar Kivy, usa
# o mesmo). Mantido como nome aqui porque test_reminder/test_confirm_delete

# de quantas em quantas horas o backup na nuvem roda sozinho (ver
# App._auto_backup_nuvem). Substituiu o botão "Salvar na Nuvem".
AUTO_CLOUD_BACKUP_HORAS = 12

# referenciam main.REMINDER_MESSAGE_COUNT.
REMINDER_MESSAGE_COUNT = reminder_text.MESSAGE_COUNT

# de quanto em quanto tempo a thread do lembrete confere o horário. 20s (e não
# 60s) porque o tick não cai no minuto exato da hora marcada — com 60s o
# lembrete chegava até ~1min depois. Ver App._start_reminder_watcher.
REMINDER_TICK_SECONDS = 20
# quanto tempo depois do horário o app ainda mostra o popup de um lembrete que
# o serviço já notificou (laço do serviço 60s + tick do app 20s, com folga)
REMINDER_POPUP_JANELA = timedelta(minutes=3)

# ponto de corte dos glifos que o Kivy não desenha: ele usa UMA fonte só, sem
# fallback pro sistema, então de setas pra cima (U+2190+) e emoji sai
# quadradinho. Mesmo limite do test_theme.run_glyphs.
_GLIFO_MAX = 0x2190


def _sem_emoji(texto):
    """Tira do texto os glifos que virariam quadradinho num Label do Kivy.

    Só o popup DENTRO do app passa por aqui — a notificação de sistema vai com
    o texto inteiro, porque quem desenha ela é o Android."""
    limpo = "".join(c for c in texto if ord(c) < _GLIFO_MAX)
    return " ".join(limpo.split())  # junta os espaços que sobraram no lugar do emoji


def _prepare_photo(src, dest):
    """Grava em `dest` a foto de perfil pronta: PNG quadrado, sem alfa e com a
    orientação do EXIF já aplicada. Deixa as exceções do Pillow subirem — quem
    chama (upload_profile_photo) é que avisa na tela."""
    from PIL import Image, ImageOps
    img = Image.open(src)
    img.load()  # decodifica agora, pra um arquivo truncado falhar aqui e não na hora de desenhar
    img = ImageOps.exif_transpose(img)  # foto de celular vem deitada sem isso
    img = _flatten_to_rgb(img)
    # recorte quadrado pelo centro: a moldura do cabeçalho é um quadrado fixo,
    # então uma foto retangular ou sobrava dos lados ou deixava faixa vazia
    # dentro do anel. ImageOps.fit corta o excedente do lado maior em vez de
    # espremer a imagem.
    img = ImageOps.fit(img, (PHOTO_SIZE, PHOTO_SIZE), centering=(0.5, 0.5))
    img.save(dest, "PNG")


# telas "normais" do app — switch_screen recusa ir pra qualquer uma delas
# enquanto o onboarding não terminou (ver switch_screen)
MAIN_SCREENS = {"missions", "history", "chart", "badges", "streaks", "settings", "advanced_stats", "rewards_shop", "profile"}

# telas de onboarding: só aparecem na 1ª execução, então não ficam no ui.kv
# (que é parseado todo boot) — moram em screens_onboarding.kv e são carregadas
# sob demanda no 1º switch_screen pra uma delas (ver App._ensure_screen).
_LAZY_SCREEN_KV = "screens_onboarding.kv"
_LAZY_SCREENS = {
    "reset_password": "ResetSenha",  # tela de senha nova (link do e-mail), rara também
    "onboarding_welcome": "OnbWelcome",
    "onboarding_account_choice": "OnbAccountChoice",
    "onboarding_account": "OnbAccount",
}

# ícone do app customizável (recompensa desbloqueável, ver main.set_app_icon
# e android_manifest_extra.xml) — sufixo de classe de cada <activity-alias>,
# "PythonActivity" é a atividade real (ícone padrão, sempre existe)
APP_ICON_ALIASES = {"bronze": "IconBronze", "prata": "IconPrata", "ouro": "IconOuro", "diamante": "IconDiamante"}
APP_ICON_DEFAULT_ACTIVITY = "org.kivy.android.PythonActivity"

# emblemas de sequência DIÁRIA (não semanal/mensal) que valem certificado de
# marco compartilhável (ver BadgeDetailPopup/share_milestone_certificate) —
# mesmos ids de achievements.DEFINITIONS
DAILY_STREAK_MILESTONES = {"streak_3": 3, "streak_7": 7, "streak_14": 14, "streak_30": 30, "streak_100": 100}


class MissionFormPopup(Popup):
    """Usado tanto pra criar quanto editar missão — mission_id None = criar."""
    mission_id = ObjectProperty(None, allownone=True)
    is_daily = BooleanProperty(True)  # controla se o seletor de dias aparece
    follow_cycle = BooleanProperty(False)  # "nos meus dias de folga" em vez de dias fixos (ver missions._cycle_off_today)
    limit_error = StringProperty("")  # "" = sem erro; só se aplica ao CRIAR (editar não é bloqueado)
    reminder_escolhido = StringProperty("")  # "HH:MM", "" = sem lembrete
    _reminder_salvo = ""  # o que já estava no banco, pra saber se a pessoa mexeu

    def _rebuild_day_toggles(self, active_days=()):
        app = App.get_running_app()
        letters = i18n.WEEKDAYS.get(app.language, i18n.WEEKDAYS[i18n.DEFAULT_LANGUAGE])
        container = self.ids.day_toggles
        container.clear_widgets()
        for i, letter in enumerate(letters):
            toggle = Factory.DayToggle()
            toggle.day_index = i
            toggle.label_text = letter
            toggle.active = i in active_days
            container.add_widget(toggle)

    def _selected_days(self):
        return ",".join(str(t.day_index) for t in self.ids.day_toggles.children if t.active)

    def open_for_add(self, periodicity="diaria"):
        app = App.get_running_app()
        self.mission_id = None
        self.title = app.t("popup_new_mission_title")
        self.ids.name_input.text = ""
        self.ids.periodicity_spinner.text = i18n.periodicity_label(periodicity, app.language)
        self.ids.difficulty_spinner.text = i18n.difficulty_label("facil", app.language)
        self.ids.instructions_input.text = ""
        self.ids.confirm_button.text = app.t("btn_add")
        self.limit_error = ""
        self.is_daily = periodicity == "diaria"
        self.follow_cycle = False
        self._rebuild_day_toggles()
        self.reminder_escolhido = ""
        self._reminder_salvo = ""
        self.open()

    def open_for_edit(self, mission_row):
        app = App.get_running_app()
        self.mission_id = mission_row["id"]
        self.title = app.t("popup_edit_mission_title")
        self.ids.name_input.text = mission_row["name"]
        self.ids.periodicity_spinner.text = i18n.periodicity_label(mission_row["periodicity"], app.language)
        self.ids.difficulty_spinner.text = i18n.difficulty_label(mission_row["difficulty"], app.language)
        self.ids.instructions_input.text = mission_row["instructions"] or ""
        self.ids.confirm_button.text = app.t("btn_save")
        self.limit_error = ""
        self.is_daily = mission_row["periodicity"] == "diaria"
        self.follow_cycle = bool(mission_row["follow_cycle"])
        days = mission_row["custom_days"] or ""
        active = {int(d) for d in days.split(",") if d}
        self._rebuild_day_toggles(active)
        self.reminder_escolhido = mission_row["reminder_time"] or ""
        self._reminder_salvo = self.reminder_escolhido
        self.open()

    def escolher_horario(self):
        """Abre o seletor. O botão mostra o horário atual, ou "sem lembrete"."""
        app = App.get_running_app()
        TimePickerPopup().abrir(self.reminder_escolhido or "08:00",
                                app.t("field_mission_reminder"),
                                lambda hm: setattr(self, "reminder_escolhido", hm))

    def selected_reminder_time(self):
        return self.reminder_escolhido

    def confirm(self):
        app = App.get_running_app()
        name = self.ids.name_input.text.strip()
        periodicity = i18n.periodicity_key(self.ids.periodicity_spinner.text, app.language)
        difficulty = i18n.difficulty_key(self.ids.difficulty_spinner.text, app.language)
        # "nos meus dias de folga" e "dias específicos" são mutuamente exclusivos
        # (ver ui.kv) — só um dos dois vale, nunca os dois ao mesmo tempo
        follow_cycle = periodicity == "diaria" and self.follow_cycle and app.cycle_enabled
        custom_days = self._selected_days() if (periodicity == "diaria" and not follow_cycle) else ""
        instructions = self.ids.instructions_input.text.strip()
        # lembrete por missão é recurso Premium — spinner só é editável pra
        # quem já é Premium (ver ui.kv), então isso é só uma trava a mais
        reminder_time = self.selected_reminder_time() if app.is_premium else ""
        if not name:
            return  # validação mínima: nome é obrigatório
        if self.mission_id is None:
            # limite só vale pra CRIAR — editar uma missão que já existe nunca
            # deveria travar (ex.: limite caiu por perder o Premium)
            limit = missions.mission_limit(app.is_premium)
            if len(missions.list_missions()) >= limit:
                self.limit_error = app.t("err_mission_limit").format(limit=limit)
                return
            mission_id = missions.add_mission(name, periodicity, difficulty, custom_days, instructions,
                                               reminder_time, follow_cycle=follow_cycle)
        else:
            mission_id = self.mission_id
            missions.update_mission(self.mission_id, name, periodicity, difficulty, custom_days, instructions,
                                     reminder_time, follow_cycle=follow_cycle)
        # horário NOVO que já passou hoje não pode apitar na hora de salvar —
        # alarme toca no horário marcado, não no clique (ver _suprimir_se_passou)
        if reminder_time != self._reminder_salvo:
            app._suprimir_se_passou(f"m{mission_id}", reminder_time)
        app.refresh_missions()
        # agenda/cancela o alarme (e (des)liga o serviço) do lembrete dessa
        # missão agora — antes só acontecia no próximo boot do app
        app._sincronizar_alarme()
        self.dismiss()
        if reminder_time and android_alarm.disponivel_para_missoes() \
                and not android_alarm.pode_abrir_tela_alarme():
            app.pedir_permissao_tela_alarme()


class RewardFormPopup(Popup):
    """Loja de Recompensas — usado tanto pra criar quanto editar uma
    recompensa (reward_id None = criar). Mesmo padrão do MissionFormPopup."""
    reward_id = ObjectProperty(None, allownone=True)

    def open_for_add(self):
        app = App.get_running_app()
        self.reward_id = None
        self.title = app.t("reward_form_new_title")
        self.ids.reward_name_input.text = ""
        self.ids.reward_cost_input.text = ""
        self.ids.reward_confirm_button.text = app.t("btn_add")
        self.open()

    def open_for_edit(self, reward_row):
        app = App.get_running_app()
        self.reward_id = reward_row["id"]
        self.title = app.t("reward_form_edit_title")
        self.ids.reward_name_input.text = reward_row["name"]
        self.ids.reward_cost_input.text = str(reward_row["cost"])
        self.ids.reward_confirm_button.text = app.t("btn_save")
        self.open()

    def confirm(self):
        name = self.ids.reward_name_input.text.strip()
        cost_text = self.ids.reward_cost_input.text.strip()
        if not name or not cost_text.isdigit() or int(cost_text) <= 0:
            return  # validação mínima: nome preenchido e custo um número positivo
        cost = int(cost_text)
        if self.reward_id is None:
            rewards.add_reward(name, cost)
        else:
            rewards.update_reward(self.reward_id, name, cost)
        App.get_running_app().refresh_rewards()
        self.dismiss()


class CompleteMissionPopup(Popup):
    """Pede a observação no momento de concluir a missão (não na criação)."""
    mission_id = NumericProperty(0)
    checkbox = ObjectProperty(None, allownone=True)
    _confirmed = False

    def confirm(self):
        obs = self.ids.obs_input.text.strip()
        app = App.get_running_app()
        missions.complete_mission(self.mission_id, obs, max_freezes_per_month=app._freeze_cap())
        telemetry.ping("complete", APP_VERSION)
        reconquista.reagendar()  # conclusão nova empurra o próximo aviso pra frente
        self._confirmed = True
        App.get_running_app().refresh_after_complete()
        self.dismiss()

    def cancel(self):
        self.dismiss()

    def on_dismiss(self):
        if not self._confirmed and self.checkbox is not None:
            self.checkbox.checked = False  # desfaz o clique se cancelou/fechou sem concluir


class TextPopup(Popup):
    """Popup genérico só-leitura — política de privacidade, termos de uso."""
    body_text = StringProperty("")

    def open_with(self, title, body):
        self.title = title
        self.body_text = body
        self.open()


class ReminderPopup(Popup):
    """Popup curto do lembrete diário / de missão — a notificação DENTRO do app
    (a de sistema é best-effort, ver App._fire_reminder / notify.py). O alarme
    de missão NÃO passa por aqui: ele tem tela própria (AlarmeView)."""
    message = StringProperty("")

    def open_with(self, title, message):
        self.title = title
        self.message = message
        self.open()


class AlarmeView(ModalView):
    """Tela cheia do alarme de missão no DESKTOP. No Android a tela é nativa
    (android_java/AlarmeActivity.java, ver App.abrir_alarme). Sem notificação:
    só a tela e o toque, que para quando a pessoa encerra (on_dismiss ->
    notify.parar_alarme)."""
    mission_name = StringProperty("")
    horario = StringProperty("")


class TimePickerPopup(Popup):
    """Escolha de horário com +/- em vez de duas listas rolantes.

    Os minutos passaram de 4 opções (00/15/30/45) pra 60, e um Spinner com 60
    itens vira uma lista rolante impossível de mirar no celular. Aqui hora e
    minuto são campos separados, com +/- de 1 e, no minuto, também de 5 (pra
    chegar em :45 sem 45 toques). Ambos dão a volta: 23 -> 00, 59 -> 00.

    Genérico — quem abre passa o horário inicial e recebe "HH:MM" de volta."""
    hora = NumericProperty(0)
    minuto = NumericProperty(0)
    titulo = StringProperty("")
    _acao = ObjectProperty(None, allownone=True)

    def abrir(self, hora_minuto, titulo, on_pick):
        try:
            h, m = (int(p) for p in str(hora_minuto).split(":"))
        except (ValueError, AttributeError):
            h, m = 8, 0   # horário corrompido/vazio: começa num padrão sensato
        self.hora = max(0, min(23, h))
        self.minuto = max(0, min(59, m))
        self.titulo = titulo
        self._acao = on_pick
        self.open()

    def mexer(self, campo, passo):
        if campo == "hora":
            self.hora = (self.hora + passo) % 24
        else:
            self.minuto = (self.minuto + passo) % 60

    def texto(self):
        return f"{self.hora:02d}:{self.minuto:02d}"

    def confirmar(self):
        acao = self._acao
        self._acao = None   # dois toques rápidos não aplicam duas vezes
        self.dismiss()
        if acao is not None:
            acao(self.texto())


class ConfirmPopup(Popup):
    """Pergunta antes de uma ação que não dá pra desfazer (hoje: apagar missão).
    Genérico de propósito — recebe a ação como callback em vez de saber o que
    está sendo apagado."""
    message = StringProperty("")
    confirm_text = StringProperty("")
    _acao = ObjectProperty(None, allownone=True)

    def ask(self, title, message, confirm_text, on_confirm):
        self.title = title
        self.message = message
        self.confirm_text = confirm_text
        self._acao = on_confirm
        self.open()

    def confirm(self):
        acao = self._acao
        self._acao = None  # dois toques rápidos no botão não podem apagar duas vezes
        self.dismiss()
        if acao is not None:
            acao()


class ApagarContaPopup(Popup):
    """Último passo de apagar a conta: o código que chegou por e-mail. Só com
    ele o servidor apaga (ver account.delete_account / delete-account)."""
    email = StringProperty("")
    erro = StringProperty("")

    def abrir(self, email):
        self.email = email
        self.erro = ""
        self.open()

    def confirmar(self):
        App.get_running_app().confirmar_apagar_conta(self, self.ids.codigo_input.text)


class MissionDetailPopup(Popup):
    """Detalhes da missão ao tocar na linha (não no checkbox nem em Editar) —
    mostra o nome inteiro, que a linha trunca com '...' quando é comprido."""
    nome_da_missao = StringProperty("")
    dificuldade = StringProperty("")
    difficulty_key = StringProperty("")  # chave crua ("facil"/"media"/"dificil"), só pra colorir
    periodicidade = StringProperty("")
    pontuacao = StringProperty("")
    instrucoes = StringProperty("")  # texto livre (ex.: os exercícios do treino) — "" = nenhuma

    def open_for(self, mission_row):
        self.nome_da_missao = mission_row["name"]
        self.dificuldade = i18n.difficulty_label(mission_row["difficulty"], App.get_running_app().language)
        self.difficulty_key = mission_row["difficulty"]
        self.periodicidade = i18n.periodicity_label(mission_row["periodicity"], App.get_running_app().language)
        self.pontuacao = str(mission_row["points"])
        self.instrucoes = mission_row["instructions"] or ""
        self.open()


class BadgeDetailPopup(Popup):
    """Detalhes do emblema ao tocar no card em Emblemas — descrição completa
    e o botão de equipar/desequipar como título ao lado do avatar (ver
    DailyQuestApp.toggle_equip_title). Fica aberto depois de tocar em
    Equipar/Desequipar pra dar pra ver o rótulo do botão confirmando a troca."""
    badge_id = StringProperty("")
    nome_do_emblema = StringProperty("")
    descricao = StringProperty("")
    unlocked = BooleanProperty(False)
    equipped = BooleanProperty(False)
    milestone_days = NumericProperty(0)  # >0 pra emblemas de sequência diária — habilita "compartilhar certificado"

    def open_for(self, badge_id, unlocked):
        app = App.get_running_app()
        self.badge_id = badge_id
        self.nome_do_emblema = app.t(f"badge_{badge_id}_name")
        self.descricao = app.t(f"badge_{badge_id}_desc")
        self.unlocked = unlocked
        self.equipped = app.equipped_title == badge_id
        self.milestone_days = DAILY_STREAK_MILESTONES.get(badge_id, 0)
        self.open()

    def toggle_equip(self):
        app = App.get_running_app()
        app.toggle_equip_title(self.badge_id)
        self.equipped = app.equipped_title == self.badge_id


class SuggestionsPopup(Popup):
    """Biblioteca de missões sugeridas, populada pelo app depois de aberta
    (a lista é dinâmica/traduzida, não dá pra montar direto no kv)."""
    pass


class ChallengesPopup(Popup):
    """Pacotes de missões prontos (ver challenges.py), populados pelo app
    depois de aberta — mesma ideia da SuggestionsPopup."""
    pass


AUTH_RESEND_COOLDOWN = 60  # segundos mínimos entre reenvios de código/reset de senha


def _auth_action(cooldown_attr=None):
    """Decorator pros handlers de autenticação (cadastro, login, código por
    e-mail, reset de senha). Trava client-side, complementando o rate limit
    que o Supabase Auth já faz no servidor (ver README > Segurança):

    - reentrada: ignora toques repetidos enquanto uma chamada já está no ar
      (as chamadas são síncronas e podem levar até 10s num 3G ruim — sem isso,
      tocar o botão 10x dispara 10 requisições).
    - cooldown: pros botões de "reenviar código" / "esqueci a senha", exige
      AUTH_RESEND_COOLDOWN segundos entre tentativas (anti flood / anti
      e-mail-bomba). O decorator só CHECA o cooldown (cooldown_attr = nome do
      atributo com o instante de liberação); quem grava é o método, via
      _start_auth_cooldown, e só depois de um envio de verdade acontecer.
    """
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(self, *args, **kwargs):
            if self._auth_in_flight:
                return None
            if cooldown_attr:
                left = getattr(self, cooldown_attr) - time.monotonic()
                if left > 0:
                    self.account_error = self.t("auth_wait_seconds").format(n=int(left) + 1)
                    return None
            self._auth_in_flight = True
            try:
                return fn(self, *args, **kwargs)
            finally:
                self._auth_in_flight = False
        return wrapper
    return deco


class DailyQuestApp(App):
    # selo sobre pose/moldura ainda não desbloqueada (ver AvatarThumb/FrameThumb em ui.kv)
    LOCK_ICON = str(APP_DIR / "assets" / "lock.png")

    progress = NumericProperty(0.0)
    current_screen = StringProperty("missions")
    chart_type = StringProperty("heatmap")  # heatmap | bars | lines
    month_label = StringProperty("")
    total_points = NumericProperty(0)
    streak = NumericProperty(0)
    level = NumericProperty(1)
    xp_progress = NumericProperty(0.0)
    xp_in_level = NumericProperty(0)
    xp_for_next = NumericProperty(missions.LEVEL_XP_BASE)
    permanent_bonus_pct = NumericProperty(0.0)  # bônus permanente de pontos (ver missions.permanent_bonus)

    dark_mode = BooleanProperty(True)
    accent_theme = StringProperty("floresta")
    bg_app = ListProperty(BASE_THEMES["dark"]["bg_app"])
    bg_card = ListProperty(BASE_THEMES["dark"]["bg_card"])
    bg_card_soft = ListProperty(BASE_THEMES["dark"]["bg_card_soft"])
    accent = ListProperty(ACCENT_THEMES["floresta"]["dark"]["accent"])
    accent_soft = ListProperty(ACCENT_THEMES["floresta"]["dark"]["accent_soft"])
    danger = ListProperty(BASE_THEMES["dark"]["danger"])
    success = ListProperty(BASE_THEMES["dark"]["success"])
    text_dark = ListProperty(BASE_THEMES["dark"]["text_dark"])
    text_light = ListProperty(BASE_THEMES["dark"]["text_light"])
    muted = ListProperty(BASE_THEMES["dark"]["muted"])

    ad_banner_visible = BooleanProperty(False)  # reserva o rodapé pro banner do AdMob (ver ads.py)

    has_account = BooleanProperty(False)  # sessão do Supabase ativa (logado)
    _auth_in_flight = False          # trava reentrada dos handlers de auth (ver _auth_action)
    _reset_cooldown_until = 0.0      # idem, "esqueci a senha"
    _delete_cooldown_until = 0.0     # idem, código de apagar a conta
    _reset_tokens = None             # (access, refresh, expires_in) do link de senha nova
    account_status = StringProperty("")  # aviso de sucesso na seção Conta (verde)
    reset_email = StringProperty("")     # conta do link de senha nova
    reset_error = StringProperty("")
    account_awaiting_confirmation = BooleanProperty(False)
    account_mode = StringProperty("signup")  # "signup" ou "login" — mesmo formulário, campos diferentes
    account_name = StringProperty("")
    account_email = StringProperty("")
    account_error = StringProperty("")
    password_visible = BooleanProperty(False)  # botão "mostrar senha" no cadastro
    pix_error = StringProperty("")  # erro ao pedir um Pix novo (Mercado Pago) — ver buy_premium_pix

    language = StringProperty(i18n.DEFAULT_LANGUAGE)

    best_streak = NumericProperty(0)
    streak_freeze_available = BooleanProperty(True)
    # -2 = ainda não calculado (antes do 1º _refresh_stats — ex.: durante o
    # tutorial guiado, que abre a tela de Missões sem refrescar). -1 = ilimitado
    # (Modo Sem Penalidade). >=0 = quantos restam. Ver freeze_status_text.
    streak_freezes_left = NumericProperty(-2)
    streak_semanal = NumericProperty(0)
    streak_mensal = NumericProperty(0)
    best_streak_semanal = NumericProperty(0)
    best_streak_mensal = NumericProperty(0)
    streak_tab = StringProperty("diaria")  # aba ativa na tela de Sequências
    # aba ativa na tela Missões: "diaria" / "semanal" / "mensal"
    mission_view = StringProperty("diaria")
    missions_empty = BooleanProperty(False)
    reminder_enabled = BooleanProperty(False)
    reminder_time = StringProperty("20:00")
    # notificações desligadas nas configs do sistema (permissão negada / canal
    # off) — o card de aviso em Ajustes liga nisso. Ver _atualizar_notif_status.
    notifications_blocked = BooleanProperty(False)
    # memo em memória do que já disparou hoje; a verdade persiste no banco
    # (settings.get_reminders_fired) — ver _fired_today. O lock e o Event são
    # criados por instância no _load_prefs (compartilhar entre instâncias
    # quebraria os testes, que sobem vários apps no mesmo processo).
    _reminder_last_fired = ""  # "YYYY-MM-DD"
    _mission_reminders_fired = {}  # {"m<id>": "YYYY-MM-DD"} — idem, por missão (Premium)

    # ciclo pessoal (escalas rotativas — 12x36, 24x48...), ver missions._cycle_off_today
    cycle_enabled = BooleanProperty(False)
    cycle_length = NumericProperty(7)

    profile_avatar = StringProperty("idle")
    profile_photo_path = StringProperty("")  # "" = usa a pose acima; senão, foto enviada (Premium)
    profile_frame = StringProperty("none")  # moldura decorativa ao redor do avatar — ver mascot.FRAMES
    app_icon = StringProperty("none")  # ícone do app na tela inicial — mesmos tiers de mascot.FRAMES
    # banner de fundo do cabeçalho (ver banners.py). profile_banner é o id
    # escolhido; banner_pattern/banner_color são o resultado já resolvido que o
    # kv (BannerArt do cabeçalho) desenha — recalculados em _apply_banner().
    profile_banner = StringProperty("none")
    custom_banner_hue = NumericProperty(210)
    custom_banner_sat = NumericProperty(45)
    custom_banner_pattern = StringProperty("solid")
    banner_pattern = StringProperty("none")
    banner_color = ListProperty([0, 0, 0, 0])
    _gravar_banner_trigger = None  # debounce da roda do banner, ver pick_custom_banner
    level_rewards_open = BooleanProperty(True)  # seção recolhível na aba Missões
    _gravar_accent_trigger = None  # ver pick_custom_accent
    history_empty = BooleanProperty(False)
    backup_status = StringProperty("")
    share_status = StringProperty("")
    photo_status = StringProperty("")  # erro do envio de foto de perfil (ver upload_profile_photo)
    onboarding_done = BooleanProperty(False)
    tutorial_step = NumericProperty(0)
    tutorial_active = BooleanProperty(False)  # overlay guiado rodando (ver TUTORIAL_STEPS)

    weekly_points = NumericProperty(0)
    weekly_change_pct = NumericProperty(0)
    weekly_best_day = StringProperty("")
    weekly_best_day_points = NumericProperty(0)
    monthly_points = NumericProperty(0)
    monthly_change_pct = NumericProperty(0)
    monthly_best_day = StringProperty("")
    monthly_best_day_points = NumericProperty(0)

    # --- Premium (compra única, ver README > Monetização) ---
    is_premium = BooleanProperty(False)
    no_penalty_mode = BooleanProperty(False)
    custom_accent_hue = NumericProperty(100)
    custom_accent_sat = NumericProperty(55)
    stats_best_weekday = StringProperty("")
    stats_best_weekday_points = NumericProperty(0)
    equipped_title = StringProperty("")  # id do emblema mostrado junto do avatar (ver toggle_equip_title)
    available_points = NumericProperty(0)  # Loja de Recompensas — ver rewards.available_points

    # cada tela pesada só remonta seus widgets quando está visível; fora dela,
    # a mudança fica "suja" e a remontagem acontece ao entrar (ver switch_screen).
    # Montar ~100 linhas de histórico / 21 cards de emblema num refresh de tela
    # que nem está aberta era o grosso da lentidão.
    _history_dirty = True
    _badges_dirty = True
    _adv_stats_dirty = True
    _avatars_dirty = True
    _level_rewards_dirty = True

    def _invalidate_lazy_screens(self):
        """Marca as telas pesadas pra remontar na próxima vez que abrirem.
        Chamado quando os dados que elas mostram mudam (ver _refresh_stats)."""
        self._history_dirty = True
        self._badges_dirty = True
        self._adv_stats_dirty = True
        self._avatars_dirty = True
        self._level_rewards_dirty = True

    def _load_prefs(self):
        """Joga as preferências do banco (app_settings) nas properties do app.
        Chamado no build() e de novo depois de restaurar um backup — o banco
        novo tem outra cor/tema/idioma/avatar/recordes (ver _reload_after_restore)."""
        prefs = settings.get_settings()
        self.language = prefs["language"]
        self.dark_mode = prefs["dark_mode"]
        self.accent_theme = prefs["accent_theme"]
        self.best_streak = prefs["best_streak"]
        self.best_streak_semanal = prefs["best_streak_semanal"]
        self.best_streak_mensal = prefs["best_streak_mensal"]
        self.reminder_enabled = prefs["reminder_enabled"]
        self.reminder_time = prefs["reminder_time"]
        self.profile_avatar = prefs["profile_avatar"]
        self.profile_photo_path = prefs["profile_photo_path"]
        self.profile_frame = prefs["profile_frame"]
        self.app_icon = prefs["app_icon"]
        self.profile_banner = prefs["profile_banner"]
        self.custom_banner_hue = prefs["custom_banner_hue"]
        self.custom_banner_sat = prefs["custom_banner_sat"]
        self.custom_banner_pattern = prefs["custom_banner_pattern"]
        self._apply_banner()
        self.onboarding_done = prefs["onboarding_done"]
        self.is_premium = prefs["is_premium"]
        self.no_penalty_mode = prefs["no_penalty_mode"] and self.is_premium
        self.custom_accent_hue = prefs["custom_accent_hue"]
        self.custom_accent_sat = prefs["custom_accent_sat"]
        self.equipped_title = prefs["equipped_title"]
        self.level_rewards_open = prefs["level_rewards_open"]
        # instância própria (a declaração na classe é um dict mutável
        # compartilhado) e zerada de propósito ao restaurar backup: o banco
        # novo tem outro reminders_fired
        self._reminder_last_fired = ""
        self._mission_reminders_fired = {}
        self._reminder_lock = threading.Lock()
        self._parar_lembrete = threading.Event()
        self._alarme_aberto = None      # a AlarmeView tocando agora, se houver
        self._em_segundo_plano = False  # on_pause/on_resume
        self._screen_history = []  # instância própria (a da classe é lista mutável compartilhada)

    def _reload_after_restore(self):
        """Depois de importar/restaurar um backup: recarrega preferências
        (inclusive a COR/tema do app) e reaplica, pra refletir na hora sem
        precisar reabrir o app."""
        self._load_prefs()
        self._apply_theme()
        self._init_work_cycle_ui()

    def build(self):
        db.init_db()
        crash_reporter.install(APP_VERSION)  # relato remoto de exceção não tratada (anônimo)
        telemetry.ping("open", APP_VERSION)  # retenção anônima, só Android (ver telemetry.py)
        if platform == "android":
            # Android 13+ (API 33+) trata notificação como permissão de RUNTIME
            # — só declarar POST_NOTIFICATIONS no manifest (buildozer.spec) não
            # basta, sem pedir isso aqui toda notificação (lembrete geral, por
            # missão, e o alarme de missão) fica muda e sem erro nenhum, o
            # Android só descarta. Achado investigando por que "nada notifica".
            try:
                from android.permissions import Permission, request_permissions
                request_permissions([Permission.POST_NOTIFICATIONS])
            except Exception as e:
                print(f"[permissao] falha ao pedir POST_NOTIFICATIONS: {e!r}")
        self.title = "Discipliner"
        icon_path = APP_DIR / "assets" / "icon.png"
        if icon_path.exists():
            self.icon = str(icon_path)
        # credenciais do cadastro guardadas só em memória (nunca no banco), pro
        # botão "Já confirmei" poder tentar entrar de novo sem pedir de novo
        self._pending_email = None
        self._pending_password = None
        self._load_prefs()
        Window.clearcolor = BASE_THEMES["dark" if self.dark_mode else "light"]["bg_app"]
        if platform not in ("android", "ios"):
            # só faz sentido forçar esse tamanho na janela de desktop (pra
            # simular a proporção de celular) — no celular de verdade a app
            # já roda em tela cheia no tamanho real, forçar isso aqui deixava
            # o app espremido num retângulo pequeno boiando na tela
            Window.size = (400, 760)
        self.root_widget = Builder.load_file(str(APP_DIR / "ui.kv"))
        # overlay do tutorial guiado: vai direto no Window (flutua por cima de
        # tudo — cabeçalho e abas incluídos) em vez de virar filho do root, que
        # é um BoxLayout e daria uma "fatia" pra ele. Fica escondido até
        # tutorial_start (ver TUTORIAL_STEPS / _position_tutorial). É ANEXADO
        # no on_start, não aqui: o Kivy só adiciona o root_widget ao Window
        # DEPOIS que build() retorna, e Window.add_widget insere no children[0]
        # (topo) — anexar aqui deixava o overlay ATRÁS do root (invisível).
        self.tutorial_overlay = Factory.TutorialOverlay()
        self.tutorial_overlay.hide()
        self._apply_theme()
        # a vinheta entra ANTES de carregar dados de propósito: se o
        # carregamento (querys, gráfico, etc.) rodar aqui dentro do build(),
        # ele consome os primeiros frames em bloco só de CPU e o fade-in
        # perde exatamente os frames que deveriam mostrar a transição suave
        # (o app "pula" pro ícone já opaco em vez de esmaecer nele — pouco
        # perceptível no PC, mas visível no celular, onde o carregamento
        # inicial é mais pesado). O carregamento em si vai pro próximo frame,
        # depois que a janela já está de pé e a animação já começou a rodar.
        self._play_splash()
        Clock.schedule_once(self._load_initial_data, 0)
        return self.root_widget

    def on_start(self):
        # agora o root_widget já está no Window — pôr o overlay AQUI garante que
        # ele entre no children[0] (desenhado por cima do root). Ver build().
        Window.add_widget(self.tutorial_overlay)
        # sem isso o "voltar" do Android (botão ou gesto da navegação por
        # gestos) cai no comportamento padrão do Kivy: encerrar o app. Ou seja,
        # voltar de qualquer tela fechava o Discipliner inteiro.
        Window.bind(on_keyboard=self._on_key)

    # telas visitadas, pra o "voltar" desfazer a navegação em vez de fechar o
    # app. Só nomes, e sem repetir a mesma tela em sequência.
    _screen_history = []

    def _on_key(self, _window, key, *_args):
        """Voltar do Android (e ESC no desktop). True = já tratei, não propague.

        Ordem: fecha o que está por cima primeiro (popup, tutorial), depois
        desfaz a navegação. Só quando não há mais nada pra desfazer é que
        devolve False e deixa o sistema fechar o app — que é o esperado no
        Android quando se está na tela inicial."""
        if key != 27:  # 27 = ESC no desktop e KEYCODE_BACK no Android
            return False

        popup = next((w for w in Window.children if isinstance(w, Popup)), None)
        if popup is not None:
            popup.dismiss()  # vale até pro ConfirmPopup, que tem auto_dismiss desligado
            return True

        if self.tutorial_active:
            if self.tutorial_step > 0:
                self.tutorial_back()
            else:
                self.tutorial_skip()
            return True

        if self._screen_history:
            anterior = self._screen_history.pop()
            self.switch_screen(anterior, _voltando=True)
            return True

        return False  # tela inicial sem histórico: deixa fechar

    def on_resume(self):
        self._em_segundo_plano = False
        telemetry.ping("open", APP_VERSION)  # voltar ao app num dia novo também conta como aberto
        # o Clock do Kivy fica pausado com o app em 2º plano, então
        # _check_reminder não roda enquanto ele está minimizado. Ao voltar,
        # checa na hora em vez de esperar até 60s do próximo tick.
        self._check_reminder(0)
        self._check_mission_reminders(0)
        # a pessoa pode ter ido nas configs do sistema mexer nas notificações
        self._atualizar_notif_status()

    def _atualizar_notif_status(self):
        """Reflete em notifications_blocked se as notificações do app estão
        desligadas no sistema — o card de aviso em Ajustes escuta isso."""
        self.notifications_blocked = not notify.enabled()

    def open_notification_settings(self):
        """Abre a tela de notificações DO APP nas configs do Android."""
        if platform != "android":
            return
        try:
            from jnius import autoclass

            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Intent = autoclass("android.content.Intent")
            Settings = autoclass("android.provider.Settings")
            activity = PythonActivity.mActivity
            intent = Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
            intent.putExtra(Settings.EXTRA_APP_PACKAGE, activity.getPackageName())
            intent.setFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            activity.startActivity(intent)
        except Exception as e:
            print(f"[notify] não consegui abrir as configs de notificação: {e!r}")

    def on_pause(self):
        self._em_segundo_plano = True  # ver _check_mission_reminders_locked
        return True  # mantém o processo vivo em 2º plano (padrão do Kivy no Android)

    def _load_initial_data(self, dt):
        # só o essencial aqui — histórico/gráfico/emblemas montam sozinhos ao
        # abrir cada aba (ver switch_screen). A tela de Missões em si é montada
        # no _finish_splash, quando ela vira a tela ativa.
        self._init_work_cycle_ui()
        ads.init(self)  # AdMob: consentimento + init numa thread (no-op fora do Android/grátis)
        # links dos e-mails voltam pro app (no-op fora do Android)
        deeplink.init({"login-callback": self._on_auth_deeplink,
                       "reset-password": self._on_reset_deeplink})
        # valida a sessão salva já no boot (numa thread — pode ir na rede pra
        # renovar o token). Sem isso, um refresh_token expirado só era
        # detectado quando a pessoa entrava em Ajustes, e até lá a UI mostrava
        # "Premium sem conta" (ver _load_account_async / account._clear_session)
        threading.Thread(target=self._load_account_async, daemon=True).start()
        self._auto_backup_nuvem()
        self._start_reminder_watcher()
        # e reafirma alarmes + serviço do lembrete a cada boot: o Android
        # descarta os alarmes quando o aparelho reinicia ou o app é atualizado
        self._sincronizar_alarme()
        self._atualizar_notif_status()

    def _on_auth_deeplink(self, params):
        """App aberto pelo link de confirmação de e-mail (ver deeplink.py) —
        params traz access_token/refresh_token/expires_in do fragmento da URI."""
        access = params.get("access_token")
        refresh = params.get("refresh_token")
        if not access or not refresh:
            return  # link sem tokens (fluxo token_hash) — usar "Já confirmei, entrar"
        expires_in = params.get("expires_in", "3600")

        def worker():
            try:
                account.complete_deeplink_login(access, refresh, expires_in)
            except Exception as e:
                print(f"[deeplink] login falhou: {e!r}")
                # não falhar calado: link de outro aparelho/expirado abria o app e nada acontecia
                Clock.schedule_once(lambda _dt: setattr(self, "account_error", self.t("err_link_invalid")), 0)
                return
            Clock.schedule_once(lambda _dt: self._after_deeplink_login(), 0)

        threading.Thread(target=worker, daemon=True).start()

    def _after_deeplink_login(self):
        self.account_awaiting_confirmation = False
        self.account_error = ""
        self._pending_email = self._pending_password = None
        self.refresh_account()
        self._apos_entrar()
        # conta: current_session() pode ir na REDE (refresh do token de sessão,
        # timeout de até 10s). Na thread da UI isso congelaria o app logo
        # depois do splash num 3G ruim — então roda numa thread e só volta pra
        # UI (Clock) pra setar as properties.
        threading.Thread(target=self._load_account_async, daemon=True).start()

    def _load_account_async(self):
        session = account.current_session()

        def apply(_dt):
            self.has_account = session is not None
            self.account_awaiting_confirmation = self.account_awaiting_confirmation and not self.has_account
            self.account_name = session["name"] if session else ""
            self.account_email = session["email"] if session else ""
            if session is None:
                # current_session() pode ter feito auto-logout (refresh_token
                # expirou) e zerado o Premium local — _load_prefs já tinha
                # lido o valor antigo pra self.is_premium, relê agora
                self.is_premium = settings.get_settings()["is_premium"]
            self.refresh_avatars()

        Clock.schedule_once(apply, 0)

    def _play_splash(self):
        """Vinheta de abertura: o GIF animado do ícone (splash_icon no kv) com
        um fade curto por cima, ~2s no total. Mascara o carregamento e funciona
        igual no celular e no PC. Ao acabar, decide entre o onboarding
        (primeira execução) e a tela normal."""
        self.switch_screen("splash")
        icon_img = self.root_widget.ids.splash_icon
        icon_img.opacity = 0
        anim = Animation(opacity=1, duration=0.3) + Animation(duration=1.4) + Animation(opacity=0, duration=0.3)
        anim.bind(on_complete=lambda *a: self._finish_splash())
        # adia o início pro próximo frame: iniciar direto aqui usa o relógio
        # de dentro do build() como referência 0, e o primeiro tick da
        # animação já vem com um dt grande (o build() ainda não terminou de
        # verdade) — o fade-in "engole" a si mesmo e o ícone aparece pronto.
        Clock.schedule_once(lambda dt: anim.start(icon_img), 0)

    def _finish_splash(self):
        if self.onboarding_done:
            self.switch_screen("missions")
            self.refresh_missions()  # agora que 'missions' é a tela ativa, monta o conteúdo
        else:
            self.switch_screen("onboarding_welcome")

    # --- traduções (chamadas direto do kv como app.t('chave')) ---
    def t(self, key):
        return i18n.t(key, self.language)

    def periodicity_values(self):
        return list(i18n.PERIODICITY_LABELS[self.language if self.language in i18n.PERIODICITY_LABELS else i18n.DEFAULT_LANGUAGE].values())

    def difficulty_values(self):
        return list(i18n.DIFFICULTY_LABELS[self.language if self.language in i18n.DIFFICULTY_LABELS else i18n.DEFAULT_LANGUAGE].values())

    def is_periodicity_daily(self, label_text):
        return i18n.periodicity_key(label_text, self.language) == "diaria"

    def periodicity_tab_label(self, key):
        return i18n.periodicity_label(key, self.language)

    def language_values(self):
        return list(i18n.LANGUAGES.values())

    def language_label(self):
        return i18n.LANGUAGES.get(self.language, i18n.LANGUAGES[i18n.DEFAULT_LANGUAGE])

    def set_language_from_label(self, label):
        code = next((k for k, v in i18n.LANGUAGES.items() if v == label), None)
        if code and code != self.language:
            self.language = code
            settings.set_language(code)
            # textos pré-montados em Python (não são bindings do kv) precisam ser refeitos
            self.refresh_missions()
            self.refresh_chart()
            self.refresh_badges()
            self.refresh_history()
            self.refresh_advanced_stats()

    # --- tema ---
    def toggle_dark_mode(self):
        self.dark_mode = not self.dark_mode
        self._apply_theme()
        settings.set_dark_mode(self.dark_mode)

    def set_accent_theme(self, theme):
        if theme == "custom" and not self.is_premium:
            return  # cor personalizada é recurso Premium (ver README > Monetização)
        self.accent_theme = theme
        self._apply_theme()
        settings.set_accent_theme(theme)

    def set_custom_accent_hue(self, hue):
        self.custom_accent_hue = hue
        if self.accent_theme == "custom":
            self._apply_theme()
        settings.set_custom_accent(hue, self.custom_accent_sat)

    def set_custom_accent_sat(self, sat):
        self.custom_accent_sat = sat
        if self.accent_theme == "custom":
            self._apply_theme()
        settings.set_custom_accent(self.custom_accent_hue, sat)

    def pick_custom_accent(self, hue, sat):
        """Arrasto na roda de cores (ver widgets.ColorWheel): matiz e saturação
        vêm juntas, e o tema é reaplicado a cada movimento pra pessoa ver a cor
        mudando ao vivo. A GRAVAÇÃO é adiada — um UPDATE no SQLite por evento
        de toque (dezenas por segundo) engasgaria o arrasto à toa."""
        self.custom_accent_hue = hue
        self.custom_accent_sat = sat
        if self.accent_theme == "custom":
            self._apply_theme()
        self._gravar_accent_depois()

    def _gravar_accent_depois(self, *_):
        if self._gravar_accent_trigger is None:
            self._gravar_accent_trigger = Clock.create_trigger(
                lambda _dt: settings.set_custom_accent(
                    self.custom_accent_hue, self.custom_accent_sat),
                0.4,
            )
        self._gravar_accent_trigger()

    def _apply_theme(self):
        mode = "dark" if self.dark_mode else "light"
        if self.accent_theme == "custom" and self.is_premium:
            accent_theme = custom_accent_variants(self.custom_accent_hue, self.custom_accent_sat)
        else:
            accent_theme = ACCENT_THEMES.get(self.accent_theme, ACCENT_THEMES["floresta"])
        theme = {**BASE_THEMES[mode], **accent_theme[mode]}
        for key, value in theme.items():
            setattr(self, key, value)
        Window.clearcolor = theme["bg_app"]  # sem tarja preta nas bordas fora do layout

    # --- Premium (compra única, ver README > Monetização) ---
    def custom_accent_preview(self):
        """Cor de prévia do swatch "Personalizada" — calculada direto dos
        sliders, funciona mesmo antes desse tema estar selecionado de fato."""
        mode = "dark" if self.dark_mode else "light"
        return custom_accent_variants(self.custom_accent_hue, self.custom_accent_sat)[mode]["accent"]

    def toggle_no_penalty_mode(self):
        if not self.is_premium:
            return
        self.no_penalty_mode = not self.no_penalty_mode
        settings.set_no_penalty_mode(self.no_penalty_mode)
        self._refresh_stats()  # o teto de congelamentos muda na hora (ver _freeze_cap)

    def buy_premium(self):
        """Abre o checkout do Stripe (cartão) no navegador — precisa de conta
        (é o user_id que liga a compra a essa conta, ver account.open_purchase_page)."""
        if not self.has_account or self.is_premium:
            return
        account.open_purchase_page()

    def buy_premium_pix(self):
        """Abre o checkout Pix do Mercado Pago (Checkout Pro) no navegador —
        mesmo padrão do buy_premium (Stripe)."""
        if not self.has_account or self.is_premium:
            return
        try:
            account.open_pix_purchase_page()
        except Exception as e:
            self.pix_error = str(e)
            return
        self.pix_error = ""

    def on_is_premium(self, instance, value):
        """Kivy chama sozinho toda vez que is_premium muda (build, compra
        confirmada, logout). Emblema "Apoiador", Modo Sem Penalidade, cor
        personalizada, lembrete por missão... várias telas mudam com o
        Premium — remonta na próxima abertura de cada uma."""
        self._invalidate_lazy_screens()
        if value:
            ads.disable()  # comprou Premium no meio da sessão — some o banner na hora

    def _sync_premium(self):
        """Chamado ao entrar em Ajustes/Perfil — é o momento natural de voltar
        do checkout no navegador, então confere se a compra já confirmou. A
        chamada de rede roda numa thread separada — direto na thread da UI
        (como era antes) travava o app por até 10s (o timeout de
        supabase_client) toda vez que alguém sem Premium abria Ajustes."""
        if not self.has_account or self.is_premium:
            return

        def worker():
            account.sync_premium_status()
            Clock.schedule_once(lambda dt: self._apply_synced_premium(), 0)

        threading.Thread(target=worker, daemon=True).start()

    def check_premium_now(self):
        """Botão "Já paguei" no card do Premium: força a conferência agora, sem
        esperar a pessoa sair e reentrar em Ajustes. O pagamento é confirmado
        por webhook no backend (stripe-webhook / mercadopago-webhook); aqui só
        relemos o resultado da tabela purchases (account.sync_premium_status)."""
        self._sync_premium()

    def _apply_synced_premium(self):
        self.is_premium = settings.get_settings()["is_premium"]

    def open_advanced_stats(self):
        self.switch_screen("advanced_stats")

    def refresh_advanced_stats(self):
        if self.current_screen != "advanced_stats":
            self._adv_stats_dirty = True  # remonta ao abrir (ver switch_screen)
            return
        self._adv_stats_dirty = False
        best = progress.best_weekday_alltime(lang=self.language)
        self.stats_best_weekday = best["label"] if best else ""
        self.stats_best_weekday_points = best["points"] if best else 0

        if "months_stats_list" in self.root_widget.ids:
            container = self.root_widget.ids.months_stats_list
            container.clear_widgets()
            for m in progress.last_months_totals(lang=self.language):
                row = Factory.MonthStatRow()
                row.month_label = m["label"]
                row.points_label = f"{m['points']} {self.t('chart_points_label')}"
                container.add_widget(row)

        if "missions_stats_list" in self.root_widget.ids:
            container = self.root_widget.ids.missions_stats_list
            container.clear_widgets()
            for m in progress.mission_performance():
                row = Factory.MissionStatRow()
                row.mission_name = m["name"]
                row.completions_label = f"{m['completions']}x"
                row.points_label = f"{m['points']} {self.t('chart_points_label')}"
                container.add_widget(row)

    _onboarding_kv_loaded = False

    def _ensure_screen(self, name):
        """Telas de onboarding entram no ScreenManager só quando alguém navega
        pra elas (screens_onboarding.kv só é parseado aí, não em todo boot)."""
        cls = _LAZY_SCREENS.get(name)
        if not cls:
            return
        sm = self.root_widget.ids.screen_manager
        if sm.has_screen(name):
            return
        if not self._onboarding_kv_loaded:
            Builder.load_file(str(APP_DIR / _LAZY_SCREEN_KV))
            DailyQuestApp._onboarding_kv_loaded = True
        sm.add_widget(Factory.get(cls)())

    def switch_screen(self, name, _voltando=False):
        # trava de verdade, não só visual: mesmo que algum toque escape do
        # cabeçalho/barra escondidos (ou de um atalho futuro), o app se
        # recusa a sair do onboarding pra tela principal antes de terminar.
        # Exceção: o tutorial guiado (ainda dentro do onboarding) precisa
        # navegar entre Missões e Ajustes pra destacar os widgets de cada uma.
        if not self.onboarding_done and not self.tutorial_active and name in MAIN_SCREENS:
            return
        # empilha a tela que está saindo, pro "voltar" do Android desfazer a
        # navegação (_on_key). _voltando=True é a própria volta: não reempilha,
        # senão voltar levaria de novo pra onde se estava.
        if not _voltando and name != self.current_screen:
            self._screen_history.append(self.current_screen)
            del self._screen_history[:-20]  # teto: navegação longa não vira vazamento
        self._ensure_screen(name)
        self.root_widget.ids.screen_manager.current = name
        self.current_screen = name
        ads.set_banner_visible(name == "missions")  # banner só na tela de Missões
        # remonta o que ficou "sujo" enquanto essa tela estava fora de vista
        if name == "chart":
            self.refresh_chart()
        elif name == "badges":
            if self._badges_dirty:
                self.refresh_badges()
        elif name == "history":
            if self._history_dirty:
                self.refresh_history()
        elif name == "advanced_stats":
            if self._adv_stats_dirty:
                self.refresh_advanced_stats()
        elif name == "rewards_shop":
            self.refresh_rewards()
        elif name == "missions":
            if self._level_rewards_dirty:
                self.refresh_level_rewards()
        elif name == "settings":
            if self._avatars_dirty:
                self.refresh_avatars()
            self._sync_premium()
        elif name == "profile":
            self._sync_premium()
            self._build_profile_pickers()

    def is_onboarding_screen(self):
        """Splash e onboarding ocupam a tela inteira — sem cabeçalho nem
        barra de abas por cima, ainda não faz sentido navegar pro resto do app."""
        return self.current_screen in (
            "splash", "onboarding_welcome", "onboarding_account_choice",
            "onboarding_account", "reset_password",
        )

    # --- onboarding (primeira execução) ---
    def _onb_ids(self):
        """ids dos campos da tela onboarding_account — que agora é uma classe
        carregada sob demanda (screens_onboarding.kv), não mais parte do
        root_widget, então os ids não sobem pro root_widget.ids."""
        return self.root_widget.ids.screen_manager.get_screen("onboarding_account").ids

    def go_to_account_choice(self):
        self.switch_screen("onboarding_account_choice")

    def go_to_account_form(self, mode="signup"):
        self.account_mode = mode
        self.account_error = ""
        self.switch_screen("onboarding_account")

    def continue_as_guest(self):
        self.start_tutorial()

    @_auth_action()
    def submit_onboarding_account(self):
        """Cadastro ou login, dependendo de account_mode — segue pro tutorial
        nos dois casos, mesmo se o e-mail ainda não foi confirmado (bloquear o
        onboarding esperando o usuário abrir o e-mail seria péssima UX; ele
        termina de confirmar/entrar depois em Ajustes, com calma)."""
        ids = self._onb_ids()
        email = ids.onb_account_email_input.text.strip()
        password = ids.onb_account_password_input.text
        if self.account_mode == "login":
            if not email:
                self.account_error = self.t("err_fill_name_email")
                return
            try:
                account.login(email, password)
            except Exception as e:
                self.account_error = self.t(str(e))
                return
            # link de entrada no e-mail: o deep link entra sozinho depois
            self._pending_email, self._pending_password = email, password
            self.account_awaiting_confirmation = True
        else:
            name = ids.onb_account_name_input.text.strip()
            if not name or not email:
                self.account_error = self.t("err_fill_name_email")
                return
            try:
                account.sign_up(name, email, password)
            except Exception as e:
                self.account_error = self.t(str(e))
                return
        self.account_error = ""
        self.refresh_account()
        self.start_tutorial()

    def start_tutorial(self):
        """Fim do onboarding — dispara o tutorial guiado (TutorialOverlay por
        cima da tela de Missões real). O passo final chama finish_onboarding."""
        self.tutorial_start(from_onboarding=True)

    # --- tutorial guiado (overlay de destaque, ver widgets.TutorialOverlay) ---
    def tutorial_start(self, from_onboarding=False):
        self._tutorial_from_onboarding = from_onboarding
        self.tutorial_active = True
        self.tutorial_overlay.show()
        self.tutorial_goto(0)  # já leva pra tela de Missões (passo 0)
        # ...e monta o conteúdo real dela pros passos não mostrarem os defaults
        # das properties (sequência/nível/congelamento). Depois do goto: aí
        # current_screen já é "missions" e refresh_missions não sai no early-return.
        self.refresh_missions()

    def tutorial_goto(self, i):
        self.tutorial_step = max(0, min(int(i), len(TUTORIAL_STEPS) - 1))
        step = TUTORIAL_STEPS[self.tutorial_step]
        if step["screen"] != self.current_screen:
            self.switch_screen(step["screen"])
        # prazo de parede (não contagem de frames): a 1ª montagem da tela de
        # Ajustes + transição + scroll_to pode levar bem mais que uns frames
        self._tut_reposition_until = time.monotonic() + 2.5
        self._tut_last_rect = None
        Clock.schedule_once(self._position_tutorial, 0)

    def _position_tutorial(self, _dt):
        if not self.tutorial_active:
            return
        step = TUTORIAL_STEPS[self.tutorial_step]
        ov = self.tutorial_overlay
        key = step["key"]
        ov.set_step(
            self.t(f"tutorial_{key}_title"),
            self.t(f"tutorial_{key}_body"),
            f"{self.tutorial_step + 1}/{len(TUTORIAL_STEPS)}",
            self.tutorial_step == 0,
            self.tutorial_step == len(TUTORIAL_STEPS) - 1,
        )
        target = self.root_widget.ids.get(step["target"]) if step["target"] else None
        if target is None:
            ov.show_centered()
            return
        # rola pra vista se o alvo estiver dentro de um ScrollView (Ajustes).
        # Para no Window: Window.parent é o próprio Window (não None), então
        # "while sv.parent" sem essa guarda dá loop infinito.
        sv = target.parent
        while sv is not None and not isinstance(sv, ScrollView):
            nxt = sv.parent
            sv = None if nxt is sv else nxt
        if sv is not None:
            sv.scroll_to(target, padding=dp(24), animate=False)
        # Depois do switch_screen/scroll o alvo pode: (a) não estar preso à
        # janela ainda, (b) ter altura 0 (colapsado no frame), ou (c) — o caso
        # do "slide 14" travado em Ajustes — já estar preso mas com POSIÇÃO
        # velha: scroll_to muda o scroll_y na hora, mas os filhos do ScrollView
        # só reposicionam no próximo layout, então to_window() aqui devolvia
        # um y absurdo (tipo -1784) e o spotlight/card iam pra fora da tela.
        # Tenta de novo até a posição assentar dentro da janela.
        x, y = target.to_window(target.x, target.y)
        ready = (
            target.get_parent_window() is not None
            and target.height > 1
            and -target.height < y < ov.height
            and -target.width < x < ov.width
        )
        # dentro da janela ainda era frouxo demais: um alvo largo (card de
        # largura inteira) passava no teste com um x velho de antes do scroll e
        # o anel ia parar longe do card — é o "Escala rotativa apontando pro
        # lugar errado". Se o alvo mora num ScrollView, o certo depois de
        # scroll_to é o CENTRO dele estar dentro da área visível do scroll.
        if ready and sv is not None:
            sx, sy = sv.to_window(sv.x, sv.y)
            cx, cy = x + target.width / 2, y + target.height / 2
            ready = sx <= cx <= sx + sv.width and sy <= cy <= sy + sv.height

        # e só desenha quando a posição REPETE em dois frames seguidos: um
        # layout no meio do caminho (transição de tela, scroll_to, altura que
        # ainda vai crescer com minimum_height) devolve coordenada boa num
        # frame e outra no seguinte. Vale pra qualquer passo, não só os que já
        # deram problema.
        rect = (round(x), round(y), round(target.width), round(target.height))
        estavel = rect == self._tut_last_rect
        self._tut_last_rect = rect
        if (not ready or not estavel) and time.monotonic() < self._tut_reposition_until:
            Clock.schedule_once(self._position_tutorial, 0)
            return
        ov.spotlight(x, y, target.width, target.height)

    def tutorial_next(self):
        if self.tutorial_step >= len(TUTORIAL_STEPS) - 1:
            self.tutorial_finish()
        else:
            self.tutorial_goto(self.tutorial_step + 1)

    def tutorial_back(self):
        if self.tutorial_step > 0:
            self.tutorial_goto(self.tutorial_step - 1)

    def tutorial_skip(self):
        self.tutorial_finish()

    def tutorial_finish(self, *_):
        self.tutorial_active = False
        self.tutorial_overlay.hide()
        if getattr(self, "_tutorial_from_onboarding", False):
            self.finish_onboarding()
        elif self.current_screen != "missions":
            self.switch_screen("missions")

    def finish_onboarding(self):
        self.onboarding_done = True
        settings.set_onboarding_done()
        self.switch_screen("missions")
        self.refresh_missions()  # 1ª montagem do conteúdo da tela inicial

    def set_chart_type(self, kind):
        self.chart_type = kind

    # --- sequências (mini abas diária/semanal/mensal) ---
    def open_streaks_screen(self):
        self.streak_tab = "diaria"
        self.switch_screen("streaks")

    def switch_streak_tab(self, tab):
        self.streak_tab = tab

    def streak_for_tab(self, tab):
        return {"diaria": self.streak, "semanal": self.streak_semanal, "mensal": self.streak_mensal}[tab]

    def best_streak_for_tab(self, tab):
        return {"diaria": self.best_streak, "semanal": self.best_streak_semanal, "mensal": self.best_streak_mensal}[tab]

    def streak_unit_label(self, tab):
        key = {"diaria": "streak_unit_days", "semanal": "streak_unit_weeks", "mensal": "streak_unit_months"}[tab]
        return self.t(key)

    def streak_multiplier_for_tab(self, tab):
        return missions.streak_multiplier(self.streak_for_tab(tab), tab)

    def streak_next_tier_text(self, tab):
        info = missions.streak_next_tier(self.streak_for_tab(tab), tab)
        if info is None:
            return self.t("streak_max_tier")
        remaining, mult = info
        unit = self.streak_unit_label(tab)
        return self.t("streak_next_tier_prefix") + f" {remaining} {unit} " + self.t("streak_next_tier_suffix") + f" {mult}x"

    def permanent_bonus_text(self):
        """"" se nenhum marco permanente foi batido ainda (ver
        missions.permanent_bonus) — a UI esconde a linha inteira nesse caso."""
        if not self.permanent_bonus_pct:
            return ""
        return self.t("permanent_bonus_note").format(pct=round(self.permanent_bonus_pct * 100))

    # --- missões ---
    def difficulty_color(self, key):
        return {"facil": self.success, "media": self.accent, "dificil": self.danger}.get(key, self.accent)

    def _schedule_label(self, mission_row):
        """"Diária"/"Semanal"/"Mensal" normalmente, ou "S/Q/S" etc. quando a
        missão diária tem dias específicos marcados."""
        days = mission_row["custom_days"] or ""
        if mission_row["periodicity"] != "diaria" or not days:
            return i18n.periodicity_label(mission_row["periodicity"], self.language)
        letters = i18n.WEEKDAYS.get(self.language, i18n.WEEKDAYS[i18n.DEFAULT_LANGUAGE])
        chosen = sorted(int(d) for d in days.split(","))
        return "/".join(letters[i] for i in chosen)

    def refresh_missions(self):
        """Lista só as missões do tipo da aba ativa (mission_view: diária /
        semanal / mensal) — o progresso também é só desse tipo (_refresh_progress)."""
        container = self.root_widget.ids.missions_list
        container.clear_widgets()
        for m in missions.list_missions():
            if m["periodicity"] != self.mission_view:
                continue
            # kv properties dinâmicas (@ syntax) só existem depois do __init__:
            # não dá pra passar como kwargs do construtor, tem que setar depois.
            row = Factory.MissionRow()
            row.mission_id = m["id"]
            row.text_name = m["name"]
            row.text_periodicity = self._schedule_label(m)
            row.text_difficulty = i18n.difficulty_label(m["difficulty"], self.language)
            row.difficulty_key = m["difficulty"]
            row.points = m["points"]
            row.is_challenge = bool(m["challenge_id"])  # selo do multiplicador de Desafio (ver missions.CHALLENGE_MULTIPLIER)
            row.done = missions.is_done_this_period(m)
            row.scheduled = missions.is_scheduled_today(m)
            container.add_widget(row)
        self.missions_empty = not container.children
        self._refresh_progress()
        self._refresh_stats()

    def _refresh_progress(self):
        self.progress = missions.progress_today(self.mission_view)

    def set_mission_view(self, periodicity):
        """Abas Diárias / Semanais / Mensais da tela Missões."""
        if periodicity != self.mission_view:
            self.mission_view = periodicity
            self.refresh_missions()

    def _freeze_cap(self):
        """None = sem limite (Modo Sem Penalidade ligado); senão, o teto de
        congelamentos/mês da diária — maior pra quem é Premium."""
        if self.is_premium and self.no_penalty_mode:
            return None
        return missions.PREMIUM_FREEZE_CAP if self.is_premium else missions.FREE_FREEZE_CAP

    def freeze_status_text(self):
        if self.streak_freezes_left == -2:
            return ""  # ainda não calculado — não afirma nada (nem "ilimitado")
        if self.streak_freezes_left < 0:
            return self.t("streak_freeze_unlimited_note")
        if self.streak_freezes_left > 0:
            return f"{self.t('streak_freeze_available_note')} ({self.streak_freezes_left})"
        return self.t("streak_freeze_used_note")

    def _refresh_stats(self):
        self._invalidate_lazy_screens()  # os dados mudaram — telas fora de vista remontam ao abrir
        cap = self._freeze_cap()
        self.streak = missions.current_streak(periodicity="diaria", max_freezes_per_month=cap)
        self.streak_semanal = missions.current_streak(periodicity="semanal")
        self.streak_mensal = missions.current_streak(periodicity="mensal")
        for periodicity, value, attr in (
            ("diaria", self.streak, "best_streak"),
            ("semanal", self.streak_semanal, "best_streak_semanal"),
            ("mensal", self.streak_mensal, "best_streak_mensal"),
        ):
            if value > getattr(self, attr):
                setattr(self, attr, value)
                settings.set_best_streak(periodicity, value)
        remaining = missions.streak_freezes_remaining(max_freezes_per_month=cap)
        self.streak_freezes_left = -1 if remaining is None else remaining
        self.streak_freeze_available = remaining is None or remaining > 0
        info = missions.level_info()
        self.level = info["level"]
        self.xp_progress = info["progress"]
        self.xp_in_level = info["xp_in_level"]
        self.xp_for_next = info["xp_for_next"]
        self.permanent_bonus_pct = missions.permanent_bonus()
        self.available_points = rewards.available_points()
        summary = progress.weekly_summary(lang=self.language)
        self.weekly_points = summary["total_points"]
        self.weekly_change_pct = summary["change_pct"]
        self.weekly_best_day = summary["best_day_label"]
        self.weekly_best_day_points = summary["best_day_points"]
        monthly = progress.monthly_summary(lang=self.language)
        self.monthly_points = monthly["total_points"]
        self.monthly_change_pct = monthly["change_pct"]
        self.monthly_best_day = monthly["best_day_label"]
        self.monthly_best_day_points = monthly["best_day_points"]
        self.refresh_badges()

    def on_toggle_mission(self, mission_id, active, checkbox):
        if active:
            CompleteMissionPopup(mission_id=mission_id, checkbox=checkbox).open()
        else:
            missions.uncomplete_mission(mission_id)
            self._refresh_progress()
            self._refresh_stats()
            self.refresh_history()

    def refresh_after_complete(self):
        self._refresh_progress()
        self._refresh_stats()  # já invalida emblemas/histórico/etc. e remonta o que estiver visível
        self.refresh_history()
        ads.on_completion()  # conta a conclusão; a cada N dispara o intersticial (grátis/Android)

    def on_remove_mission(self, mission_id):
        """Pergunta antes de apagar — o "×" fica ao lado do "Editar" numa
        linha pequena, e um toque errado apagava a missão na hora, sem desfazer."""
        nome = next((m["name"] for m in missions.list_missions() if m["id"] == mission_id), "")
        if not nome:
            return  # missão já não existe (toque duplo / lista desatualizada)
        Factory.ConfirmPopup().ask(
            self.t("confirm_delete_title"),
            self.t("confirm_delete_mission").format(name=nome),
            self.t("btn_delete"),
            lambda: self.remove_mission_confirmed(mission_id),
        )

    def remove_mission_confirmed(self, mission_id):
        missions.remove_mission(mission_id)
        self.refresh_missions()
        self._sincronizar_alarme()  # cancela o alarme do lembrete da missão apagada

    def open_add_popup(self, periodicity="diaria"):
        # já vem no tipo da aba de onde foi aberto (semanal/mensal)
        MissionFormPopup().open_for_add(periodicity)

    def open_edit_popup(self, mission_id):
        mission = next((m for m in missions.list_missions() if m["id"] == mission_id), None)
        if mission is not None:
            MissionFormPopup().open_for_edit(mission)

    def open_mission_details(self, mission_id):
        mission = next((m for m in missions.list_missions() if m["id"] == mission_id), None)
        if mission is not None:
            Factory.MissionDetailPopup().open_for(mission)

    def open_badge_details(self, badge_id):
        entry = next((e for e in achievements.status() if e["id"] == badge_id), None)
        if entry is not None:
            Factory.BadgeDetailPopup().open_for(badge_id, entry["unlocked"])

    def toggle_equip_title(self, badge_id):
        """Equipa esse emblema como título ao lado do avatar, ou desequipa se
        já era o equipado — só emblemas desbloqueados podem ser equipados."""
        if badge_id not in self.unlocked_badge_ids():
            return
        self.equipped_title = "" if self.equipped_title == badge_id else badge_id
        settings.set_equipped_title(self.equipped_title)

    def open_suggestions_popup(self):
        popup = Factory.SuggestionsPopup()
        popup.open()
        container = popup.ids.suggestions_list
        container.clear_widgets()
        added = missions.added_suggestion_ids()
        for s in mission_suggestions.SUGGESTIONS:
            row = Factory.SuggestionRow()
            row.sugg_id = s["id"]
            row.text_name = self.t(f"sugg_{s['id']}_name")
            row.text_periodicity = i18n.periodicity_label(s["periodicity"], self.language)
            row.text_difficulty = i18n.difficulty_label(s["difficulty"], self.language)
            row.difficulty_key = s["difficulty"]
            row.already_added = s["id"] in added
            container.add_widget(row)

    def add_suggested_mission(self, row):
        """row: a SuggestionRow que chamou (ver ui.kv) — dá pra virar "X" na
        hora, sem precisar refazer o popup inteiro."""
        s = mission_suggestions.get(row.sugg_id)
        if s is None or row.already_added:
            return
        missions.add_mission(
            self.t(f"sugg_{row.sugg_id}_name"), s["periodicity"], s["difficulty"],
            suggestion_id=row.sugg_id,
        )
        row.already_added = True
        self.refresh_missions()

    def open_challenges_popup(self):
        popup = Factory.ChallengesPopup()
        popup.open()
        container = popup.ids.challenges_list
        container.clear_widgets()
        added = missions.added_challenge_ids()
        for c in challenges.CHALLENGES:
            row = Factory.ChallengeRow()
            row.challenge_id = c["id"]
            row.text_name = self.t(f"challenge_{c['id']}_name")
            row.text_desc = self.t(f"challenge_{c['id']}_desc")
            row.already_added = c["id"] in added
            container.add_widget(row)

    def add_challenge(self, row):
        """row: a ChallengeRow que chamou (ver ui.kv) — mesma ideia de
        add_suggested_mission."""
        c = challenges.get(row.challenge_id)
        if c is None or row.already_added:
            return
        # não recria uma missão que já existe: seja porque a sugestão foi
        # adicionada avulsa antes, seja porque outro desafio compartilha o
        # mesmo id (ex.: "review_week" está em "focus" e "finance")
        skip = missions.added_suggestion_ids()
        for sugg_id in c["mission_ids"]:
            if sugg_id in skip:
                continue
            skip.add(sugg_id)
            s = mission_suggestions.get(sugg_id)
            if s is not None:
                missions.add_mission(
                    self.t(f"sugg_{sugg_id}_name"), s["periodicity"], s["difficulty"],
                    challenge_id=row.challenge_id, suggestion_id=sugg_id,
                )
        row.already_added = True
        self.refresh_missions()

    def points_for(self, periodicity_label, difficulty_label):
        # os Spinners mostram o label bonito ("Diária"); a tabela de pontos usa a chave crua ("diaria")
        periodicity = i18n.periodicity_key(periodicity_label, self.language) or "diaria"
        difficulty = i18n.difficulty_key(difficulty_label, self.language) or "facil"
        return missions.points_for(periodicity, difficulty)

    def points_word(self, n):
        return self.t("point_singular") if n == 1 else self.t("point_plural")

    # --- histórico ---
    def refresh_history(self):
        """Agrupa em Hoje / Ontem / Esta Semana / Este Mês / Mais Antigo —
        db.history() já vem ordenado por data desc, então cada balde
        mantém a ordem cronológica reversa só de continuar a percorrer."""
        if self.current_screen != "history":
            self._history_dirty = True  # ~100 linhas: só monta ao abrir a aba (ver switch_screen)
            return
        self._history_dirty = False
        container = self.root_widget.ids.history_list
        container.clear_widgets()
        rows = db.history()
        self.history_empty = len(rows) == 0
        today = date.today()
        buckets = [
            ("history_today", []), ("history_yesterday", []), ("history_this_week", []),
            ("history_this_month", []), ("history_older", []),
        ]
        bucket_by_key = dict(buckets)
        for h in rows:
            delta = (today - date.fromisoformat(h["date"])).days
            if delta <= 0:
                key = "history_today"
            elif delta == 1:
                key = "history_yesterday"
            elif delta <= 7:
                key = "history_this_week"
            elif delta <= 30:
                key = "history_this_month"
            else:
                key = "history_older"
            bucket_by_key[key].append(h)

        for key, items in buckets:
            if not items:
                continue
            header = Factory.HistorySectionLabel()
            header.text = self.t(key)
            container.add_widget(header)
            for h in items:
                row = Factory.HistoryRow()
                row.mission_name = h["mission_name"]
                row.periodicity_text = i18n.periodicity_label(h["periodicity"], self.language)
                row.obs_text = h["obs"] or ""
                row.points_text = f"+{h['points']}"
                row.date_text = date.fromisoformat(h["date"]).strftime("%d/%m")
                container.add_widget(row)

    def sleeping_mascot_path(self):
        return mascot.asset_path(mascot.SLEEPING_FILE)

    def current_avatar_path(self):
        """Pra mostrar o avatar escolhido no canto superior esquerdo do cabeçalho.
        Foto enviada (Premium, ver upload_profile_photo) tem prioridade sobre a
        pose do Focum, enquanto existir uma."""
        if self.profile_photo_path and Path(self.profile_photo_path).exists():
            return self.profile_photo_path
        entry = next((a for a in mascot.AVATARS if a["id"] == self.profile_avatar), mascot.AVATARS[0])
        return mascot.asset_path(entry["file"])

    # --- gráfico ---
    def refresh_chart(self):
        data = progress.monthly_heatmap_data(lang=self.language)
        ids = self.root_widget.ids

        cal = ids.heatmap_calendar
        cal.points_by_day = data["points_by_day"]
        cal.days_in_month = data["days_in_month"]
        cal.first_weekday = data["first_weekday"]
        cal.today_day = data["today_day"]
        cal.weekday_letters = i18n.WEEKDAYS.get(self.language, i18n.WEEKDAYS[i18n.DEFAULT_LANGUAGE])

        for chart in (ids.bar_chart, ids.line_chart):
            chart.points_by_day = data["points_by_day"]
            chart.days_in_month = data["days_in_month"]
            chart.today_day = data["today_day"]

        self.month_label = data["month_label"]
        self.total_points = data["total_points"]

    # --- conta ---
    def refresh_account(self):
        session = account.current_session()
        self.has_account = session is not None
        self.account_awaiting_confirmation = self.account_awaiting_confirmation and not self.has_account
        self.account_name = session["name"] if session else ""
        self.account_email = session["email"] if session else ""
        if session is None:
            # current_session() pode ter feito auto-logout (refresh_token
            # expirou/rotacionou) e zerado o Premium local — reconcilia a
            # property com o banco pra não sobrar "Premium sem conta"
            self.is_premium = settings.get_settings()["is_premium"]
        self.refresh_avatars()

    def toggle_password_visible(self):
        self.password_visible = not self.password_visible

    def toggle_account_mode(self):
        self.account_mode = "login" if self.account_mode == "signup" else "signup"
        self.account_error = ""

    def _start_auth_cooldown(self, attr):
        setattr(self, attr, time.monotonic() + AUTH_RESEND_COOLDOWN)

    @_auth_action()
    def submit_account_form(self):
        ids = self.root_widget.ids
        email = ids.account_email_input.text.strip()
        password = ids.account_password_input.text
        if self.account_mode == "login":
            if not email:
                self.account_error = self.t("err_fill_name_email")
                return
            try:
                account.login(email, password)
            except Exception as e:
                self.account_error = self.t(str(e))
                return
            # link de entrada no e-mail: o deep link entra sozinho depois
            self._pending_email, self._pending_password = email, password
            self.account_awaiting_confirmation = True
        else:
            name = ids.account_name_input.text.strip()
            if not name or not email:
                self.account_error = self.t("err_fill_name_email")
                return
            self._pending_email, self._pending_password = email, password
            try:
                confirmed = account.sign_up(name, email, password)
            except Exception as e:
                self.account_error = self.t(str(e))
                return
            self.account_awaiting_confirmation = not confirmed
        self.account_error = ""
        self.refresh_account()

    @_auth_action()
    def retry_login_after_confirmation(self):
        """Botão 'Reenviar link' na tela de aguardando confirmação — manda um
        link de entrada novo (cadastro já confirmado ou login cujo e-mail
        sumiu). Quem entra é o deep link (_on_auth_deeplink)."""
        if not self._pending_email:
            return
        try:
            account.login(self._pending_email, self._pending_password)
        except Exception as e:
            self.account_error = self.t(str(e))
            return
        self.account_error = ""

    @_auth_action(cooldown_attr="_reset_cooldown_until")
    def request_password_reset(self, email):
        email = email.strip()
        if not email:
            self.account_error = self.t("err_fill_name_email")
            return
        try:
            account.request_password_reset(email)
        except Exception as e:
            self.account_error = self.t(str(e))
            return
        self._start_auth_cooldown("_reset_cooldown_until")  # só trava depois de um envio real
        self.account_error = self.t("reset_email_sent")

    def logout(self):
        account.logout()
        self.is_premium = False  # account.logout() já zera o cache local; reflete na UI
        self.no_penalty_mode = False  # dependia de is_premium (ver build())
        self.refresh_account()

    def save_profile(self):
        """Ajustes > Conta: só o nome de usuário muda por aqui."""
        name = self.root_widget.ids.profile_name_input.text.strip()
        self.account_status = ""
        if not name:
            self.account_error = self.t("err_fill_name_email")
            return
        try:
            account.update_name(name)
        except Exception as e:
            self.account_error = self.t(str(e))
            return
        self.account_error = ""
        self.account_status = self.t("name_saved")
        self.refresh_account()

    @_auth_action(cooldown_attr="_reset_cooldown_until")
    def pedir_troca_senha(self):
        """Link de senha nova no e-mail da conta logada; ele abre o app direto
        na tela reset_password (ver _on_reset_deeplink)."""
        self.account_status = ""
        try:
            account.request_password_reset(self.account_email)
        except Exception as e:
            self.account_error = self.t(str(e))
            return
        self._start_auth_cooldown("_reset_cooldown_until")
        self.account_error = ""
        self.account_status = self.t("password_change_sent")

    def pedir_apagar_conta(self):
        """1º aviso: o que vai ser perdido. Só depois dele o código é enviado."""
        Factory.ConfirmPopup().ask(self.t("delete_account_title"), self.t("delete_account_warning"),
                                   self.t("btn_send_code"), self._enviar_codigo_apagar)

    @_auth_action(cooldown_attr="_delete_cooldown_until")
    def _enviar_codigo_apagar(self):
        try:
            email = account.request_delete_code()
        except Exception as e:
            self.account_error = self.t(str(e))
            return
        self._start_auth_cooldown("_delete_cooldown_until")
        ApagarContaPopup().abrir(email)

    @_auth_action()
    def confirmar_apagar_conta(self, popup, codigo):
        try:
            account.delete_account(codigo)
        except Exception as e:
            popup.erro = self.t(str(e))
            return
        popup.dismiss()
        self._pos_apagar_conta()

    def _pos_apagar_conta(self):
        """Conta e dados apagados: o app volta a ser recém-instalado."""
        self._fim_restore(True, "")  # relê prefs/tema e remonta tudo com o banco vazio
        self.is_premium = False
        self.account_status = self.account_error = ""
        self._screen_history.clear()
        self._sincronizar_alarme()  # sem missões, cancela os alarmes que sobraram
        self.switch_screen("onboarding_welcome")
        Factory.TextPopup().open_with(self.t("delete_account_title"), self.t("account_deleted"))

    def _on_reset_deeplink(self, params):
        """App aberto pelo link do e-mail de senha nova. Valida numa thread (vai
        à rede) e abre a tela dedicada."""
        access = params.get("access_token")
        if not access or params.get("type", "recovery") != "recovery":
            return
        refresh = params.get("refresh_token", "")
        expires_in = params.get("expires_in", "3600")

        def worker():
            try:
                email = account.validar_link_reset(access)
            except Exception as e:
                erro = str(e)
                Clock.schedule_once(lambda _dt: Factory.TextPopup().open_with(
                    self.t("reset_password_title"), self.t(erro)), 0)
                return

            def abrir(_dt):
                self._reset_tokens = (access, refresh, expires_in)
                self.reset_email = email
                self.reset_error = ""
                self.switch_screen("reset_password")

            Clock.schedule_once(abrir, 0)

        threading.Thread(target=worker, daemon=True).start()

    @_auth_action()
    def salvar_nova_senha(self):
        ids = self.root_widget.ids.screen_manager.get_screen("reset_password").ids
        senha = ids.reset_password_input.text
        if senha != ids.reset_password_confirm.text:
            self.reset_error = self.t("err_password_mismatch")
            return
        if not self._reset_tokens:
            self.reset_error = self.t("reset_link_invalid")
            return
        try:
            account.complete_password_reset(*self._reset_tokens, senha)
        except Exception as e:
            self.reset_error = self.t(str(e))
            return
        self._reset_tokens = None
        ids.reset_password_input.text = ids.reset_password_confirm.text = ""
        self.reset_error = ""
        self.refresh_account()
        self.sair_da_tela_senha()
        Factory.TextPopup().open_with(self.t("reset_password_title"), self.t("password_changed"))

    def sair_da_tela_senha(self):
        self._reset_tokens = None
        self.switch_screen("settings" if self.onboarding_done else "onboarding_welcome")

    def open_legal_popup(self, which):
        title_key = "privacy_policy_title" if which == "privacy" else "terms_title"
        body_key = "privacy_policy_text" if which == "privacy" else "terms_of_use_text"
        Factory.TextPopup().open_with(self.t(title_key), self.t(body_key))

    # script do seletor de arquivo do desktop — roda num subprocesso (ver
    # _pick_file). tkinter dentro do loop SDL2 do Kivy (mesma main thread)
    # TRAVA o app: dois toolkits disputando o event loop. Um thread do mesmo
    # processo é frágil (Tcl/Tk não foi feito pra isso). Subprocesso isolado
    # nunca conflita, e o custo (abrir um python) é irrelevante numa ação rara.
    _PICKER_SCRIPT = (
        "import sys, tkinter as tk\n"
        "from tkinter import filedialog\n"
        "r = tk.Tk(); r.withdraw()\n"
        "try: r.attributes('-topmost', True)\n"
        "except Exception: pass\n"
        "mode, pattern, dext, iname, label = sys.argv[1:6]\n"
        "if mode == 'save':\n"
        "    p = filedialog.asksaveasfilename(defaultextension=dext, filetypes=[(label, pattern)], initialfile=iname)\n"
        "else:\n"
        "    p = filedialog.askopenfilename(filetypes=[(label, pattern)])\n"
        "r.destroy()\n"
        "sys.stdout.write(p or '')\n"
    )

    def _pick_file(self, mode, callback, ext=".db", filter_label="Backup Discipliner", initial_name="discipliner_backup.db"):
        """Escolhe um arquivo pra salvar/abrir e chama callback(path_ou_None)
        — SEMPRE assíncrono (via Clock no desktop, via Activity no Android),
        os callers já passam um callback e não usam retorno. No Android o
        seletor nativo vem pelo Storage Access Framework (android_picker);
        no desktop, um subprocesso com tkinter
        (ver _PICKER_SCRIPT). `ext` pode ser uma tupla (a foto de perfil
        aceita .png/.jpg/.jpeg)."""
        exts = (ext,) if isinstance(ext, str) else tuple(ext)
        if android_picker.disponivel():
            # NÃO usa mais o plyer aqui: ele devolve um caminho de arquivo que
            # o Android moderno não deixa abrir, então backup e foto de perfil
            # simplesmente não funcionavam. Ver android_picker.
            # foto aceita vários formatos: "image/*" deixa o seletor mostrar
            # todos eles de uma vez, em vez de travar num único MIME
            if set(exts) <= set(PHOTO_EXTS):
                mime = "image/*"
            else:
                mime = _MIME_POR_EXT.get(exts[0], "application/octet-stream")
            if mode == "save":
                android_picker.salvar_arquivo(callback, mime=mime, nome_sugerido=initial_name)
            else:
                android_picker.escolher_arquivo(callback, mime=mime)
            return

        pattern = " ".join(f"*{e}" for e in exts)

        # sem janela de console piscando no Windows quando o app roda sem console
        no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0) if platform == "win" else 0

        def worker():
            try:
                out = subprocess.run(
                    [sys.executable, "-c", self._PICKER_SCRIPT,
                     mode, pattern, exts[0], initial_name, filter_label],
                    capture_output=True, text=True, timeout=600,
                    creationflags=no_window,
                )
                path = out.stdout.strip()
            except Exception as e:
                print(f"[seletor de arquivo] falhou: {e!r}")
                path = ""
            Clock.schedule_once(lambda _dt: callback(path or None), 0)

        threading.Thread(target=worker, daemon=True).start()

    def export_backup(self):
        def done(path):
            if not path:
                return
            try:
                backup.export_to(path)
            except OSError as e:
                # destino sem permissão / disco cheio / drive removido —
                # avisa em vez de a callback morrer no silêncio
                print(f"[backup] export falhou: {e!r}")
                self.backup_status = self.t("backup_export_failed")
                return
            self.backup_status = self.t("backup_export_success")
        self._pick_file("save", done)

    def import_backup(self):
        def done(path):
            if not path:
                return
            try:
                backup.import_from(path)
            except (backup.InvalidBackupError, OSError):
                self.backup_status = self.t("backup_import_invalid")
                return
            self._reload_after_restore()  # cor/tema/idioma/avatar do banco novo
            self.refresh_missions()
            self.refresh_history()
            self.refresh_chart()
            self.refresh_account()
            self.refresh_badges()
            self.refresh_rewards()
            self.backup_status = self.t("backup_import_success")
        self._pick_file("open", done)

    def _auto_backup_nuvem(self):
        """Backup na nuvem automático, no máximo 1 a cada AUTO_CLOUD_BACKUP_HORAS.

        Substituiu o botão "Salvar na Nuvem": depender de a pessoa lembrar de
        clicar significava, na prática, backup nenhum. Roda NUMA THREAD (vai à
        rede e sobe o banco inteiro) e falha em silêncio — sem conta, sem
        internet ou com a API fora do ar, a única consequência é o carimbo não
        avançar e ele tentar de novo na próxima abertura.

        O carimbo só é gravado DEPOIS do upload dar certo, senão uma falha de
        rede faria o app esperar 12h pra tentar de novo."""
        def worker():
            try:
                session = account.current_session()
                if session is None:
                    return  # convidado: não há pra onde subir
                ultimo = settings.get_settings()["last_cloud_backup"]
                if ultimo:
                    try:
                        passado = datetime.fromisoformat(ultimo)
                    except ValueError:
                        passado = None  # carimbo corrompido: trata como "nunca"
                    if passado and datetime.now() - passado < timedelta(hours=AUTO_CLOUD_BACKUP_HORAS):
                        return
                backup.export_to_cloud(session["access_token"], session["user_id"])
                settings.set_last_cloud_backup(datetime.now().isoformat(timespec="seconds"))
                print("[backup] backup automático na nuvem concluído")
            except Exception as e:
                print(f"[backup] backup automático falhou (tenta de novo depois): {e!r}")

        threading.Thread(target=worker, daemon=True).start()

    def restore_from_cloud(self, automatico=False):
        """Substitui o banco local pelo backup na nuvem dessa conta.

        `automatico=True` é o caminho de quem ACABOU de entrar na conta (ver
        _apos_entrar): entrar já traz o progresso de volta, sem depender de a
        pessoa achar o botão em Ajustes. Nesse caminho, o banco que estava
        aqui é guardado antes em daily_quest.antes-da-nuvem.db — quem entrou
        numa conta depois de usar como convidado não perde o que fez.

        Vai à REDE e troca o arquivo do banco, então roda numa thread; o que
        mexe na interface volta pro Clock (thread da UI)."""
        def worker():
            session = account.current_session()
            if session is None:
                return  # convidado: não há nuvem de onde puxar
            if automatico:
                try:
                    backup.export_to(db.DB_PATH.with_suffix(".antes-da-nuvem.db"))
                except Exception as e:
                    print(f"[backup] cópia de segurança antes do restore falhou: {e!r}")
            try:
                achou = backup.import_from_cloud(session["access_token"], session["user_id"])
            except backup.InvalidBackupError:
                Clock.schedule_once(lambda _dt: self._fim_restore(None, self.t("backup_import_invalid")), 0)
                return
            except Exception as e:
                erro = str(e)
                Clock.schedule_once(lambda _dt: self._fim_restore(None, erro), 0)
                return
            if not achou:
                # conta nova/sem backup não é erro no caminho automático — o
                # primeiro _auto_backup_nuvem sobe o banco daqui a pouco
                aviso = "" if automatico else self.t("backup_cloud_none")
                Clock.schedule_once(lambda _dt: self._fim_restore(None, aviso), 0)
                return
            # o arquivo restaurado é de OUTRO aparelho — reescreve a sessão local
            # com a sessão atual, senão a conta ficaria deslogada (ou pior, com
            # o token de sessão de outro aparelho) depois do restore
            account.restore_session_row(session)
            Clock.schedule_once(lambda _dt: self._fim_restore(True, self.t("backup_import_success")), 0)

        threading.Thread(target=worker, daemon=True).start()

    def _fim_restore(self, ok, status):
        """Parte do restore que mexe na interface — sempre na thread da UI."""
        self.backup_status = status
        if not ok:
            return
        self._reload_after_restore()  # cor/tema/idioma/avatar do banco novo
        self.refresh_missions()
        self.refresh_history()
        self.refresh_chart()
        self.refresh_account()
        self.refresh_badges()
        self.refresh_rewards()

    def _apos_entrar(self):
        """Pós-login comum às 4 portas de entrada (Ajustes, onboarding, "Já
        confirmei" e o deeplink do e-mail de confirmação): puxa o backup da
        nuvem dessa conta."""
        self.restore_from_cloud(automatico=True)

    def share_streak_card(self):
        def done(path):
            if not path:
                return
            import share_card
            streak_word = self.t("streak_day") if self.streak == 1 else self.t("streak_days")
            # total_points é do mês atual (mesmo dado do gráfico) — usa o
            # mesmo rótulo do gráfico pra não parecer que é vitalício
            level_text = f"{self.t('level_prefix')} {self.level} · {self.total_points} {self.t('chart_points_label')}"
            share_card.generate(
                path, self.streak, streak_word, level_text,
                self.current_avatar_path(), self.bg_app, self.accent, self.text_dark,
            )
            self.share_status = self.t("share_success")
        self._pick_file(
            "save", done, ext=".png", filter_label="Imagem PNG",
            initial_name="discipliner_sequencia.png",
        )

    def share_milestone_certificate(self, milestone_days):
        def done(path):
            if not path:
                return
            import share_card
            subtitle = f"{milestone_days} {self.t('streak_day') if milestone_days == 1 else self.t('streak_days')}"
            share_card.generate_certificate(
                path, milestone_days, self.t("certificate_title"), subtitle,
                self.current_avatar_path(), self.bg_app, self.accent, self.text_dark,
            )
            self.share_status = self.t("share_success")
        self._pick_file(
            "save", done, ext=".png", filter_label="Imagem PNG",
            initial_name=f"discipliner_certificado_{milestone_days}.png",
        )

    # --- emblemas ---
    def _sync_equipped_title(self):
        """Barato (1 query): se o emblema equipado como título re-bloqueou (ex.:
        perdeu o Premium), tira ele. Roda sempre; o rebuild pesado dos cards da
        aba Emblemas é lazy (ver refresh_badges)."""
        if self.equipped_title and self.equipped_title not in self.unlocked_badge_ids():
            self.equipped_title = ""
            settings.set_equipped_title("")

    def refresh_badges(self):
        if "badges_list" not in self.root_widget.ids:
            return  # tela ainda não foi construída na primeira chamada de build()
        self._sync_equipped_title()
        self.refresh_avatars()        # aba Ajustes — tem sua própria guarda de visibilidade
        self.refresh_level_rewards()  # aba Missões — idem
        if self.current_screen != "badges":
            self._badges_dirty = True  # remonta ao abrir a aba (ver switch_screen)
            return
        self._badges_dirty = False
        container = self.root_widget.ids.badges_list
        container.clear_widgets()
        for entry in achievements.status():
            card = Factory.BadgeCard()
            card.badge_id = entry["id"]
            card.name_text = self.t(f"badge_{entry['id']}_name")
            card.desc_text = self.t(f"badge_{entry['id']}_desc")
            card.unlocked = entry["unlocked"]
            card.preview_img = mascot.reward_preview_path(entry["id"])
            if not card.preview_img:  # sem pose: a recompensa pode ser uma moldura
                card.preview_frame_color = mascot.reward_frame_color(entry["id"]) or [0, 0, 0, 0]
            container.add_widget(card)

    def refresh_level_rewards(self):
        """Preview das recompensas de nível (emblemas 'level_*') — mostrado na
        aba Missões, junto do cartão de nível, pra dar um gostinho do que vem
        a seguir sem precisar ir até a aba Emblemas."""
        if "level_rewards_list" not in self.root_widget.ids:
            return
        if not self.level_rewards_open:
            self._level_rewards_dirty = True  # remonta quando reabrir (ver toggle_level_rewards)
            return
        if self.current_screen != "missions":
            self._level_rewards_dirty = True
            return
        self._level_rewards_dirty = False
        container = self.root_widget.ids.level_rewards_list
        container.clear_widgets()
        for entry in achievements.status():
            if not entry["id"].startswith("level_"):
                continue
            card = Factory.BadgeCard()
            card.size_hint_x = None
            card.width = dp(170)
            card.name_text = self.t(f"badge_{entry['id']}_name")
            card.desc_text = self.t(f"badge_{entry['id']}_desc")
            card.unlocked = entry["unlocked"]
            card.preview_img = mascot.reward_preview_path(entry["id"])
            container.add_widget(card)

    # --- Loja de Recompensas (ver rewards.py) ---
    def refresh_rewards(self):
        self.available_points = rewards.available_points()
        ids = self.root_widget.ids
        if "rewards_list" in ids:
            container = ids.rewards_list
            container.clear_widgets()
            for r in rewards.list_rewards():
                row = Factory.RewardRow()
                row.reward_id = r["id"]
                row.reward_name = r["name"]
                row.cost = r["cost"]
                container.add_widget(row)
        if "reward_history_list" in ids:
            container = ids.reward_history_list
            container.clear_widgets()
            for h in rewards.redemption_history():
                row = Factory.RewardHistoryRow()
                row.reward_name = h["reward_name"]
                row.cost = h["cost"]
                row.redeemed_at = date.fromisoformat(h["redeemed_at"]).strftime("%d/%m")
                container.add_widget(row)

    def open_add_reward_popup(self):
        Factory.RewardFormPopup().open_for_add()

    def open_edit_reward_popup(self, reward_id):
        reward = next((r for r in rewards.list_rewards() if r["id"] == reward_id), None)
        if reward is not None:
            Factory.RewardFormPopup().open_for_edit(reward)

    def on_remove_reward(self, reward_id):
        """Pergunta antes de apagar, mesma razão da missão (ver
        on_remove_mission): o "×" fica encostado no "Editar" numa linha
        pequena, e apagar não tem desfazer."""
        nome = next((r["name"] for r in rewards.list_rewards() if r["id"] == reward_id), "")
        if not nome:
            return  # recompensa já não existe (toque duplo / lista desatualizada)
        Factory.ConfirmPopup().ask(
            self.t("confirm_delete_reward_title"),
            self.t("confirm_delete_reward").format(name=nome),
            self.t("btn_delete"),
            lambda: self.remove_reward_confirmed(reward_id),
        )

    def remove_reward_confirmed(self, reward_id):
        rewards.remove_reward(reward_id)
        self.refresh_rewards()

    def redeem_reward(self, reward_id):
        try:
            rewards.redeem(reward_id)
        except rewards.NotEnoughPointsError:
            return  # botão já fica desabilitado sem pontos suficientes (ver ui.kv) — segunda trava
        self.refresh_rewards()

    # --- foto de perfil (Focum) ---
    def unlocked_badge_ids(self):
        return {e["id"] for e in achievements.status() if e["unlocked"]}

    def _build_avatar_thumbs(self, container):
        """Preenche `container` com um AvatarThumb por pose — usado tanto pela
        lista da tela de Ajustes quanto pelo popup do cabeçalho. Retorna os
        thumbs criados, pra quem chamou poder ligar comportamento extra neles
        (ex.: fechar o popup ao escolher)."""
        container.clear_widgets()
        thumbs = []
        for entry in mascot.avatar_status(self.unlocked_badge_ids()):
            if not entry["path"]:
                continue  # arte da pose ainda não existe (ver mascot.py) — não mostra quadrado em branco
            thumb = Factory.AvatarThumb()
            thumb.avatar_id = entry["id"]
            thumb.img_path = entry["path"]
            thumb.unlocked = entry["unlocked"]
            container.add_widget(thumb)
            thumbs.append(thumb)
        return thumbs

    def refresh_avatars(self):
        if "avatar_list" not in self.root_widget.ids:
            return
        if self.current_screen != "settings":
            self._avatars_dirty = True  # remonta ao abrir Ajustes (ver switch_screen)
            return
        self._avatars_dirty = False
        self._build_avatar_thumbs(self.root_widget.ids.avatar_list)

    def _build_frame_thumbs(self, container, action="frame"):
        """Mesma ideia do _build_avatar_thumbs, mas pras molduras/ícones do
        app — sem arquivo de imagem no SELETOR (o anel colorido já basta pra
        essa miniatura pequena; a arte de verdade só aparece equipada, no
        cabeçalho — ver App.current_frame_path), então nunca pula nenhuma.
        action="icon" reaproveita o mesmo widget/tiers pro seletor de ícone
        do app (ver widgets.FrameThumb)."""
        container.clear_widgets()
        for entry in mascot.frame_status(self.unlocked_badge_ids()):
            thumb = Factory.FrameThumb()
            thumb.frame_id = entry["id"]
            thumb.frame_color = entry["color"] or [0.6, 0.6, 0.6, 1]  # "none" usa um cinza neutro pro anel
            thumb.unlocked = entry["unlocked"]
            thumb.action = action
            container.add_widget(thumb)

    def open_profile_screen(self):
        """Abre a tela de personalização de perfil (banner, foto, moldura,
        ícone) — antes era um popup no toque do avatar, virou tela de verdade."""
        self.switch_screen("profile")

    def _build_profile_pickers(self):
        """(Re)monta as 4 listas da tela de perfil. Chamado ao entrar na tela
        (ver switch_screen) — as listas são dinâmicas (poses/molduras
        desbloqueadas, banners) e traduzidas, não dá pra montar no kv."""
        ids = self.root_widget.ids
        if "prof_avatar_list" not in ids:
            return
        self._build_avatar_thumbs(ids.prof_avatar_list)
        self._build_frame_thumbs(ids.prof_frame_list)
        self._build_frame_thumbs(ids.prof_icon_list, action="icon")
        self._build_banner_thumbs(ids.prof_banner_list)

    def _build_banner_thumbs(self, container):
        container.clear_widgets()
        for entry in banners.BANNERS:
            thumb = Factory.BannerThumb()
            thumb.banner_id = entry["id"]
            pat, col = banners.resolve(entry["id"])
            thumb.pattern = pat
            thumb.color = list(col)
            thumb.selected = self.profile_banner == entry["id"]
            container.add_widget(thumb)

    def _mark_banner_selection(self):
        """Só atualiza o anel de selecionado nos thumbs já montados — NÃO
        remonta a lista. Remontar no on_release do próprio thumb destruía o
        widget no meio do toque ('os botões do banner clicam raramente')."""
        if self.current_screen != "profile" or "prof_banner_list" not in self.root_widget.ids:
            return
        for thumb in self.root_widget.ids.prof_banner_list.children:
            if hasattr(thumb, "banner_id"):
                thumb.selected = thumb.banner_id == self.profile_banner

    def _apply_banner(self):
        """Recalcula banner_pattern/banner_color (o que o kv desenha) a partir
        do banner escolhido + os valores do personalizado."""
        self.banner_pattern, col = banners.resolve(
            self.profile_banner, self.custom_banner_hue,
            self.custom_banner_sat, self.custom_banner_pattern)
        self.banner_color = list(col)

    def set_profile_banner(self, banner_id):
        # "custom" só entra pelo fluxo próprio (pick_custom_banner) — Premium;
        # os presets são livres.
        if banner_id == "custom" and not self.is_premium:
            return
        settings.set_profile_banner(banner_id)
        self.profile_banner = banner_id
        self._apply_banner()
        self._mark_banner_selection()

    def set_custom_banner_pattern(self, pattern):
        if not self.is_premium or pattern not in banners.PATTERNS:
            return
        self.custom_banner_pattern = pattern
        self.profile_banner = "custom"
        settings.set_profile_banner("custom")
        settings.set_custom_banner(self.custom_banner_hue, self.custom_banner_sat, pattern)
        self._apply_banner()
        self._mark_banner_selection()

    def pick_custom_banner(self, hue, sat):
        """Arrasto na roda HSV do banner personalizado (Premium). Grava
        debounced, igual pick_custom_accent — arrastar dispara isto muitas
        vezes por segundo."""
        if not self.is_premium:
            return
        self.custom_banner_hue = hue
        self.custom_banner_sat = sat
        self.profile_banner = "custom"
        self._apply_banner()
        self._mark_banner_selection()
        if self._gravar_banner_trigger is None:
            self._gravar_banner_trigger = Clock.create_trigger(
                lambda _dt: (settings.set_profile_banner("custom"),
                             settings.set_custom_banner(self.custom_banner_hue,
                                                        self.custom_banner_sat,
                                                        self.custom_banner_pattern)),
                0.4)
        self._gravar_banner_trigger()

    def set_profile_avatar(self, avatar_id):
        entry = next((a for a in mascot.avatar_status(self.unlocked_badge_ids()) if a["id"] == avatar_id), None)
        if entry and entry["unlocked"]:
            settings.set_profile_avatar(avatar_id)
            self.profile_avatar = avatar_id
            # escolher uma pose do Focum volta a usá-la; a foto enviada (se
            # tinha uma) é apagada do aparelho junto — cada envio grava um
            # arquivo com nome novo, então não dá pra deixar sobrando
            antiga = self.profile_photo_path
            settings.set_profile_photo_path("")
            self.profile_photo_path = ""
            if antiga:
                Path(antiga).unlink(missing_ok=True)

    def upload_profile_photo(self):
        """Recurso Premium — escolhe uma imagem e usa como foto de perfil,
        substituindo a pose do Focum enquanto existir (ver current_avatar_path).
        Redimensiona pra não guardar uma foto gigante nem deixar a UI lenta
        carregando ela toda vez; só cabe 1 foto enviada por vez (a anterior é
        apagada)."""
        if not self.is_premium:
            return

        def done(path):
            if not path:
                return
            from PIL import UnidentifiedImageError
            # nome novo a cada envio: o Kivy guarda a textura em cache pelo
            # NOME do arquivo (Cache 'kv.image'), então reescrever sempre o
            # mesmo profile_photo.png mostrava a foto velha (ou uma textura
            # meio carregada) em vez da nova
            dest = db.DB_PATH.parent / f"profile_photo_{int(time.time())}.png"
            try:
                _prepare_photo(path, dest)
            except (UnidentifiedImageError, OSError, ValueError, SyntaxError) as e:
                # formato não suportado / arquivo corrompido — a foto atual (ou
                # a pose do Focum) continua valendo, mas agora AVISA: antes
                # isso era um print silencioso e parecia que o botão não fazia nada
                print(f"[foto de perfil] arquivo inválido, ignorado: {e!r}")
                self.photo_status = self.t("photo_invalid")
                return
            antiga = self.profile_photo_path
            settings.set_profile_photo_path(str(dest))
            self.profile_photo_path = str(dest)
            self.photo_status = ""
            if antiga and antiga != str(dest):
                Path(antiga).unlink(missing_ok=True)

        def escolhido(path):
            try:
                done(path)
            finally:
                # o seletor do Android entrega uma CÓPIA temporária do
                # content:// (ver android_picker); depois de processada não
                # serve mais pra nada
                if path and android_picker.disponivel():
                    Path(path).unlink(missing_ok=True)

        self.photo_status = ""
        # _pick_file já roteia pro Storage Access Framework no Android (ver
        # android_picker) — não precisa mais do desvio que existia aqui
        self._pick_file("open", escolhido, ext=PHOTO_EXTS, filter_label="Imagem")

    def photo_formats_text(self):
        """Legenda embaixo do botão de enviar foto — "Formatos: PNG, JPG, ...".
        Montada a partir de PHOTO_EXTS pra nunca discordar do que o seletor
        de arquivo realmente aceita."""
        return self.t("photo_formats") + " " + ", ".join(e[1:].upper() for e in PHOTO_EXTS)

    def toggle_level_rewards(self):
        self.level_rewards_open = not self.level_rewards_open
        settings.set_level_rewards_open(self.level_rewards_open)
        if self.level_rewards_open:
            self.refresh_level_rewards()  # ficou marcada como suja enquanto recolhida

    def current_frame_color(self):
        """RGBA da moldura equipada, ou totalmente transparente se nenhuma —
        pra usar direto num Color: do canvas sem precisar checar "none" no kv."""
        return mascot.frame_color(self.profile_frame) or [0, 0, 0, 0]

    def current_frame_path(self):
        """Caminho do PNG da moldura equipada, ou "" se nenhuma/arquivo
        ausente — quem usa tem que colapsar o tamanho da Image nesse caso
        (source vazio pinta um retângulo branco, não fica invisível sozinho)."""
        return mascot.frame_path(self.profile_frame)

    def current_frame_scale(self):
        """1.0 = tamanho normal — algumas molduras pedem um pouco mais (ver
        mascot.FRAMES > scale) pra cobrir direito o fundo da foto."""
        return mascot.frame_scale(self.profile_frame)

    def set_profile_frame(self, frame_id):
        entry = next((f for f in mascot.frame_status(self.unlocked_badge_ids()) if f["id"] == frame_id), None)
        if entry and entry["unlocked"]:
            settings.set_profile_frame(frame_id)
            self.profile_frame = frame_id

    def set_app_icon(self, icon_id):
        """Troca o ícone do app na tela inicial do celular — recompensa
        desbloqueável, MESMOS marcos das molduras de avatar (ver
        mascot.FRAMES: bronze/prata/ouro/diamante). "none" = ícone padrão.

        Só existe de verdade no Android (usa PackageManager via pyjnius —
        "tela inicial" nem é um conceito no PC). Liga a activity-alias
        escolhida e desliga TODAS as outras (inclusive a PythonActivity
        "de base"), senão apareceriam 2 ícones juntos na tela inicial —
        técnica padrão de troca de ícone, mas essa parte especificamente
        não dá pra confirmar rodando local, só num Android de verdade."""
        if icon_id != "none":
            entry = next((f for f in mascot.frame_status(self.unlocked_badge_ids()) if f["id"] == icon_id), None)
            if not (entry and entry["unlocked"]):
                return
        if platform == "android":
            try:
                from jnius import autoclass
                ComponentName = autoclass("android.content.ComponentName")
                PackageManager = autoclass("android.content.pm.PackageManager")
                PythonActivity = autoclass("org.kivy.android.PythonActivity")
                context = PythonActivity.mActivity
                package_name = context.getPackageName()
                pm = context.getPackageManager()
                targets = {"none": APP_ICON_DEFAULT_ACTIVITY}
                targets.update({k: f"{package_name}.{v}" for k, v in APP_ICON_ALIASES.items()})
                for candidate_id, component in targets.items():
                    state = (
                        PackageManager.COMPONENT_ENABLED_STATE_ENABLED if candidate_id == icon_id
                        else PackageManager.COMPONENT_ENABLED_STATE_DISABLED
                    )
                    pm.setComponentEnabledSetting(
                        ComponentName(package_name, component), state, PackageManager.DONT_KILL_APP,
                    )
            except Exception as e:
                print(f"[app_icon] falha ao trocar o ícone: {e!r}")
                return
        settings.set_app_icon(icon_id)
        self.app_icon = icon_id

    # --- lembrete diário. App aberto/minimizado: thread _start_reminder_watcher.
    # App fechado: serviço permanente + AlarmManager (ver _sincronizar_alarme,
    # android_alarm, service_reminder). Reboot ainda depende de reabrir o app
    # uma vez — ver LIMITACOES.md. ---
    def escolher_horario_lembrete(self):
        TimePickerPopup().abrir(self.reminder_time, self.t("reminder_time_label"),
                                self.set_reminder_time)

    def toggle_reminder_enabled(self):
        self.reminder_enabled = not self.reminder_enabled
        settings.set_reminder(self.reminder_enabled, self.reminder_time)
        self._suprimir_lembrete_de_hoje()
        self._sincronizar_alarme()

    def set_reminder_time(self, hora_minuto):
        self.reminder_time = hora_minuto
        settings.set_reminder(self.reminder_enabled, self.reminder_time)
        self._suprimir_lembrete_de_hoje()
        self._sincronizar_alarme()

    def _suprimir_se_passou(self, chave, horario):
        """Marca `chave` como entregue hoje se `horario` JÁ PASSOU — sem
        notificar. Chamado no momento em que a pessoa ESCOLHE o horário.

        Sem isso, marcar 08:00 às 20:00 disparava o lembrete NA HORA do
        clique: a checagem só compara `agora >= horario`. Vale pro lembrete
        diário e pro alarme de cada missão (que ainda por cima apita). O
        catch-up dos dias seguintes continua valendo — só o dia corrente é
        suprimido."""
        if not horario or datetime.now().strftime("%H:%M") < horario:
            return  # ainda vai acontecer hoje: deixa disparar normalmente
        self._remember_fired(chave)  # grava no banco e no memo em memória

    def _suprimir_lembrete_de_hoje(self):
        if self.reminder_enabled:
            self._suprimir_se_passou("daily", self.reminder_time)

    def _sincronizar_alarme(self):
        """Põe os alarmes do sistema E o serviço do lembrete de acordo com o
        estado atual. Chamado no boot e a cada mudança de lembrete (diário ou
        de missão). Fora do Android é no-op.

        Quem entrega a notificação com o app FECHADO: o AlarmManager. No
        horário exato (`setAlarmClock`) ele acorda o serviço, que notifica,
        reagenda e SAI. O serviço NÃO fica de pé — antes ficava, e a
        consequência era o app aparecer em segundo plano o tempo todo com uma
        notificação permanente na barra."""
        if self.reminder_enabled:
            android_alarm.agendar(self.reminder_time)
        else:
            android_alarm.cancelar()
        self._sincronizar_alarmes_missao()
        reconquista.reagendar()  # aviso pra quem some (ver reconquista.py)
        # versões anteriores subiam um serviço PERMANENTE (:foreground:sticky).
        # Quem atualiza vindo delas pode ter esse serviço ainda de pé, com a
        # notificação fixa na barra; derruba uma vez aqui.
        android_alarm.parar_servico_lembrete()

    def _sincronizar_alarmes_missao(self):
        """Alarmes dos lembretes por missão (Premium). Sem Premium, cancela
        todos — senão um alarme antigo sobreviveria à perda do benefício."""
        if not android_alarm.disponivel_para_missoes():
            return
        horarios = [(m["id"], m["reminder_time"] if self.is_premium else "")
                    for m in missions.list_missions()]
        android_alarm.sincronizar_missoes(horarios)

    # --- ciclo pessoal (escalas rotativas — 12x36, 24x48...), ver
    # missions._cycle_off_today e docs/superpowers/specs/2026-08-28-ciclo-pessoal-design.md ---
    def cycle_length_values(self):
        return [str(n) for n in range(2, 16)]

    def _rebuild_cycle_day_toggles(self, active_days=()):
        container = self.root_widget.ids.cycle_day_toggles
        container.clear_widgets()
        for i in range(self.cycle_length):
            toggle = Factory.DayToggle()
            toggle.day_index = i
            toggle.label_text = str(i + 1)
            toggle.active = i in active_days
            toggle.bind(on_release=lambda *a: self._save_work_cycle())
            container.add_widget(toggle)

    def _selected_cycle_off_days(self):
        return ",".join(str(t.day_index) for t in self.root_widget.ids.cycle_day_toggles.children if t.active)

    def _reset_cycle_today_spinner(self, today_cycle_day=1):
        spinner = self.root_widget.ids.cycle_today_spinner
        spinner.values = [str(n) for n in range(1, self.cycle_length + 1)]
        spinner.text = str(today_cycle_day)

    def _init_work_cycle_ui(self):
        """Chamado 1x na abertura do app — popula os widgets dinâmicos (dias
        de folga, "hoje é o dia ?") a partir do que já está salvo."""
        prefs = settings.get_settings()
        self.cycle_enabled = prefs["cycle_enabled"]
        self.cycle_length = prefs["cycle_length"]
        active = {int(d) for d in prefs["cycle_off_days"].split(",") if d}
        self._rebuild_cycle_day_toggles(active)
        today_cycle_day = 1
        if prefs["cycle_anchor_date"]:
            anchor = date.fromisoformat(prefs["cycle_anchor_date"])
            today_cycle_day = (date.today() - anchor).days % self.cycle_length + 1
        self._reset_cycle_today_spinner(today_cycle_day)

    def toggle_work_cycle_enabled(self):
        self.cycle_enabled = not self.cycle_enabled
        self._save_work_cycle()

    def set_cycle_length(self, length_label):
        if not length_label:
            return
        self.cycle_length = int(length_label)
        self._rebuild_cycle_day_toggles()  # tamanho mudou -> índices antigos não valem mais
        self._reset_cycle_today_spinner()
        self._save_work_cycle()

    def apply_cycle_preset(self, preset):
        presets = {"12x36": (2, {1}), "24x48": (3, {1, 2})}
        if preset in presets:
            self.cycle_length, off_days = presets[preset]
            self._rebuild_cycle_day_toggles(off_days)
        else:  # "custom" — mantém o tamanho atual, só garante os atalhos ligarem o ciclo
            self._rebuild_cycle_day_toggles()
        self._reset_cycle_today_spinner()
        self.cycle_enabled = True
        self._save_work_cycle()

    def set_cycle_today(self, _today_label):
        self._save_work_cycle()

    def _save_work_cycle(self):
        today_label = self.root_widget.ids.cycle_today_spinner.text
        settings.set_work_cycle(
            enabled=self.cycle_enabled,
            length=self.cycle_length,
            off_days=self._selected_cycle_off_days(),
            today_cycle_day=int(today_label) if today_label else 1,
        )

    def _start_reminder_watcher(self):
        """Checa os lembretes numa THREAD, não no Clock do Kivy.

        O Clock só roda com o app em 1º plano: ao minimizar, ele congela, e o
        lembrete das 20:00 só saía quando a pessoa reabrisse o app — chegando
        "atrasado" horas depois. Uma thread comum não é congelada pelo Kivy;
        ela continua rodando enquanto o processo estiver vivo em 2º plano, que
        é o caso normal de quem só minimiza o app.

        Continua sem cobrir o app FECHADO/morto pelo Android: pra isso não tem
        jeito em Python puro, precisa de serviço do p4a + AlarmManager (ver
        README > Lembrete diário)."""
        def loop():
            # lê o intervalo a cada volta de propósito: o teste baixa pra
            # décimos de segundo em vez de esperar 20s de verdade
            while not self._parar_lembrete.wait(REMINDER_TICK_SECONDS):
                try:
                    self._check_reminder(0)
                    self._check_mission_reminders(0)
                except Exception as e:  # uma falha não pode matar o laço
                    print(f"[reminder] checagem falhou: {e!r}")

        self._parar_lembrete.clear()
        # primeira checagem já no boot (app aberto depois da hora marcada), sem
        # esperar os 20s do 1º ciclo; no Clock pra não competir com a montagem
        # da tela inicial
        Clock.schedule_once(self._check_reminder, 4)
        Clock.schedule_once(self._check_mission_reminders, 4)
        threading.Thread(target=loop, daemon=True).start()

    def on_stop(self):
        # sem isso a thread sobrevive ao app parar — nos testes, que sobem
        # vários apps no mesmo processo, ela dispararia lembrete do app antigo
        self._parar_lembrete.set()

    def _fired_today(self, key):
        """Esse lembrete já disparou hoje? `_*_fired` são só memo em memória —
        a verdade fica no banco (settings.get_reminders_fired), senão cada vez
        que o Android mata e reabre o app o lembrete do dia dispara de novo,
        em qualquer horário. Era isso que aparecia como "notificação atrasada"."""
        today_str = date.today().isoformat()
        memo = (self._reminder_last_fired == today_str if key == "daily"
                else self._mission_reminders_fired.get(key) == today_str)
        if memo:
            return True
        if settings.get_reminders_fired().get(key) == today_str:
            self._remember_fired(key, memo_only=True)
            return True
        return False

    def _remember_fired(self, key, memo_only=False):
        today_str = date.today().isoformat()
        if key == "daily":
            self._reminder_last_fired = today_str
        else:
            self._mission_reminders_fired[key] = today_str
        if not memo_only:
            settings.set_reminder_fired(key, today_str)

    def _claim_fired(self, key):
        """Tenta pegar a marca "disparou hoje" de forma atômica entre PROCESSOS
        (app x serviço). True = eu ganhei, devo notificar. Atualiza o memo em
        memória dos dois lados do resultado."""
        won = settings.claim_reminder_fired(key, date.today().isoformat())
        # ganhando ou não, a partir de agora esse assunto já disparou hoje —
        # reidrata o memo pra não bater no banco de novo neste processo
        self._remember_fired(key, memo_only=True)
        return won

    def _check_reminder(self, _dt):
        # a thread do watcher e o on_resume (thread da UI) podem cair aqui ao
        # mesmo tempo; sem o lock, as duas passam pelo _fired_today antes de
        # qualquer uma marcar, e o lembrete sai duplicado
        with self._reminder_lock:
            self._check_reminder_locked()

    def _check_reminder_locked(self):
        if not self.reminder_enabled:
            return
        # ">=" (não "=="): se um tick do Clock cair fora do minuto exato do
        # horário (app aberto só depois, drift do relógio, frame lento), o
        # lembrete do dia não some — dispara na 1ª checagem já passada a hora.
        # HH:MM zero-padded compara certo como string dentro do mesmo dia.
        agora = datetime.now()
        if agora.strftime("%H:%M") < self.reminder_time:
            return
        hoje = date.today().isoformat()
        if getattr(self, "_popup_diario_dia", "") == hoje:
            return  # este processo já mostrou o lembrete de hoje
        ja_disparou = self._fired_today("daily")
        # marca do dia já tomada pelo SERVIÇO (outro processo): com o app
        # aberto só saía a notificação de sistema, o popup nunca aparecia.
        # Mostra o popup também — mas só logo depois do horário, senão
        # reabrir o app horas depois traria o lembrete de volta
        h, m = map(int, self.reminder_time.split(":"))
        recente = agora - agora.replace(hour=h, minute=m, second=0, microsecond=0) <= REMINDER_POPUP_JANELA
        if ja_disparou and not recente:
            return
        pending = missions.pending_today()
        if not pending:
            return  # tudo concluído — não marca como "já disparou": se desmarcar algo, ainda avisa hoje
        title, body = self.t("reminder_notification_title"), self._reminder_body(pending)
        if not ja_disparou and self._claim_fired("daily"):
            # id 2, NÃO 1: id 1 é o do foreground service permanente
            # (service_reminder.NOTIF_DIARIO explica) — postar com 1 sobrescreve
            # a notificação do serviço e ela trava sem poder ser dispensada.
            self._fire_reminder(title, body, notification_id=2)
        elif getattr(self, "_em_segundo_plano", False):
            return  # serviço já notificou e não há tela à vista; tenta de novo ao voltar
        else:
            self._abrir_popup_lembrete(title, body)  # sistema já saiu pelo serviço
        self._popup_diario_dia = hoje

    def _reminder_body(self, pending):
        return reminder_text.daily_body(pending, self.streak, self.language)

    def _fire_reminder(self, title, body, notification_id=2):
        """Notificação de sistema (bônus, pode falhar no Android/desktop) MAIS
        um popup dentro do app — este último sempre é visto, porque o lembrete
        só dispara com o app aberto e em 1º plano (o Clock do Kivy pausa em 2º
        plano; não é um serviço de fundo, ver README)."""
        try:
            # texto inteiro, com emoji: quem desenha a notificação de sistema é
            # o Android (ou o balão do Windows), que tem fonte de emoji
            notify.send(title, body, notification_id=notification_id)
        except Exception as e:
            print(f"[reminder] notificação de sistema falhou: {e!r}")
        self._abrir_popup_lembrete(title, body)

    def _abrir_popup_lembrete(self, title, body):
        # o popup é desenhado pelo Kivy: (a) usa UMA fonte só e não faz fallback
        # pro sistema, então emoji viraria quadradinho (_sem_emoji), e (b) mexer
        # em widget fora da thread da UI corrompe o estado do Kivy — daí o
        # Clock, que roda o callback na thread certa (o watcher é uma thread)
        def abrir(_dt):
            try:
                Factory.ReminderPopup().open_with(title, _sem_emoji(body))
            except Exception as e:
                print(f"[reminder] popup falhou: {e!r}")

        Clock.schedule_once(abrir, 0)

    # --- alarme de missão: tela cheia + toque, sem notificação ---
    def _montar_alarme(self, mission):
        """A AlarmeView pronta pra abrir. Fechar É encerrar: é o on_dismiss que
        para o toque e devolve a tela bloqueada ao normal."""
        view = Factory.AlarmeView()
        view.mission_name = mission["name"]
        view.horario = mission["reminder_time"] or datetime.now().strftime("%H:%M")
        view.bind(on_dismiss=self._fim_alarme)
        return view

    def abrir_alarme(self, mission_id):
        """Abre a tela do alarme da missão e começa a tocar. Thread da UI.

        No Android é a tela nativa (AlarmeActivity) — a mesma que o serviço
        abre com o app fechado, então o alarme é igual nos dois casos. A
        AlarmeView (Kivy) fica pro desktop."""
        if self._alarme_aberto is not None:
            return  # já tem um tocando: não empilha dois toques
        mission = next((m for m in missions.list_missions() if m["id"] == mission_id), None)
        if mission is None:
            return  # missão apagada entre o agendamento e o disparo
        if android_alarm.abrir_tela_alarme(mission["name"], mission["reminder_time"],
                                           self.language, em_primeiro_plano=True):
            return
        self._alarme_aberto = self._montar_alarme(mission)
        self._alarme_aberto.open()
        # toque em THREAD: tocar_alarme bloqueia enquanto o som roda
        threading.Thread(target=notify.tocar_alarme,
                         args=(notify.ALARME_APP_SEGUNDOS,), daemon=True).start()

    def _fim_alarme(self, *_args):
        notify.parar_alarme()
        self._alarme_aberto = None

    def pedir_permissao_tela_alarme(self):
        """Sem 'sobrepor a outros apps' o Android não deixa o serviço abrir a
        tela do alarme com o app fechado — só sobraria a notificação. Pergunta
        uma vez, quando a pessoa marca um alarme."""
        Factory.ConfirmPopup().ask(self.t("alarm_overlay_title"), self.t("alarm_overlay_msg"),
                                   self.t("alarm_overlay_btn"),
                                   android_alarm.abrir_config_sobreposicao)

    def _check_mission_reminders(self, _dt):
        """Lembrete por missão (Premium — horário próprio, não só o horário
        único do diário). Com o app aberto: thread a cada REMINDER_TICK_SECONDS.
        Fechado: cada missão tem um `setAlarmClock` (exato) próprio que acorda o
        serviço no horário (ver android_alarm.agendar_missao / service_reminder).
        A marca "já disparou" é compartilhada com o serviço via
        settings.claim_reminder_fired, pra não notificar em dobro."""
        with self._reminder_lock:  # mesmo motivo do _check_reminder
            self._check_mission_reminders_locked()

    def _check_mission_reminders_locked(self):
        if not self.is_premium:
            return
        if platform == "android" and self._em_segundo_plano:
            # minimizado, a tela do alarme abriria invisível e tocaria sem ter
            # como encerrar. Quem cobre é o serviço: o alarme do sistema acorda
            # ele e ele traz o app pra frente já na tela do alarme
            return
        now_hm = datetime.now().strftime("%H:%M")
        for m in missions.list_missions():
            # ">" e não "!=": com igualdade exata, um lembrete cujo minuto
            # passou com o app fechado não atrasava — sumia de vez. Agora vale
            # a mesma regra do lembrete diário (dispara na 1ª checagem já
            # passada a hora, uma vez só por dia).
            if not m["reminder_time"] or m["reminder_time"] > now_hm:
                continue
            if not missions.is_scheduled_today(m) or missions.is_done_this_period(m):
                continue  # não é hoje, ou já concluiu — nada pra lembrar (não marca)
            # _fired_today por último de propósito: é o único que vai ao banco,
            # e assim missão concluída/fora do dia não gera leitura a cada tick
            key = f"m{m['id']}"
            if self._fired_today(key):
                continue
            if not self._claim_fired(key):
                continue  # o serviço já abriu o alarme dessa missão hoje
            # tela cheia + toque, sem notificação. Clock: esta checagem roda
            # na thread do lembrete, e widget só se mexe na thread da UI
            Clock.schedule_once(lambda _dt, mid=m["id"]: self.abrir_alarme(mid), 0)


if __name__ == "__main__":
    DailyQuestApp().run()
