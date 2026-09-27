"""Готовит спрайт героя из картинки-скриншота пиксель-арта.

Что делает:
1. Убирает фон-«шахматку» (белые и светло-серые клетки, связанные с краем картинки).
2. Возвращает картинку к исходной сетке пикселей: каждый квадрат PIXEL×PIXEL становится одним пикселем
   (цвет — средний по «большинству» похожих пикселей квадрата).
3. Сводит тысячи «мыльных» оттенков к небольшой палитре — как в настоящем пиксель-арте.

Запуск: .venv\\Scripts\\python.exe tools\\prepare_sprite.py путь_к_картинке.png [размер_пикселя] [куда_сохранить]
Размер пикселя по умолчанию — PIXEL. Чем он больше, тем меньше получится герой
(3.8 — примерно 91×87, 5.7 — примерно 60×58).
Результат: assets\\slark.png (герой смотрит вправо).
"""
import sys
from collections import deque
from pathlib import Path

import numpy as np
import pygame

PIXEL = 5.7          # сколько пикселей картинки превращаются в один пиксель спрайта (3.8 — исходная сетка)
OFFSET = 0.0         # сдвиг сетки
PALETTE_SIZE = 28    # сколько цветов оставить
FLIP = False         # True — если на картинке герой смотрит влево (в игре нужен взгляд вправо)

OUT = Path(__file__).resolve().parent.parent / "assets" / "slark.png"


def remove_background(a):
    """Маска фона: светлые серые пиксели, до которых можно «дойти» от края картинки."""
    h, w, _ = a.shape
    light = (a.min(axis=2) > 200) & ((a.max(axis=2) - a.min(axis=2)) < 18)
    background = np.zeros((h, w), bool)
    queue = deque([(y, x) for y in range(h) for x in (0, w - 1)] + [(y, x) for x in range(w) for y in (0, h - 1)])
    while queue:
        y, x = queue.popleft()
        if 0 <= y < h and 0 <= x < w and not background[y, x] and light[y, x]:
            background[y, x] = True
            queue.extend(((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)))
    return background


def to_grid(a, background):
    """Каждый квадрат сетки → один пиксель. Возвращает (цвета HxWx3, непрозрачность HxW)."""
    h, w, _ = a.shape
    gw, gh = int((w - OFFSET) / PIXEL), int((h - OFFSET) / PIXEL)
    colors = np.zeros((gh, gw, 3), int)
    solid = np.zeros((gh, gw), bool)
    for gy in range(gh):
        for gx in range(gw):
            x0, x1 = int(OFFSET + gx * PIXEL), int(OFFSET + (gx + 1) * PIXEL)
            y0, y1 = int(OFFSET + gy * PIXEL), int(OFFSET + (gy + 1) * PIXEL)
            block = a[y0:y1, x0:x1].reshape(-1, 3)
            keep = ~background[y0:y1, x0:x1].reshape(-1)
            if keep.mean() < 0.5:
                continue  # квадрат в основном из фона — прозрачный
            block = block[keep]
            # «большинство»: берём пиксель, ближе всего к которому остальные, и усредняем похожие на него
            distances = np.abs(block[:, None, :] - block[None, :, :]).sum(axis=2)
            center = block[distances.sum(axis=1).argmin()]
            similar = block[np.abs(block - center).sum(axis=1) < 60]
            colors[gy, gx] = similar.mean(axis=0)
            solid[gy, gx] = True
    return colors, solid


def reduce_palette(colors, solid, k):
    """Простая k-means кластеризация цветов: оставляем k самых «представительных»."""
    pixels = colors[solid].astype(float)
    rng = np.random.default_rng(1)
    centers = pixels[rng.choice(len(pixels), k, replace=False)]
    for _ in range(25):
        labels = ((pixels[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2).argmin(axis=1)
        for i in range(k):
            if (labels == i).any():
                centers[i] = pixels[labels == i].mean(axis=0)
    result = colors.copy()
    result[solid] = centers[labels].round().astype(int)
    return result


def crop(colors, solid):
    ys, xs = np.where(solid)
    return colors[ys.min():ys.max() + 1, xs.min():xs.max() + 1], solid[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def main(path, out=OUT):
    image = pygame.image.load(path)
    a = pygame.surfarray.array3d(image).transpose(1, 0, 2).astype(int)
    background = remove_background(a)
    colors, solid = to_grid(a, background)
    colors = reduce_palette(colors, solid, PALETTE_SIZE)
    colors, solid = crop(colors, solid)
    if FLIP:
        colors, solid = colors[:, ::-1], solid[:, ::-1]
    h, w = solid.shape
    sprite = pygame.Surface((w, h), pygame.SRCALPHA)
    for y in range(h):
        for x in range(w):
            if solid[y, x]:
                sprite.set_at((x, y), tuple(int(c) for c in colors[y, x]) + (255,))
    pygame.image.save(sprite, out)
    print(f"Готово: {out} ({w}×{h}, цветов: {len({tuple(c) for c in colors[solid]})})")


if __name__ == "__main__":
    if len(sys.argv) > 2:
        PIXEL = float(sys.argv[2])
    main(sys.argv[1], Path(sys.argv[3]) if len(sys.argv) > 3 else OUT)
