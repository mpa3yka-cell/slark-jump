"""Фон «Прыжков Сларка» — пиксель-арт в стиле тёмного фэнтези: зоны по высоте и параллакс.

Чем выше поднимается Сларк, тем сильнее меняется мир:
    0 м      — Долина замка: сумерки, средневековый замок на холме, река, деревушка, туман, лес
    250 м    — Кровавый закат: огромное красное солнце, облака в огне, вороны
    600 м    — Над облаками: море облаков внизу, лунная ночь
    1000 м   — Звёздная бездна: звёзды, туманности, планеты
Небо рисуется полосами с «шахматными» переходами, всё остальное — без сглаживания, пиксель к пикселю.
Дальние слои едут вниз медленнее ближних — так получается глубина (параллакс).
"""
import math
import random

import pygame

from common import WIDTH, HEIGHT, small_font, big_font

PIXELS_PER_METER = 20
TRANSITION = 80   # за сколько метров одна зона перетекает в другую
SKY_BANDS = 16    # на сколько полос делится небо

BIOMES = [
    {"name": "Долина замка", "id": "valley", "from": 0,
     "top": (16, 18, 46), "bottom": (104, 74, 122), "stars": 0.35, "clouds": 0.22,
     "cloud": ((42, 36, 68), (62, 54, 94), (88, 78, 122))},
    {"name": "Кровавый закат", "id": "sunset", "from": 250,
     "top": (54, 22, 60), "bottom": (242, 118, 66), "stars": 0.0, "clouds": 0.55,
     "cloud": ((104, 36, 58), (190, 84, 66), (250, 158, 88))},
    {"name": "Над облаками", "id": "clouds", "from": 600,
     "top": (22, 30, 76), "bottom": (130, 150, 204), "stars": 0.3, "clouds": 1.0,
     "cloud": ((112, 122, 176), (164, 176, 220), (224, 230, 250))},
    {"name": "Звёздная бездна", "id": "space", "from": 1000,
     "top": (4, 2, 14), "bottom": (30, 14, 58), "stars": 1.0, "clouds": 0.0,
     "cloud": ((44, 30, 78), (66, 46, 108), (96, 70, 140))},
]


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(a, b, t):
    return tuple(int(lerp(a[i], b[i], t)) for i in range(3))


def biome_index(height_m):
    index = 0
    for i, b in enumerate(BIOMES):
        if height_m >= b["from"]:
            index = i
    return index


def biome_at(height_m):
    """Возвращает (зона, следующая зона, насколько перешли в следующую от 0 до 1)."""
    i = biome_index(height_m)
    current = BIOMES[i]
    if i + 1 < len(BIOMES):
        nxt = BIOMES[i + 1]
        t = (height_m - (nxt["from"] - TRANSITION)) / TRANSITION
        return current, nxt, max(0.0, min(1.0, t))
    return current, current, 0.0


def blend(height_m, key):
    a, b, t = biome_at(height_m)
    if isinstance(a[key], tuple) and isinstance(a[key][0], tuple):
        return tuple(lerp_color(ca, cb, t) for ca, cb in zip(a[key], b[key]))
    if isinstance(a[key], tuple):
        return lerp_color(a[key], b[key], t)
    return lerp(a[key], b[key], t)


def weight(height_m, biome_id):
    """Насколько «сильна» зона на этой высоте (от 0 до 1) — для луны, солнца, ворон."""
    a, b, t = biome_at(height_m)
    return (1 - t) * (a["id"] == biome_id) + t * (b["id"] == biome_id)


# --- Пиксельные картинки фона ---

def checker_strip(width, height, color):
    """«Шахматка»: каждый второй пиксель закрашен (так в пиксель-арте делают полупрозрачность)."""
    strip = pygame.Surface((width, height), pygame.SRCALPHA)
    row = pygame.Surface((width + 1, 1), pygame.SRCALPHA)
    for x in range(0, width + 1, 2):
        row.set_at((x, 0), color + (255,))
    for y in range(height):
        strip.blit(row, (-(y % 2), y))
    return strip


def dithered(surface):
    """Оставляет «шахматкой» только половину пикселей картинки (ореолы, туман, тени)."""
    result = surface.copy()
    result.blit(checker_strip(*surface.get_size(), (255, 255, 255)), (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    return result


def make_mountains(seed, width, height, colors, snow):
    """Зубчатые горы: каждая колонка пикселей — своей высоты; склоны к свету — светлее."""
    dark, mid, light = colors
    rng = random.Random(seed)
    surf = pygame.Surface((width, height), pygame.SRCALPHA)
    heights = []
    y = rng.randint(60, 120)
    target = rng.randint(30, 130)
    for x in range(width):
        if abs(y - target) < 2:
            target = rng.randint(30, height - 60)
        y += (1 if target > y else -1) * rng.choice((0, 1, 1, 2))
        heights.append(y)
    heights[-1] = heights[0]
    for x, top in enumerate(heights):
        rising = x > 0 and heights[x - 1] > top          # склон, повёрнутый к свету (слева)
        pygame.draw.line(surf, dark, (x, top), (x, height))
        pygame.draw.line(surf, light if rising else mid, (x, top), (x, top + 4 + (x * 7 % 4)))
        if snow and top < height * 0.4:
            pygame.draw.line(surf, (196, 190, 226) if rising else (150, 144, 186), (x, top), (x, top + 2))
    return surf


def make_castle_hill():
    """Холм со средневековым замком: башни с коническими крышами и флагами, зубчатые стены,
    светящиеся окна, ворота и дорога вниз."""
    w, h = WIDTH, 300
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    body, lit, roof, rim = (32, 28, 56), (56, 50, 88), (60, 30, 52), (84, 70, 116)
    window, flag = (255, 190, 76), (170, 38, 40)
    hill = [(170, h), (290, 232), (380, 196), (452, 178), (640, 176), (712, 204), (w, 222), (w, h)]
    pygame.draw.polygon(surf, (26, 26, 48), hill)
    pygame.draw.lines(surf, (48, 46, 78), False, hill[1:-1], 2)
    rng = random.Random(4)

    def battlements(x, y, width):
        for bx in range(x, x + width - 3, 7):
            pygame.draw.rect(surf, body, (bx, y - 5, 4, 5))

    def tower(x, top, width, bottom=178, spire=26):
        pygame.draw.rect(surf, body, (x, top, width, bottom - top))
        pygame.draw.rect(surf, lit, (x, top, 3, bottom - top))           # свет слева
        apex = (x + width // 2, top - spire)
        pygame.draw.polygon(surf, roof, [(x - 3, top), (x + width + 3, top), apex])
        pygame.draw.line(surf, rim, (x - 3, top), apex)
        pygame.draw.line(surf, body, apex, (apex[0], apex[1] - 8))       # флагшток
        pygame.draw.polygon(surf, flag, [(apex[0] + 1, apex[1] - 8), (apex[0] + 8, apex[1] - 6),
                                         (apex[0] + 1, apex[1] - 4)])
        for wy in range(top + 8, bottom - 12, 16):                        # окна
            if rng.random() < 0.7:
                pygame.draw.rect(surf, window if rng.random() < 0.75 else (60, 40, 50), (x + width // 2 - 1, wy, 3, 5))

    pygame.draw.rect(surf, body, (452, 132, 184, 46))       # стена
    pygame.draw.rect(surf, lit, (452, 132, 184, 3))
    battlements(452, 132, 184)
    pygame.draw.rect(surf, body, (496, 80, 50, 98))          # главная башня-донжон
    pygame.draw.rect(surf, lit, (496, 80, 3, 98))
    battlements(496, 80, 50)
    tower(510, 44, 22, 80, 30)                               # шпиль над донжоном
    tower(440, 96, 24)
    tower(566, 106, 22)
    tower(616, 88, 26)
    for wx, wy in ((506, 96), (530, 96), (506, 118), (530, 120), (470, 146), (600, 148), (620, 150)):
        pygame.draw.rect(surf, window, (wx, wy, 3, 5))
    pygame.draw.rect(surf, (12, 10, 20), (515, 156, 14, 22))   # ворота
    pygame.draw.circle(surf, (12, 10, 20), (522, 157), 7)
    for i in range(12):                                         # дорога вниз по холму
        pygame.draw.rect(surf, (58, 52, 80), (522 - i * 9 + (i % 3), 180 + i * 5, 8, 2))
    return surf


def make_valley():
    """Долина: холмы с деревьями, река, отражающая небо, деревушка с огоньками и туман."""
    w, h = WIDTH, 240
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    rng = random.Random(12)
    for tone, base_y, amp, seed in (((34, 48, 60), 70, 26, 1), ((28, 40, 50), 110, 20, 2)):
        r = random.Random(seed)
        points = [(0, h)]
        phase = r.uniform(0, 6)
        for x in range(0, w + 1, 8):
            points.append((x, base_y + math.sin(x / 90 + phase) * amp + math.sin(x / 37) * 6))
        points.append((w, h))
        pygame.draw.polygon(surf, tone, points)
        pygame.draw.lines(surf, tuple(c + 16 for c in tone), False, points[1:-1], 2)
    # река змейкой: отражает небо, с бликами
    river = []
    for i in range(0, 30):
        y = 100 + i * 5
        x = 120 + math.sin(i / 4) * 60 + i * 12
        river.append((x, y))
    for (x1, y1), (x2, y2) in zip(river, river[1:]):
        width = 6 + (y1 - 100) // 12
        pygame.draw.line(surf, (92, 80, 132), (x1, y1), (x2, y2), width)
    for x, y in river[::3]:
        pygame.draw.rect(surf, (150, 132, 180), (x - 2, y, 4, 1))
    # деревья: круглые кроны со светлым краем сверху-слева
    for _ in range(46):
        x, y = rng.randint(0, w), rng.randint(62, h - 20)
        r = rng.randint(4, 8)
        pygame.draw.rect(surf, (20, 22, 30), (x - 1, y, 2, r))
        pygame.draw.circle(surf, (24, 38, 42), (x, y), r)
        pygame.draw.circle(surf, (38, 58, 58), (x - r // 3, y - r // 3), max(1, r // 2))
    # деревушка у реки: домики с огоньками
    for x, y in ((250, 118), (268, 124), (290, 116), (330, 128), (360, 122)):
        pygame.draw.rect(surf, (30, 26, 38), (x, y, 12, 8))
        pygame.draw.polygon(surf, (70, 34, 44), [(x - 2, y), (x + 14, y), (x + 6, y - 6)])
        pygame.draw.rect(surf, (255, 190, 76), (x + 4, y + 3, 2, 2))
    # полоса тумана «шахматкой»
    mist = pygame.Surface((w, 14), pygame.SRCALPHA)
    mist.fill((132, 116, 168, 255))
    surf.blit(dithered(mist), (0, 92))
    return surf


def draw_pine(surf, x, base, h, dark, light):
    """Пиксельная ёлка: ярусы-треугольники, левый край подсвечен."""
    pygame.draw.rect(surf, dark, (x - 2, base - h * 0.22, 4, h * 0.22))
    for tier in range(4):
        ty = base - h * 0.18 - tier * h * 0.19
        tw = h * 0.33 * (1 - tier * 0.2)
        apex = (x, ty - h * 0.33)
        pygame.draw.polygon(surf, dark, [(x - tw, ty), (x + tw, ty), apex])
        pygame.draw.line(surf, light, (x - tw + 1, ty - 1), apex)


def make_forest(seed, count, min_h, max_h, dark, light):
    surf = pygame.Surface((WIDTH, 240), pygame.SRCALPHA)
    rng = random.Random(seed)
    for _ in range(count):
        draw_pine(surf, rng.randint(-20, WIDTH + 20), 240, rng.randint(min_h, max_h), dark, light)
    pygame.draw.rect(surf, dark, (0, 226, WIDTH, 14))
    return surf


def make_moon(tint=(236, 228, 212)):
    surf = pygame.Surface((104, 104), pygame.SRCALPHA)
    halo = pygame.Surface((104, 104), pygame.SRCALPHA)
    pygame.draw.circle(halo, (84, 80, 128), (52, 52), 50)
    surf.blit(dithered(halo), (0, 0))
    pygame.draw.circle(surf, (110, 104, 150), (52, 52), 40)
    pygame.draw.circle(surf, tint, (52, 52), 34)
    pygame.draw.circle(surf, tuple(min(255, c + 16) for c in tint), (47, 47), 27)
    for cx, cy, r in ((62, 44, 6), (41, 62, 5), (58, 64, 3), (40, 40, 3)):
        pygame.draw.circle(surf, tuple(c - 30 for c in tint), (cx, cy), r)
        pygame.draw.circle(surf, tuple(c - 50 for c in tint), (cx + 1, cy + 1), r - 1)
    return surf


def make_sun():
    """Кровавое солнце заката: диск из полос, «пиксельный» ореол, поперёк — тёмные перистые облака."""
    size = 260
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    halo = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(halo, (250, 120, 70), (size // 2, size // 2), size // 2)
    surf.blit(dithered(halo), (0, 0))
    r = 92
    colors = [(255, 226, 130), (255, 196, 96), (255, 160, 72), (244, 118, 60), (220, 76, 56), (176, 40, 52)]
    disc = pygame.Surface((size, size), pygame.SRCALPHA)
    for i, color in enumerate(colors):
        band = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(band, color + (255,), (size // 2, size // 2), r)
        top = size // 2 - r + i * 2 * r // len(colors)
        disc.blit(band, (0, top), (0, top, size, 2 * r // len(colors) + 1))
    surf.blit(disc, (0, 0))
    for y, x1, x2 in ((size // 2 + 20, 20, 200), (size // 2 + 44, 60, 250), (size // 2 - 10, 120, 240)):
        pygame.draw.rect(surf, (96, 30, 52), (x1, y, x2 - x1, 5), border_radius=2)
        pygame.draw.rect(surf, (150, 56, 60), (x1 + 6, y, x2 - x1 - 12, 2))
    return surf


def make_cloud(rng, width):
    """Пиксельное облако: 3 оттенка (тень, основа, свет). Цвета — «заглушки» 1/2/3,
    при создании облака они заменяются цветами зоны."""
    height = width // 2
    shape = pygame.Surface((width, height), pygame.SRCALPHA)
    blobs = []
    for _ in range(8):
        r = rng.randint(width // 8, width // 4)
        blobs.append((rng.randint(r, width - r), rng.randint(height // 2, height - r // 2 - 2), r))
    for x, y, r in blobs:
        pygame.draw.circle(shape, (1, 1, 1), (x, y), r)
    for x, y, r in blobs:
        pygame.draw.circle(shape, (2, 2, 2), (x - 1, y - 3), r - 2)
    for x, y, r in blobs:
        pygame.draw.circle(shape, (3, 3, 3), (x - 3, y - 6), max(1, r - 7))
    return shape


def color_cloud(shape, tones, outline):
    """Заменяет «заглушки» 1/2/3 на цвета зоны и обводит контуром."""
    surf = shape.copy()
    pixels = pygame.PixelArray(surf)
    for code, color in zip((1, 2, 3), tones):
        pixels.replace((code, code, code), color)
    del pixels
    result = pygame.Surface((surf.get_width() + 2, surf.get_height() + 2), pygame.SRCALPHA)
    ring = pygame.mask.from_surface(surf).to_surface(setcolor=outline + (255,), unsetcolor=(0, 0, 0, 0))
    for dx, dy in ((0, 1), (2, 1), (1, 0), (1, 2)):
        result.blit(ring, (dx, dy))
    result.blit(surf, (1, 1))
    return result


def make_cloud_sea(rng, tones):
    """Море облаков — широкая полоса облаков, над которой поднимается Сларк."""
    surf = pygame.Surface((WIDTH, 200), pygame.SRCALPHA)
    outline = tuple(max(0, c - 30) for c in tones[0])
    x = -60
    while x < WIDTH:
        cloud = color_cloud(make_cloud(rng, rng.randint(180, 280)), tones, outline)
        surf.blit(cloud, (x, rng.randint(10, 60)))
        x += rng.randint(90, 150)
    pygame.draw.rect(surf, tones[1], (0, 120, WIDTH, 80))  # низ сплошной — он всегда у нижнего края экрана
    return surf


def make_nebula(rng, radius, color):
    """Туманность: мягкие облака газа, нарисованные в 4 раза мельче и увеличенные без сглаживания."""
    small = radius // 2
    surf = pygame.Surface((small, small), pygame.SRCALPHA)
    second = tuple(min(255, int(c * 0.6 + d * 0.4)) for c, d in zip(color, (255, 120, 200)))
    for _ in range(14):
        r = rng.randint(small // 6, small // 3)
        x = rng.randint(r, small - r)
        y = rng.randint(r, small - r)
        tint = color if rng.random() < 0.6 else second
        for step in range(r, 0, -max(1, r // 4)):
            pygame.draw.circle(surf, tint + (int(56 * (1 - step / r) + 20),), (x, y), step)
    for _ in range(6):
        surf.set_at((rng.randint(2, small - 3), rng.randint(2, small - 3)), (255, 245, 255, 255))
    return pygame.transform.scale_by(surf, 4)


def make_planet(rng, radius):
    base = rng.choice([(206, 122, 86), (104, 158, 222), (176, 142, 222), (132, 196, 140)])
    surf = pygame.Surface((radius * 3, radius * 2 + 8), pygame.SRCALPHA)
    cx, cy = radius * 3 // 2, radius + 4
    pygame.draw.circle(surf, base, (cx, cy), radius)
    for i in range(-2, 3):
        band = [min(255, int(c * (0.8 if i % 2 else 1.1))) for c in base]
        pygame.draw.rect(surf, band, (cx - radius, cy + i * radius // 3 - 2, radius * 2, 4))
    shadow = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    pygame.draw.circle(shadow, (0, 0, 0, 255), (cx, cy), radius)
    pygame.draw.circle(shadow, (0, 0, 0, 0), (cx - radius // 3, cy - radius // 3), radius)
    surf.blit(dithered(shadow), (0, 0))
    pygame.draw.ellipse(surf, (234, 224, 255), (cx - radius * 1.45, cy - 5, radius * 2.9, 12), 2)
    return surf


class Background:
    def __init__(self, lookahead=0):
        rng = random.Random(5)
        self.time = 0
        # lookahead — насколько выше обычного экрана нужно заранее готовить облака (для дуэли)
        self.lookahead = lookahead
        self.stars = [(rng.randint(0, WIDTH - 1), rng.randint(0, HEIGHT * 2 - 1), rng.random() < 0.15,
                       rng.uniform(0, 6)) for _ in range(260)]
        # слои долины: (картинка, насколько медленнее камеры едет вниз, где верх картинки в начале)
        self.ground_layers = [
            (make_mountains(3, WIDTH, 260, ((40, 38, 76), (54, 50, 94), (76, 70, 120)), True), 0.05, HEIGHT - 340),
            (make_castle_hill(), 0.09, HEIGHT - 320),
            (make_valley(), 0.17, HEIGHT - 205),
            (make_forest(8, 30, 110, 180, (12, 14, 24), (30, 32, 52)), 0.4, HEIGHT - 150),
        ]
        self.moon = make_moon()
        self.big_moon = pygame.transform.scale_by(make_moon((226, 232, 246)), 2)
        self.sun = make_sun()
        self.cloud_sea = make_cloud_sea(random.Random(9), BIOMES[2]["cloud"])
        self.cloud_shapes = [make_cloud(rng, w) for w in (120, 160, 200, 240, 280)]
        self.cloud_layers = [{"factor": 0.25, "scale": 0.7, "clouds": [], "next": 0.0},
                             {"factor": 0.55, "scale": 1.0, "clouds": [], "next": 0.0}]
        self.fireflies = [[rng.uniform(0, WIDTH), rng.uniform(HEIGHT * 0.3, HEIGHT), rng.uniform(0, 6)]
                          for _ in range(26)]
        self.firefly_glow = pygame.Surface((9, 9))
        pygame.draw.circle(self.firefly_glow, (60, 90, 20), (4, 4), 4)
        pygame.draw.rect(self.firefly_glow, (170, 255, 90), (3, 3, 3, 3))
        self.ravens = [[rng.uniform(-200, WIDTH), rng.uniform(60, 360), rng.uniform(0.8, 1.8), rng.uniform(0, 6)]
                       for _ in range(9)]
        self.nebulae = []
        self.next_nebula = 0.0
        self.shooting = None
        self.sky_key = None
        self.sky = None
        self.banner_index = -1  # чтобы в начале показать название первой зоны
        self.banner_timer = 0
        self.banner_text = None
        self.thunder = False    # грозы в этой версии нет, флаг оставлен для совместимости

    # --- обновление ---

    def update(self, climbed):
        self.time += 1 / 60
        height_m = climbed / PIXELS_PER_METER
        self.update_clouds(climbed)
        self.update_space(climbed, height_m)
        for fly in self.fireflies:
            fly[2] += 0.02
            fly[0] += math.sin(fly[2] * 1.3) * 0.5
            fly[1] += math.cos(fly[2]) * 0.3
        for raven in self.ravens:
            raven[0] += raven[2]
            raven[1] += math.sin(self.time * 2 + raven[3]) * 0.3
            if raven[0] > WIDTH + 30:
                raven[0], raven[1] = random.uniform(-300, -30), random.uniform(60, 360)

        index = biome_index(height_m)
        if index != self.banner_index:
            self.banner_index = index
            self.banner_timer = 180
            self.banner_text = big_font.render(BIOMES[index]["name"], False, (255, 240, 220))
        if self.banner_timer > 0:
            self.banner_timer -= 1

    def cloud_screen_y(self, cloud, layer, climbed):
        return HEIGHT - (cloud["alt"] - climbed * layer["factor"])

    def update_clouds(self, climbed):
        for layer in self.cloud_layers:
            f = layer["factor"]
            # создаём облака, которые скоро появятся сверху экрана
            while layer["next"] < climbed * f + HEIGHT + 300 + self.lookahead:
                layer["next"] += random.uniform(70, 150)
                real_height = (layer["next"] - HEIGHT / 2) / f / PIXELS_PER_METER
                if random.random() < blend(real_height, "clouds"):
                    shape = random.choice(self.cloud_shapes)
                    if layer["scale"] != 1:
                        shape = pygame.transform.scale_by(shape, layer["scale"])  # без сглаживания
                    tones = blend(real_height, "cloud")
                    outline = tuple(max(0, c - 30) for c in tones[0])
                    layer["clouds"].append({"alt": layer["next"], "x": random.uniform(-100, WIDTH),
                                            "image": color_cloud(shape, tones, outline),
                                            "speed": random.uniform(0.15, 0.4) * f})
            for cloud in layer["clouds"]:
                cloud["x"] += cloud["speed"]
                if cloud["x"] > WIDTH + 50:
                    cloud["x"] = -cloud["image"].get_width() - 50
            layer["clouds"] = [c for c in layer["clouds"] if self.cloud_screen_y(c, layer, climbed) < HEIGHT + 200]

    def update_space(self, climbed, height_m):
        f = 0.06
        if weight(height_m, "space") > 0 or height_m > BIOMES[3]["from"] - 200:
            while self.next_nebula < climbed * f + HEIGHT + 400 + self.lookahead:
                self.next_nebula = max(self.next_nebula, climbed * f + HEIGHT) + random.uniform(250, 450)
                rng = random.Random(random.random())
                color = random.choice([(170, 70, 240), (50, 180, 210), (230, 80, 160), (100, 100, 240)])
                item = {"alt": self.next_nebula, "x": random.uniform(0, WIDTH),
                        "image": make_nebula(rng, random.randint(90, 140), color)}
                if random.random() < 0.4:
                    item["planet"] = make_planet(rng, random.randint(22, 38))
                self.nebulae.append(item)
            self.nebulae = [n for n in self.nebulae if HEIGHT - (n["alt"] - climbed * f) < HEIGHT + 400]
        if weight(height_m, "space") > 0.5 and self.shooting is None and random.random() < 0.004:
            self.shooting = [random.uniform(WIDTH * 0.3, WIDTH), random.uniform(0, HEIGHT * 0.4), 30]
        if self.shooting:
            self.shooting[0] -= 14
            self.shooting[1] += 6
            self.shooting[2] -= 1
            if self.shooting[2] <= 0:
                self.shooting = None

    # --- рисование ---

    def draw_sky(self, surf, height_m):
        """Небо полосами: каждая следующая полоса чуть светлее, стык — «шахматкой»."""
        top, bottom = blend(height_m, "top"), blend(height_m, "bottom")
        size = surf.get_size()
        key = (top, bottom, size)
        if key != self.sky_key:
            w, h = size
            sky = pygame.Surface(size)
            band_h = h / SKY_BANDS
            colors = [lerp_color(top, bottom, (i / (SKY_BANDS - 1)) ** 1.3) for i in range(SKY_BANDS)]
            for i, color in enumerate(colors):
                sky.fill(color, (0, round(i * band_h), w, round(band_h) + 1))
            for i, color in enumerate(colors[1:], start=1):
                sky.blit(checker_strip(w, 4, color), (0, round(i * band_h) - 4))
            self.sky = sky
            self.sky_key = key
        surf.blit(self.sky, (0, 0))

    def draw_faded(self, surf, image, pos, amount):
        """Рисует картинку, проявляя её по мере того, как зона вступает в силу."""
        if amount >= 0.97:
            surf.blit(image, pos)
        elif amount > 0.03:
            image.set_alpha(int(amount * 255))
            surf.blit(image, pos)
            image.set_alpha(255)

    def draw(self, surf, climbed, oy=0):
        """Рисует фон. oy — насколько всё сдвинуто вниз (когда холст выше экрана, как в дуэли)."""
        height_m = climbed / PIXELS_PER_METER
        view_h = surf.get_height()
        self.draw_sky(surf, height_m)

        # звёзды: одиночные пиксели, яркие — крестиком; мерцают
        stars = blend(height_m, "stars")
        if stars > 0.05:
            top, bottom = self.sky_key[:2]
            for x, y, bright, phase in self.stars:
                y = int((y + climbed * 0.02) % (HEIGHT * 2))
                if y >= view_h:
                    continue
                k = stars * (0.55 + 0.45 * math.sin(self.time * 2 + phase)) * (1 - y / view_h * 0.6)
                color = lerp_color(lerp_color(top, bottom, y / view_h), (255, 252, 230), k)
                surf.set_at((x, y), color)
                if bright and k > 0.5 and 0 < y < view_h - 1 and 0 < x < WIDTH - 1:
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        surf.set_at((x + dx, y + dy), lerp_color(color, top, 0.4))
        if self.shooting:
            x, y, _ = self.shooting
            pygame.draw.line(surf, (255, 255, 255), (x, y), (x + 40, y - 17), 2)

        # луна над долиной (очень далеко — почти не двигается)
        self.draw_faded(surf, self.moon, (90, 50 + climbed * 0.02 + oy * 0.5), weight(height_m, "valley"))
        # кровавое солнце: выплывает сверху и медленно «садится» по мере подъёма
        sunset = weight(height_m, "sunset")
        if sunset > 0.03:
            sun_y = HEIGHT - (1180 - climbed * 0.14) + oy
            self.draw_faded(surf, self.sun, (WIDTH // 2 - 130, sun_y), sunset)
        # большая луна над облаками
        clouds = weight(height_m, "clouds")
        if clouds > 0.03:
            moon_y = HEIGHT - (2200 - climbed * 0.12) + oy
            self.draw_faded(surf, self.big_moon, (WIDTH - 300, moon_y), clouds)

        # туманности и планеты в космосе
        for n in self.nebulae:
            y = HEIGHT - (n["alt"] - climbed * 0.06) + oy
            image = n["image"]
            surf.blit(image, (n["x"] - image.get_width() / 2, y - image.get_height() / 2))
            if "planet" in n:
                surf.blit(n["planet"], (n["x"] + 30, y - 10))

        # облака — позади гор и замка (в долине они не должны закрывать замок)
        for layer in self.cloud_layers:
            for cloud in layer["clouds"]:
                y = self.cloud_screen_y(cloud, layer, climbed) + oy
                if -300 < y < view_h + 50:
                    surf.blit(cloud["image"], (int(cloud["x"]), int(y)))

        # горы, замок, долина и лес — уезжают вниз, когда поднимаемся (дальние — медленнее)
        for image, factor, top in self.ground_layers:
            y = top + climbed * factor + oy
            if y < view_h:
                surf.blit(image, (0, y))

        # вороны на фоне заката (и немного — над долиной)
        ravens = min(1.0, sunset * 1.2 + weight(height_m, "valley") * 0.3)
        if ravens > 0.1:
            count = int(len(self.ravens) * ravens)
            for x, y, _, phase in self.ravens[:count]:
                up = math.sin(self.time * 9 + phase) > 0
                x, y = int(x), int(y + oy)
                wing = -3 if up else 2
                pygame.draw.lines(surf, (20, 10, 22), False, [(x - 6, y + wing), (x - 2, y), (x, y + 1), (x + 2, y),
                                                             (x + 6, y + wing)], 2)

        # море облаков: в зоне облаков оно всегда внизу, под Сларком, — поднимается снизу и проявляется
        if clouds > 0.03:
            sea_y = view_h - 150 + (1 - clouds) * 160
            self.draw_faded(surf, self.cloud_sea, (0, sea_y), clouds)

        # светлячки над долиной
        valley = weight(height_m, "valley")
        if valley > 0.05:
            for x, y, phase in self.fireflies:
                glow = valley * (0.5 + 0.5 * math.sin(self.time * 3 + phase * 5))
                if glow > 0.25:
                    self.firefly_glow.set_alpha(int(glow * 255))
                    surf.blit(self.firefly_glow, (int(x) - 4, int(y) - 4 + oy), special_flags=pygame.BLEND_RGB_ADD)

    def draw_front(self, surf, climbed, oy=0):
        """То, что поверх игры: название новой зоны."""
        view_h = surf.get_height()
        if self.banner_timer > 0 and self.banner_text:
            alpha = min(255, self.banner_timer * 6, (180 - self.banner_timer) * 8)
            center_y = view_h // 3
            shadow = big_font.render(BIOMES[self.banner_index]["name"], False, (30, 12, 30))
            for image, dx in ((shadow, 3), (self.banner_text, 0)):
                image = image.copy()
                image.set_alpha(alpha)
                surf.blit(image, image.get_rect(center=(WIDTH // 2 + dx, center_y + dx)))
            sub = small_font.render(f"{BIOMES[self.banner_index]['from']} м", False, (240, 226, 220))
            sub.set_alpha(alpha)
            surf.blit(sub, sub.get_rect(center=(WIDTH // 2, center_y + 45)))
