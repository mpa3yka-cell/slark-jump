"""Иконка игры (assets/icon.ico): Сларк на тёмном фоне с оранжевой рамкой. Пиксели увеличиваются без сглаживания.

Запуск: .venv\\Scripts\\python.exe tools\\make_icon.py
"""
import struct
from io import BytesIO
from pathlib import Path

import pygame

ASSETS = Path(__file__).resolve().parent.parent / "assets"
SIZES = [256, 64, 48, 32, 16]


def draw_icon(size):
    canvas = pygame.Surface((128, 128), pygame.SRCALPHA)
    pygame.draw.rect(canvas, (58, 20, 48), (0, 0, 128, 128), border_radius=24)
    pygame.draw.rect(canvas, (254, 142, 29), (4, 4, 120, 120), 3, border_radius=20)
    pygame.draw.rect(canvas, (30, 22, 60), (8, 8, 112, 112), border_radius=18)
    hero = pygame.image.load(ASSETS / "slark.png")
    canvas.blit(hero, hero.get_rect(center=(66, 66)))
    if size >= 128:
        return pygame.transform.scale(canvas, (size, size))          # крупно — чёткие пиксели
    return pygame.transform.smoothscale(canvas, (size, size))        # мелко — сглаживаем, чтобы читалось


def png_bytes(surface):
    buffer = BytesIO()
    pygame.image.save(surface, buffer, "icon.png")
    return buffer.getvalue()


images = [png_bytes(draw_icon(s)) for s in SIZES]
header = struct.pack("<HHH", 0, 1, len(images))
offset = 6 + 16 * len(images)
table = b""
for size, data in zip(SIZES, images):
    side = 0 if size == 256 else size  # 0 в формате .ico означает 256
    table += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(data), offset)
    offset += len(data)
(ASSETS / "icon.ico").write_bytes(header + table + b"".join(images))
print("Иконка готова:", ASSETS / "icon.ico")
