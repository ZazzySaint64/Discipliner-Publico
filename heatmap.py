"""Calendário-mapa de calor (estilo GitHub/Streaks) desenhado no canvas do Kivy —
sem Matplotlib. Um quadrado por dia do mês, cor mais forte = mais pontos naquele dia.
"""
from kivy.graphics import Color, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import DictProperty, ListProperty, NumericProperty
from kivy.uix.label import Label
from kivy.uix.widget import Widget


class HeatmapCalendar(Widget):
    points_by_day = DictProperty({})    # {1: 5, 2: 0, ...}
    days_in_month = NumericProperty(30)
    first_weekday = NumericProperty(0)  # 0=segunda (mesma convenção do calendar.monthrange)
    today_day = NumericProperty(0)
    base_color = ListProperty([0.90, 0.91, 0.97, 1])
    accent_color = ListProperty([0.95, 0.55, 0.30, 1])
    text_dark = ListProperty([0.20, 0.20, 0.32, 1])
    weekday_letters = ListProperty(["S", "T", "Q", "Q", "S", "S", "D"])  # traduzido pelo app (ver i18n.WEEKDAYS)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._child_labels = []
        self.bind(
            pos=self._redraw, size=self._redraw, points_by_day=self._redraw,
            days_in_month=self._redraw, first_weekday=self._redraw, today_day=self._redraw,
            base_color=self._redraw, accent_color=self._redraw, text_dark=self._redraw,
            weekday_letters=self._redraw,
        )

    def _redraw(self, *_args):
        self.canvas.clear()
        for lbl in self._child_labels:
            self.remove_widget(lbl)
        self._child_labels = []

        if self.width <= 0 or self.height <= 0:
            return

        cols, rows = 7, 6
        gap = dp(5)
        header_h = dp(22)
        cell = min(
            (self.width - gap * (cols - 1)) / cols,
            (self.height - header_h - gap * (rows + 1)) / rows,
        )
        grid_w = cell * cols + gap * (cols - 1)
        x0 = self.x + (self.width - grid_w) / 2
        header_y = self.top - header_h

        for i, letter in enumerate(self.weekday_letters):
            lbl = Label(
                text=letter, color=self.text_dark, bold=True, font_size="11sp",
                size_hint=(None, None), size=(cell, header_h),
                pos=(x0 + i * (cell + gap), header_y),
            )
            self.add_widget(lbl)
            self._child_labels.append(lbl)

        max_points = max(self.points_by_day.values(), default=0) or 1
        row_top = header_y - gap

        day = 1
        col = self.first_weekday
        row = 0
        while day <= self.days_in_month:
            points = self.points_by_day.get(day, 0)
            intensity = min(points / max_points, 1.0) if points else 0.0
            r, g, b = self._mix(intensity)
            cx = x0 + col * (cell + gap)
            cy = row_top - (row + 1) * cell - row * gap

            with self.canvas:
                Color(rgba=(r, g, b, 1))
                RoundedRectangle(pos=(cx, cy), size=(cell, cell), radius=[cell * 0.28])
                if day == self.today_day:
                    Color(rgba=self.accent_color)
                    Line(
                        rounded_rectangle=(cx, cy, cell, cell, cell * 0.28),
                        width=dp(1.6),
                    )

            day_label = Label(
                text=str(day),
                color=(1, 1, 1, 1) if intensity > 0.45 else self.text_dark,
                bold=(day == self.today_day),
                font_size="12sp",
                size_hint=(None, None),
                size=(cell, cell),
                pos=(cx, cy),
            )
            self.add_widget(day_label)
            self._child_labels.append(day_label)

            col += 1
            if col > 6:
                col = 0
                row += 1
            day += 1

    def _mix(self, intensity):
        """Interpola base_color -> accent_color; intensidade mínima visível de 25% pra dia com pontos."""
        if intensity <= 0:
            return self.base_color[:3]
        t = 0.25 + 0.75 * intensity
        br, bg_, bb = self.base_color[:3]
        ar, ag, ab = self.accent_color[:3]
        return (br + (ar - br) * t, bg_ + (ag - bg_) * t, bb + (ab - bb) * t)
