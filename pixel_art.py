"""Инструменты пиксель-арта в стиле тёмного фэнтези.

- Палитра — «лесенки» цветов (от тёмного к светлому): камень, мох, дерево, ржавое железо, кость,
  кровь, угли, проклятый фиолетовый, призрачный бирюзовый, золото.
- pixelize(): гладкий рисунок → пиксель-арт из цветов палитры, без полупрозрачных краёв.
- shade(): «ручная» светотень — края, повёрнутые к свету (вверх-влево), на ступеньку светлее,
  в тени (вниз-вправо) — темнее, плюс фактура (россыпь соседних оттенков) на камне и дереве.
- outlined(): двойной контур, как у героя: тёмный внутри и цветная кайма снаружи.
- Деформации спрайта сдвигами целых пикселей (без растягивания и размытия).
"""
import pygame

OUTLINE = (26, 12, 30)          # тёмный контур
RIM_HERO = (254, 142, 29)       # оранжевая кайма героя
RIM_ENEMY = (170, 38, 40)       # кровавая кайма врагов — сразу видно, что опасно
RIM_ITEM = (230, 190, 70)       # золотая кайма бонусов

RAMPS = {
    "stone":  [(20, 16, 28), (34, 28, 44), (52, 44, 64), (74, 64, 88), (100, 90, 114), (132, 122, 146),
               (170, 160, 182)],
    "moss":   [(24, 32, 22), (38, 52, 30), (56, 74, 38), (80, 98, 50), (110, 126, 64), (146, 156, 86)],
    "wood":   [(30, 18, 16), (48, 28, 22), (70, 42, 30), (96, 60, 40), (126, 82, 52), (160, 110, 70)],
    "rust":   [(40, 24, 24), (66, 38, 34), (96, 56, 44), (130, 78, 54), (166, 104, 66), (200, 136, 86)],
    "bone":   [(74, 62, 52), (112, 98, 80), (152, 138, 112), (192, 180, 150), (226, 218, 190), (248, 244, 224)],
    "blood":  [(46, 10, 18), (80, 16, 26), (122, 24, 34), (170, 38, 40), (214, 62, 54), (240, 110, 86)],
    "ember":  [(96, 40, 14), (150, 68, 18), (210, 104, 24), (254, 142, 29), (255, 190, 76), (255, 232, 150)],
    "curse":  [(30, 12, 44), (52, 20, 74), (82, 34, 112), (118, 56, 156), (160, 90, 200), (206, 146, 236)],
    "ghost":  [(14, 36, 44), (24, 62, 70), (36, 96, 100), (56, 138, 134), (92, 184, 168), (150, 226, 206)],
    "night":  [(20, 34, 70), (34, 58, 108), (52, 90, 150), (80, 130, 190), (120, 176, 224), (180, 214, 240)],
    "gold":   [(82, 56, 14), (130, 94, 26), (184, 140, 42), (230, 190, 70), (255, 232, 130)],
    "steel":  [(30, 32, 40), (52, 56, 68), (80, 86, 102), (116, 122, 140), (160, 166, 184), (214, 218, 230)],
}
PALETTE = [c for ramp in RAMPS.values() for c in ramp] + [OUTLINE, (255, 255, 255)]

# где цвет стоит в своей «лесенке» — чтобы делать его на ступеньку светлее или темнее
_place = {}
for _name, _ramp in RAMPS.items():
    for _i, _c in enumerate(_ramp):
        _place.setdefault(_c, (_ramp, _i))

_nearest_cache = {}


def nearest(color):
    """Ближайший цвет палитры (с запоминанием — картинок в игре много, а цветов мало)."""
    key = color[:3]
    found = _nearest_cache.get(key)
    if found is None:
        r, g, b = key
        found = min(PALETTE, key=lambda p: (p[0] - r) ** 2 * 3 + (p[1] - g) ** 2 * 4 + (p[2] - b) ** 2 * 2)
        _nearest_cache[key] = found
    return found


def step(color, delta):
    """Тот же цвет на delta ступенек светлее (или темнее) в его «лесенке»."""
    place = _place.get(color[:3])
    if not place:
        return color[:3]
    ramp, i = place
    return ramp[max(0, min(len(ramp) - 1, i + delta))]


def pixelize(surface, alpha_threshold=120):
    """Гладкий рисунок → пиксель-арт: каждый пиксель либо полностью виден (цвет из палитры), либо прозрачен."""
    result = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    w, h = surface.get_size()
    source = pygame.PixelArray(surface)
    target = pygame.PixelArray(result)
    for x in range(w):
        for y in range(h):
            r, g, b, a = surface.unmap_rgb(source[x, y])
            if a >= alpha_threshold:
                target[x, y] = nearest((r, g, b)) + (255,)
    del source, target
    return result


def _noise(x, y, seed):
    """Одинаковый «шум» для одной и той же точки — фактура не мерцает от кадра к кадру."""
    n = (x * 374761393 + y * 668265263 + seed * 2246822519) & 0xFFFFFFFF
    n = (n ^ (n >> 13)) * 1274126177 & 0xFFFFFFFF
    return (n ^ (n >> 16)) / 0xFFFFFFFF


def shade(surface, texture=0.0, seed=1):
    """Светотень «как руками»: свет сверху-слева, тень снизу-справа; texture — доля пикселей
    с фактурой (0 — гладко, 0.2 — шершавый камень)."""
    w, h = surface.get_size()
    result = surface.copy()
    mask = pygame.mask.from_surface(surface, 127)
    source = pygame.PixelArray(surface)
    target = pygame.PixelArray(result)

    def solid(x, y):
        return 0 <= x < w and 0 <= y < h and mask.get_at((x, y))

    for x in range(w):
        for y in range(h):
            if not mask.get_at((x, y)):
                continue
            color = surface.unmap_rgb(source[x, y])[:3]
            delta = 0
            if not solid(x, y - 1) or not solid(x - 1, y):
                delta += 1                         # край к свету
            if not solid(x, y + 1) or not solid(x + 1, y):
                delta -= 1                         # край в тени
            if texture:
                n = _noise(x, y, seed)
                if n < texture / 2:
                    delta -= 1
                elif n > 1 - texture / 2:
                    delta += 1
            if delta:
                target[x, y] = step(color, delta) + (255,)
    del source, target
    return result


def padded(surface, n):
    result = pygame.Surface((surface.get_width() + 2 * n, surface.get_height() + 2 * n), pygame.SRCALPHA)
    result.blit(surface, (n, n))
    return result


def _ring(surface, color):
    """Контур толщиной 1 пиксель вокруг непрозрачной части (только по 4 направлениям — как рисуют руками)."""
    silhouette = pygame.mask.from_surface(surface, 127).to_surface(setcolor=color + (255,), unsetcolor=(0, 0, 0, 0))
    ring = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        ring.blit(silhouette, (dx, dy))
    ring.blit(surface, (0, 0))
    return ring


def outlined(surface, rim=None, inner=OUTLINE):
    """Тёмный контур и (если задан rim) цветная кайма снаружи. Картинка становится на 2–4 пикселя больше."""
    result = _ring(padded(surface, 2 if rim else 1), inner)
    if rim:
        result = _ring(result, rim)
    return result


# --- Деформации без размытия: двигаем целые ряды и столбцы пикселей ---

def shift_rows(surface, offsets, margin=2):
    """Сдвигает каждый ряд y по горизонтали на offsets(y) пикселей (волна, наклон)."""
    w, h = surface.get_size()
    result = pygame.Surface((w + 2 * margin, h), pygame.SRCALPHA)
    for y in range(h):
        result.blit(surface, (margin + offsets(y), y), (0, y, w, 1))
    return result


def remap_rows(surface, rows):
    """Новая картинка из рядов исходной: rows — список номеров рядов (повтор ряда = вытягивание)."""
    w = surface.get_width()
    result = pygame.Surface((w, len(rows)), pygame.SRCALPHA)
    for y, source_y in enumerate(rows):
        result.blit(surface, (0, y), (0, source_y, w, 1))
    return result


def remap_columns(surface, columns):
    h = surface.get_height()
    result = pygame.Surface((len(columns), h), pygame.SRCALPHA)
    for x, source_x in enumerate(columns):
        result.blit(surface, (x, 0), (source_x, 0, 1, h))
    return result


def stretch_band(count, band_start, band_end, extra):
    """Номера рядов (или столбцов), где внутри полосы [band_start, band_end) равномерно
    повторены (extra > 0) или выкинуты (extra < 0) |extra| рядов."""
    band = list(range(band_start, band_end))
    if extra > 0:
        gap = len(band) / (extra + 1)
        repeat = {band[int(gap * (i + 1))] for i in range(extra)}
        band = [r for b in band for r in ((b, b) if b in repeat else (b,))]
    elif extra < 0:
        gap = len(band) / (-extra + 1)
        drop = {band[int(gap * (i + 1))] for i in range(-extra)}
        band = [b for b in band if b not in drop]
    return list(range(0, band_start)) + band + list(range(band_end, count))


def move_region(surface, rect, dx, dy):
    """Сдвигает кусок картинки (хвост, плавник). Старое место не стираем — так не остаётся дыр."""
    piece = surface.subsurface(rect).copy()
    result = surface.copy()
    result.blit(piece, (rect[0] + dx, rect[1] + dy))
    return result


def silhouette(surface, color):
    return pygame.mask.from_surface(surface, 127).to_surface(setcolor=color, unsetcolor=(0, 0, 0, 0))
