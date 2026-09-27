"""Графика «Прыжков Сларка»: пиксель-арт в стиле тёмного фэнтези.

Герой — спрайт из assets/slark.png (подготовлен инструментом tools/prepare_sprite.py).
Его анимация — сдвиги целых пикселей (pixel_art.py): колышутся хвост и шипы капюшона,
машет плавник, при приземлении он сплющивается, в прыжке вытягивается, в полёте наклоняется.

Всё остальное рисуется кодом гладко, а потом превращается в пиксель-арт:
цвета сводятся к палитре тёмного фэнтези, добавляются светотень и фактура «как руками»
и двойной контур, как у героя (кровавая кайма — враги, золотая — бонусы).
"""
import math
from pathlib import Path

import pygame

import pixel_art as px

ASSETS = Path(__file__).resolve().parent / "assets"
SS = 4                      # во сколько раз крупнее рисуем перед уменьшением
FRAMES = 8                  # кадров в каждой анимации


# --- Инструменты гладкого рисования (потом всё пикселизуется) ---

class Pen:
    """Рисует в «дизайнерских» координатах: сама умножает их на k."""

    def __init__(self, surface, k):
        self.surface = surface
        self.k = k

    def pt(self, x, y):
        return round(x * self.k), round(y * self.k)

    def polygon(self, color, points):
        pygame.draw.polygon(self.surface, color, [self.pt(x, y) for x, y in points])

    def ellipse(self, color, x, y, w, h):
        k = self.k
        pygame.draw.ellipse(self.surface, color, pygame.Rect(round(x * k), round(y * k), round(w * k), round(h * k)))

    def circle(self, color, x, y, r):
        pygame.draw.circle(self.surface, color, self.pt(x, y), max(1, round(r * self.k)))

    def line(self, color, a, b, width):
        pygame.draw.line(self.surface, color, self.pt(*a), self.pt(*b), max(1, round(width * self.k)))

    def limb(self, color, points, width):
        for a, b in zip(points, points[1:]):
            self.line(color, a, b, width)
        for x, y in points:
            self.circle(color, x, y, width / 2)

    def rect(self, color, x, y, w, h, radius=0):
        k = self.k
        pygame.draw.rect(self.surface, color, pygame.Rect(round(x * k), round(y * k), round(w * k), round(h * k)),
                         border_radius=round(radius * k))


def render(width, height, draw, scale=1.0, rim=None, outline=True, texture=0.0, seed=1):
    """Рисует картинку функцией draw(pen) размером width×height × scale, потом превращает
    в пиксель-арт: палитра, светотень (и фактура, если texture > 0), контур."""
    w, h = round(width * scale), round(height * scale)
    big = pygame.Surface((w * SS, h * SS), pygame.SRCALPHA)
    draw(Pen(big, SS * scale))
    image = px.shade(px.pixelize(pygame.transform.smoothscale(big, (w, h))), texture, seed)
    return px.outlined(image, rim=rim) if outline else image


def make_glow(radius, color):
    """Мягкое свечение на чёрном фоне — рисуется поверх с «добавлением света» (BLEND_RGB_ADD)."""
    glow = pygame.Surface((radius * 2, radius * 2))
    for r in range(radius, 0, -1):
        k = (1 - r / radius) ** 2
        pygame.draw.circle(glow, [int(c * k) for c in color], (radius, radius), r)
    return glow


def phases():
    return [i / FRAMES * math.tau for i in range(FRAMES)]


def flipped(frames):
    return [pygame.transform.flip(f, True, False) for f in frames]


# --- Герой ---

HERO_PAD = 3
# Части спрайта — в долях его ширины и высоты (подходит для любого размера спрайта).
TAIL = (0.0, 0.07, 0.40, 0.30)      # изогнутый хвост сверху слева: x, y, ширина, высота
FIN = (0.0, 0.59, 0.36, 0.36)       # плавник снизу слева
SPIKES_BOTTOM = 0.27                # выше этой доли высоты — шипы капюшона
BODY_ROWS = (0.31, 0.91)            # ряды, которые дублируем/выкидываем при вытягивании/сплющивании
BODY_COLUMNS = (0.29, 0.92)         # столбцы — при расширении/сужении
SQUASH_LEVELS = (-2, -1, 0, 1, 2)   # <0 — сплющен, >0 — вытянут
LEANS = (-1, 0, 1)                  # наклон назад / прямо / вперёд


class HeroFrame:
    """Кадр героя и точка, которой он стоит на земле (середина ступней)."""

    def __init__(self, image, anchor_x, feet_y):
        self.image = image
        self.anchor_x = anchor_x
        self.feet_y = feet_y


def part(fraction_rect, size):
    """Прямоугольник части спрайта в пикселях (с учётом полей HERO_PAD)."""
    w, h = size
    x, y, fw, fh = fraction_rect
    return (round(x * w), round(y * h) + HERO_PAD, round(fw * w) + HERO_PAD, round(fh * h))


def build_hero_frame(base, sprite_size, anchor_x, feet_y, t, squash, lean):
    w, h = sprite_size
    image = base
    # хвост описывает маленький круг, плавник машет вверх-вниз
    image = px.move_region(image, part(TAIL, sprite_size), round(math.sin(t)), round(math.cos(t)))
    image = px.move_region(image, part(FIN, sprite_size), 0, round(math.sin(t + 1.8) * 1.5))
    # шипы капюшона колышутся волной (чем выше ряд, тем сильнее)
    spikes = SPIKES_BOTTOM * h + HERO_PAD
    image = px.shift_rows(image, lambda y: round(math.sin(t * 1.3 + y * 0.5) * 1.2 * max(0, spikes - y) / spikes),
                          margin=2)
    anchor_x += 2
    # вытягивание (squash > 0): лишние ряды в теле, тело чуть уже; сплющивание — наоборот
    rows = px.stretch_band(image.get_height(), round(BODY_ROWS[0] * h) + HERO_PAD,
                           round(BODY_ROWS[1] * h) + HERO_PAD, squash * 2)
    image = px.remap_rows(image, rows)
    columns = px.stretch_band(image.get_width(), round(BODY_COLUMNS[0] * w) + HERO_PAD + 2,
                              round(BODY_COLUMNS[1] * w) + HERO_PAD + 2, -squash)
    image = px.remap_columns(image, columns)
    anchor_x = next(i for i, c in enumerate(columns) if c >= anchor_x)
    feet_y = image.get_height() - (base.get_height() - feet_y)
    # наклон: верх сдвинут вперёд или назад лесенкой, ступни на месте
    height = image.get_height()
    image = px.shift_rows(image, lambda y: round(lean * 3 * (feet_y - y) / height), margin=3)
    anchor_x += 3
    return HeroFrame(image, anchor_x, feet_y)


def load_hero_base():
    sprite = pygame.image.load(ASSETS / "slark.png").convert_alpha()
    base = px.padded(sprite, HERO_PAD)
    mask = pygame.mask.from_surface(base)
    feet_y = max(y for x in range(base.get_width()) for y in range(base.get_height()) if mask.get_at((x, y))) + 1
    feet_columns = [x for x in range(base.get_width()) if mask.get_at((x, feet_y - 1))]
    anchor_x = sum(feet_columns) // len(feet_columns)
    return base, sprite.get_size(), anchor_x, feet_y


def build_hero():
    """Все кадры героя: [смотрит вправо/влево][(сплющивание, наклон)][фаза]."""
    base, size, anchor_x, feet_y = load_hero_base()
    frames = {"right": {}, "left": {}}
    for squash in SQUASH_LEVELS:
        for lean in LEANS:
            right = [build_hero_frame(base, size, anchor_x, feet_y, t, squash, lean) for t in phases()]
            frames["right"][squash, lean] = right
            frames["left"][squash, lean] = [
                HeroFrame(pygame.transform.flip(f.image, True, False), f.image.get_width() - 1 - f.anchor_x, f.feet_y)
                for f in right]
    return frames


# --- Враги ---

CREEP_W, CREEP_H = 44, 50          # скелет-воин
FAMILIAR_W, FAMILIAR_H = 64, 48    # горгулья
MINE_W, MINE_H = 44, 42            # проклятая мина

BONE, BONE_DARK = (206, 194, 162), (132, 118, 94)
RUST, IRON = (130, 78, 54), (104, 110, 128)


def draw_skeleton(pen, t):
    """Скелет-воин: ржавый шлем, меч, щит, рваный плащ, горящие глаза. t — фаза шага."""
    swing = math.sin(t)
    bob = abs(math.sin(t)) * 1.2
    # рваный плащ за спиной
    pen.polygon((96, 20, 30), [(15, 16 - bob), (26, 16 - bob), (25, 30), (22, 38), (20, 33), (17, 39), (14, 33),
                               (11, 37)])
    # дальняя нога
    pen.limb(BONE_DARK, [(20, 30 - bob), (20 - swing * 3, 39), (19 - swing * 5, 47)], 2.4)
    pen.ellipse(BONE_DARK, 16 - swing * 5, 45.5, 6, 2.5)
    # щит на дальней руке
    pen.circle((78, 48, 32), 10, 26 - bob, 7.5)
    pen.circle((104, 66, 42), 10, 26 - bob, 6)
    pen.circle(IRON, 10, 26 - bob, 2)
    for a in range(0, 360, 90):
        pen.circle((150, 150, 160), 10 + math.cos(math.radians(a)) * 5.5, 26 - bob + math.sin(math.radians(a)) * 5.5,
                   0.8)
    # таз, позвоночник, рёбра
    pen.rect(BONE, 16, 28 - bob, 11, 3.5, 1.5)
    pen.line(BONE, (22, 16 - bob), (22, 29 - bob), 2)
    pen.ellipse(BONE, 15, 15 - bob, 14, 12)
    pen.ellipse((44, 30, 40), 17, 17 - bob, 10, 8)
    for i in range(3):
        pen.line(BONE, (16.5, 19 + i * 2.6 - bob), (27.5, 19 + i * 2.6 - bob), 1)
    # ближняя нога
    pen.limb(BONE, [(24, 30 - bob), (24 + swing * 3, 39), (25 + swing * 5, 47)], 2.4)
    pen.ellipse(BONE, 23 + swing * 5, 45.5, 6, 2.5)
    # череп с горящими глазницами и железный шлем с шипом
    pen.circle(BONE, 25, 10 - bob, 6.8)
    pen.rect(BONE, 22, 14 - bob, 8, 3.5, 1)
    for i in range(4):  # зубы
        pen.line((50, 40, 36), (23 + i * 2, 14.5 - bob), (23 + i * 2, 17 - bob), 0.6)
    pen.circle((26, 12, 30), 27.3, 9.8 - bob, 2.5)
    pen.circle((255, 110, 30), 27.6, 9.8 - bob, 1.3)
    pen.circle((26, 12, 30), 22.5, 9.8 - bob, 1.6)
    pen.polygon((116, 122, 140), [(17.5, 8 - bob), (18.5, 3 - bob), (25, 0 - bob), (31.5, 3 - bob), (32.5, 8 - bob)])
    pen.polygon((80, 86, 102), [(17.5, 8 - bob), (18.5, 5 - bob), (32, 5 - bob), (32.5, 8 - bob)])
    pen.polygon((160, 166, 184), [(24, 0.5 - bob), (25, -5 - bob), (26.5, 0.5 - bob)])
    # рука с ржавым мечом
    hand = (35 + swing * 2, 21 - bob)
    pen.limb(BONE, [(26, 17 - bob), (31, 21 - bob), hand], 2.2)
    tip = (44 + swing * 2, 5 - bob + swing * 2)
    pen.polygon((150, 156, 170), [(hand[0] - 1, hand[1] - 1), (tip[0], tip[1]), (tip[0] + 2.5, tip[1] + 1.5),
                                  (hand[0] + 1.5, hand[1] + 1)])
    pen.line(RUST, (hand[0] + 1, hand[1] - 1), ((hand[0] + tip[0]) / 2, (hand[1] + tip[1]) / 2), 1)
    pen.line((90, 60, 36), (hand[0] - 3, hand[1] - 2), (hand[0] + 3, hand[1] + 2), 2)


def draw_gargoyle(pen, t):
    """Горгулья из тёмного камня: рога, огненные глаза, крылья летучей мыши. t — фаза взмаха."""
    flap = math.sin(t)
    stone, stone_dark, stone_light = (84, 76, 102), (50, 44, 64), (128, 118, 146)
    tip_y = 4 + (1 - flap) * 16
    for side in (-1, 1):
        root = (32 + side * 5, 22)
        tip = (32 + side * 30, tip_y)
        membrane = [root, tip, (32 + side * 27, tip_y + 12), (32 + side * 21, tip_y + 8), (32 + side * 18, tip_y + 14),
                    (32 + side * 12, 30)]
        pen.polygon((70, 30, 44) if side < 0 else (96, 40, 58), membrane)
        pen.line(stone_light, root, tip, 1.4)
        pen.line(stone_dark, (32 + side * 21, tip_y + 8), (32 + side * 9, 24), 1)
    pen.line(stone_dark, (30, 32), (21, 43), 3)
    pen.polygon(stone_dark, [(21, 43), (15, 46), (20, 38)])
    pen.ellipse(stone, 23, 18, 18, 18)
    pen.ellipse(stone_light, 27, 20, 8, 7)
    for i in range(3):
        pen.line(stone_dark, (26, 27 + i * 2.5), (38, 27 + i * 2.5), 0.8)
    pen.ellipse(stone, 33, 10, 15, 13)
    pen.polygon((200, 188, 158), [(36, 12), (31, 1), (39, 10)])
    pen.polygon((200, 188, 158), [(44, 12), (50, 1), (41, 10)])
    pen.ellipse((255, 140, 40), 40, 14, 4.5, 3.5)
    pen.ellipse((255, 232, 150), 41, 14.5, 1.5, 1.5)
    pen.polygon((236, 230, 210), [(42, 20), (44, 20), (43, 23.5)])
    pen.limb(stone_dark, [(28, 33), (27, 38)], 3)
    pen.limb(stone_dark, [(36, 33), (37, 38)], 3)


def draw_cursed_mine(pen, eye_open):
    """Проклятая мина: железный шар с шипами и глазом (глаз открыт — горит)."""
    cx, cy = 22, 21
    for angle in range(0, 360, 45):
        a = math.radians(angle + 22)
        base1 = (cx + math.cos(a - 0.25) * 10, cy + math.sin(a - 0.25) * 10)
        base2 = (cx + math.cos(a + 0.25) * 10, cy + math.sin(a + 0.25) * 10)
        tip = (cx + math.cos(a) * 19, cy + math.sin(a) * 19)
        pen.polygon((116, 120, 136), [base1, tip, base2])
    pen.circle((70, 62, 72), cx, cy, 12)
    pen.circle((104, 94, 106), cx - 3, cy - 3, 7)
    pen.rect(RUST, cx - 12, cy + 3, 24, 3)
    if eye_open:
        pen.ellipse((255, 214, 110), cx - 6, cy - 4, 12, 7)
        pen.ellipse((210, 60, 30), cx - 3, cy - 3.5, 6, 6)
        pen.rect((30, 10, 16), cx - 0.8, cy - 3.5, 1.6, 6)
    else:
        pen.line((30, 10, 16), (cx - 6, cy - 0.5), (cx + 6, cy - 0.5), 1.4)
        pen.line((160, 40, 40), (cx - 5, cy + 0.8), (cx + 5, cy + 0.8), 0.8)


# --- Бонусы ---

def draw_mushroom(pen, squeeze):
    """Светящийся гриб-батут (вместо пружины). squeeze от 0 до 1 — насколько примят."""
    cap_y = 4 + squeeze * 6
    pen.rect((198, 188, 164), 12, cap_y + 6, 7, 24 - cap_y - 6, 2)
    pen.rect((150, 140, 116), 12, cap_y + 6, 2.5, 24 - cap_y - 6, 1)
    pen.ellipse((82, 34, 112), 1, cap_y, 29, 12 - squeeze * 3)
    pen.ellipse((140, 70, 180), 3, cap_y + 1, 25, 7 - squeeze * 2)
    for x, y, r in ((8, cap_y + 3, 1.8), (16, cap_y + 2, 2.2), (23, cap_y + 4, 1.6)):
        pen.circle((226, 196, 246), x, y, r)
    pen.rect((92, 184, 168), 4, cap_y + 9 - squeeze * 2, 23, 1.5)
    pen.ellipse((56, 74, 38), 6, 24, 19, 4)


def draw_wings_item(pen, t):
    """«Крылья тьмы» (вместо ракеты): пара крыльев летучей мыши вокруг проклятого кристалла."""
    flap = math.sin(t) * 3
    for side in (-1, 1):
        root = (20 + side * 3, 16)
        tip = (20 + side * 19, 3 - flap)
        pen.polygon((52, 20, 74), [root, tip, (20 + side * 18, 14 - flap), (20 + side * 13, 12), (20 + side * 11, 20),
                                   (20 + side * 6, 18)])
        pen.line((152, 138, 112), root, tip, 1.2)
        pen.line((118, 56, 156), (20 + side * 13, 12), (20 + side * 6, 16), 0.8)
    pen.polygon((118, 56, 156), [(20, 8), (25, 16), (20, 26), (15, 16)])
    pen.polygon((206, 146, 236), [(20, 10), (22.5, 16), (20, 20), (18, 16)])
    pen.circle((255, 255, 255), 19, 13, 0.8)


def draw_flight_wings(pen, t):
    """Крылья, которые раскрываются за спиной Сларка во время полёта."""
    flap = math.sin(t)
    for side in (-1, 1):
        root = (40 + side * 4, 26)
        tip = (40 + side * 36, 6 + (1 - flap) * 14)
        elbow = (40 + side * 24, 12 + (1 - flap) * 6)
        membrane = [root, elbow, tip, (40 + side * 33, 20 + (1 - flap) * 8), (40 + side * 26, 24 + (1 - flap) * 3),
                    (40 + side * 18, 30), (40 + side * 10, 32)]
        pen.polygon((62, 24, 88) if side < 0 else (82, 34, 112), membrane)
        pen.line((170, 156, 128), root, elbow, 1.6)
        pen.line((170, 156, 128), elbow, tip, 1.2)
        pen.line((118, 56, 156), elbow, (40 + side * 18, 30), 0.9)


def draw_dagger(pen):
    """Кинжал Сларка, остриём вверх: стальной клинок с долом, золотая гарда, обмотанная рукоять."""
    pen.polygon((160, 166, 184), [(5, 0), (8.5, 6), (8, 17), (2, 17), (1.5, 6)])
    pen.polygon((214, 218, 230), [(5, 1), (6.5, 6), (6, 16), (5, 16)])
    pen.line((80, 86, 102), (5, 5), (5, 15), 0.7)
    pen.rect((230, 190, 70), 0, 17, 10, 2.5, 1)
    pen.rect((96, 60, 40), 3, 19.5, 4, 5)
    for y in (20.5, 22.5):
        pen.line((150, 68, 18), (3, y), (7, y + 1), 0.8)
    pen.circle((230, 190, 70), 5, 25.5, 1.8)


def draw_shadow_orb(pen, t):
    pen.circle((52, 20, 74), 20, 20, 17)
    for i in range(5):
        a = t + i * math.tau / 5
        pen.circle((160, 90, 200), 20 + math.cos(a) * 9, 20 + math.sin(a) * 9, 5)
    pen.circle((26, 12, 30), 20, 20, 9)
    pen.ellipse((255, 190, 76), 14, 17, 5, 3)
    pen.ellipse((255, 190, 76), 21, 17, 5, 3)


# --- Платформы ---

PLATFORM_DRAW_H = 26        # картинка платформы выше её «ступени» (16 px): мох и цепи свисают
TEXTURED = {"valley": 0.22, "sunset": 0.2, "clouds": 0.14, "space": 0.16}


def draw_platform(pen, kind, biome, w):
    h = 18
    if kind == "breaking":
        # гнилые доски с трещиной и отломанным углом
        pen.rect((70, 42, 30), 0, 3, w, h - 3, 2)
        for x in range(0, int(w), 16):
            pen.rect((96, 60, 40) if x // 16 % 2 else (84, 52, 34), x + 1, 4, 14, h - 6, 1)
        pen.polygon((0, 0, 0, 0), [(w - 14, h), (w, h - 7), (w, h)])
        mid = w / 2
        pen.polygon((30, 18, 16), [(mid - 3, 3), (mid + 2, 3), (mid, 9), (mid + 4, h - 1), (mid - 1, 10), (mid - 4, h - 1),
                                   (mid - 2, 8)])
        for x in (8, w - 22):
            pen.circle((110, 126, 64), x, 6, 1.6)
        return
    if kind == "vanishing":
        # призрачная плита: полупрозрачная, с завитками
        pen.rect((56, 138, 134, 190), 0, 3, w, h - 5, 6)
        pen.rect((150, 226, 206, 220), 3, 4, w - 6, 3, 2)
        for x in range(8, int(w) - 6, 16):
            pen.line((150, 226, 206, 200), (x, h - 2), (x + 3, h + 5), 1.2)
            pen.circle((92, 184, 168, 200), x + 3, h + 5, 1.4)
        return
    if kind == "trampoline":
        # гроздь светящихся грибов
        pen.rect((56, 74, 38), 2, 12, w - 4, 8, 3)
        for i, x in enumerate(range(10, int(w) - 6, 22)):
            pen.rect((198, 188, 164), x - 2, 6, 5, 8, 1)
            pen.ellipse((82, 34, 112), x - 11, 0, 22, 10)
            pen.ellipse((140, 70, 180), x - 9, 1, 18, 5)
            pen.circle((226, 196, 246), x - 4, 3, 1.5)
            pen.circle((226, 196, 246), x + 3, 4, 1.2)
        return

    if biome == "valley":
        # булыжник: два ряда камней, сверху мох, вниз свисают корни
        pen.rect((34, 28, 44), 0, 3, w, h - 3, 3)
        for x in range(0, int(w), 13):
            pen.rect((74, 64, 88) if x // 13 % 2 else (88, 78, 102), x + 1, 4, 12, 6, 2)
        for x in range(-6, int(w), 13):
            pen.rect((64, 56, 78) if x // 13 % 2 else (80, 70, 94), x + 1, 11, 12, 6, 2)
        pen.rect((56, 74, 38), 0, 1, w, 5, 3)
        for x in range(2, int(w), 6):
            pen.circle((80, 98, 50) if x % 12 else (110, 126, 64), x, 2 + (x * 7 % 3) * 0.6, 2.4)
        for x in range(7, int(w) - 4, 17):
            pen.line((56, 74, 38), (x, h - 1), (x + (x % 3) - 1, h + 5 + x % 4), 1.3)
    elif biome == "sunset":
        # тёмная балка: доски, железные скобы с заклёпками, снизу цепи
        pen.rect((48, 28, 22), 0, 3, w, h - 4, 2)
        pen.rect((70, 42, 30), 0, 4, w, 5, 1)
        pen.rect((62, 38, 26), 0, 10, w, 5, 1)
        for x in range(6, int(w) - 6, 30):
            pen.rect((80, 86, 102), x, 3, 5, h - 4)
            pen.circle((170, 170, 180), x + 2.5, 6, 0.9)
            pen.circle((170, 170, 180), x + 2.5, 13, 0.9)
        for x in (12, w - 14):
            for i in range(3):
                pen.ellipse((116, 122, 140), x - 1.5, h - 1 + i * 3, 3, 4)
    elif biome == "clouds":
        # древний мрамор с золотой каймой и трещинами
        pen.rect((132, 122, 146), 0, 3, w, h - 4, 2)
        pen.rect((170, 160, 182), 0, 3, w, 5, 2)
        pen.rect((230, 190, 70), 0, h - 4, w, 2)
        for x in range(10, int(w) - 8, 24):
            pen.polygon((230, 190, 70), [(x, 11), (x + 3, 8), (x + 6, 11), (x + 3, 14)])
        pen.line((74, 64, 88), (w * 0.3, 3), (w * 0.35, 9), 0.8)
        pen.line((74, 64, 88), (w * 0.35, 9), (w * 0.31, 13), 0.8)
    else:  # space
        # обсидиан с горящими рунами и кристаллами
        pen.rect((20, 16, 28), 0, 4, w, h - 5, 3)
        pen.rect((52, 44, 64), 0, 4, w, 3, 2)
        for x in range(8, int(w) - 8, 18):
            pen.line((160, 90, 200), (x, 10), (x + 4, 14), 1)
            pen.line((160, 90, 200), (x + 4, 10), (x, 14), 1)
        for x in range(4, int(w) - 4, 26):
            pen.polygon((118, 56, 156), [(x, 5), (x + 3, -1), (x + 6, 5)])
            pen.polygon((206, 146, 236), [(x + 2, 4), (x + 3, 1), (x + 4, 4)])

    if kind == "moving":
        # бирюзовые руны-стрелки: платформа ездит влево-вправо
        pen.rect((92, 184, 168), 4, h - 1, w - 8, 2, 1)
        for x, d in ((6, -1), (w - 6, 1)):
            pen.polygon((150, 226, 206), [(x, 7), (x - d * 4, 10), (x, 13)])
    elif kind == "elevator":
        # проклятая руна посередине и обрывки цепей: платформа ездит вверх-вниз
        cx = w / 2
        pen.circle((82, 34, 112), cx, 10, 5)
        pen.polygon((206, 146, 236), [(cx - 3, 11), (cx, 6), (cx + 3, 11)])
        pen.polygon((206, 146, 236), [(cx - 3, 12), (cx, 16), (cx + 3, 12)])
        for x in (4, w - 7):
            for i in range(2):
                pen.ellipse((116, 122, 140), x, h - 1 + i * 3, 3, 4)


class Art:
    """Все картинки игры. Создаются один раз при запуске."""

    def __init__(self):
        self.hero = build_hero()
        skeleton = [render(CREEP_W, CREEP_H, lambda pen, t=t: draw_skeleton(pen, t), rim=px.RIM_ENEMY)
                    for t in phases()]
        self.creep = {"right": skeleton, "left": flipped(skeleton)}
        gargoyle = [render(FAMILIAR_W, FAMILIAR_H, lambda pen, t=t: draw_gargoyle(pen, t), rim=px.RIM_ENEMY)
                    for t in phases()]
        self.familiar = {"right": gargoyle, "left": flipped(gargoyle)}
        self.mine = [render(MINE_W, MINE_H, lambda pen, o=o: draw_cursed_mine(pen, o), rim=px.RIM_ENEMY)
                     for o in (False, True)]
        self.spring = [render(31, 28, lambda pen, s=s: draw_mushroom(pen, s), rim=px.RIM_ITEM) for s in (0, 1)]
        self.rocket = render(40, 28, lambda pen: draw_wings_item(pen, 0), rim=px.RIM_ITEM)
        self.flight_wings = [render(80, 40, lambda pen, t=t: draw_flight_wings(pen, t)) for t in phases()]
        self.dagger = render(10, 28, draw_dagger, rim=px.RIM_HERO)
        self.dagger_glow = make_glow(12, (120, 70, 20))
        self.shadow_orb = [render(40, 40, lambda pen, t=t: draw_shadow_orb(pen, t), rim=px.RIM_ITEM)
                           for t in phases()]
        self.mine_glow = make_glow(26, (255, 70, 20))
        self.rocket_glow = make_glow(34, (150, 60, 220))
        self.shadow_glow = make_glow(50, (150, 80, 255))
        self.platforms = {}
        base, size, anchor_x, feet_y = load_hero_base()
        self.icon = build_hero_frame(base, size, anchor_x, feet_y, 0, 0, 0).image

    def platform(self, kind, biome, width):
        key = (kind, biome, width)
        if key not in self.platforms:
            texture = TEXTURED.get(biome, 0) if kind in ("normal", "moving", "elevator", "breaking") else 0
            self.platforms[key] = render(width, PLATFORM_DRAW_H, lambda pen: draw_platform(pen, kind, biome, width),
                                         texture=texture, seed=width)
        return self.platforms[key]
