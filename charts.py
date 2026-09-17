"""Gráfico de colunas e de linhas — alternativas ao heatmap, mesma fonte de dados
(pontos por dia do mês), desenhados no canvas do Kivy. Sem Matplotlib."""
from kivy.graphics import Color, Ellipse, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import DictProperty, ListProperty, NumericProperty
from kivy.uix.label import Label
from kivy.uix.widget import Widget


class _DailyChartBase(Widget):
    """Comum aos dois: eixo de dias do mês, mesmas props de dados e cor."""
    points_by_day = DictProperty({})
    days_in_month = NumericProperty(30)
    today_day = NumericProperty(0)
    accent_color = ListProperty([0.95, 0.55, 0.30, 1])
    grid_color = ListProperty([0.90, 0.91, 0.97, 1])
    text_dark = ListProperty([0.20, 0.20, 0.32, 1])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._child_labels = []
        self.bind(
            pos=self._redraw, size=self._redraw, points_by_day=self._redraw,
            days_in_month=self._redraw, today_day=self._redraw,
            accent_color=self._redraw, grid_color=self._redraw, text_dark=self._redraw,
        )

    def _plot_area(self):
        """Área útil de desenho, descontando uma margem pra rótulos do eixo x."""
        margin_bottom = dp(20)
        margin_side = dp(6)
        x0 = self.x + margin_side
        y0 = self.y + margin_bottom
        w = self.width - margin_side * 2
        h = self.height - margin_bottom - dp(6)
        return x0, y0, w, h

    def _clear(self):
        self.canvas.clear()
        for lbl in self._child_labels:
            self.remove_widget(lbl)
        self._child_labels = []

    def _draw_day_labels(self, x0, y0, w):
        n = self.days_in_month
        step = 5 if n > 15 else 1
        for day in range(1, n + 1, step):
            cx = x0 + (day - 0.5) * (w / n)
            lbl = Label(
                text=str(day), color=(*self.text_dark[:3], 0.65),
                font_size="10sp", size_hint=(None, None), size=(dp(20), dp(16)),
                pos=(cx - dp(10), self.y),
            )
            self.add_widget(lbl)
            self._child_labels.append(lbl)

    def _redraw(self, *_args):
        raise NotImplementedError


class BarChart(_DailyChartBase):
    def _redraw(self, *_args):
        self._clear()
        if self.width <= 0 or self.height <= 0:
            return
        x0, y0, w, h = self._plot_area()
        n = self.days_in_month
        max_points = max(self.points_by_day.values(), default=0) or 1
        slot = w / n
        bar_w = max(slot * 0.6, dp(2))

        with self.canvas:
            Color(rgba=self.grid_color)
            Line(points=[x0, y0, x0 + w, y0], width=dp(1))

            for day in range(1, n + 1):
                points = self.points_by_day.get(day, 0)
                bar_h = (points / max_points) * h if points else 0
                cx = x0 + (day - 0.5) * slot
                is_today = day == self.today_day
                Color(rgba=self.accent_color if not is_today else (*self.accent_color[:3], 1))
                if bar_h > 0:
                    RoundedRectangle(
                        pos=(cx - bar_w / 2, y0), size=(bar_w, bar_h),
                        radius=[min(bar_w * 0.35, dp(4))],
                    )
                if is_today:
                    Color(rgba=self.accent_color)
                    Line(points=[cx - bar_w / 2 - dp(2), y0 - dp(3), cx + bar_w / 2 + dp(2), y0 - dp(3)], width=dp(2))

        self._draw_day_labels(x0, y0, w)


class LineChart(_DailyChartBase):
    def _redraw(self, *_args):
        self._clear()
        if self.width <= 0 or self.height <= 0:
            return
        x0, y0, w, h = self._plot_area()
        n = self.days_in_month
        max_points = max(self.points_by_day.values(), default=0) or 1
        slot = w / n

        coords = []
        for day in range(1, n + 1):
            points = self.points_by_day.get(day, 0)
            cx = x0 + (day - 0.5) * slot
            cy = y0 + (points / max_points) * h
            coords.append((cx, cy))

        with self.canvas:
            Color(rgba=self.grid_color)
            Line(points=[x0, y0, x0 + w, y0], width=dp(1))

            Color(rgba=self.accent_color)
            flat = [c for point in coords for c in point]
            if len(coords) > 1:
                Line(points=flat, width=dp(2), joint="round")

            for day, (cx, cy) in enumerate(coords, start=1):
                if self.points_by_day.get(day, 0) <= 0:
                    continue
                r = dp(4) if day != self.today_day else dp(6)
                Ellipse(pos=(cx - r, cy - r), size=(r * 2, r * 2))

        self._draw_day_labels(x0, y0, w)
