"""Общее для всех игр: окно, шрифты, цвета, картинки, звуки и рисование текста."""
import sys
from pathlib import Path

import pygame

WIDTH, HEIGHT = 800, 600
FPS = 60

BG_COLOR = (30, 30, 40)
TEXT_COLOR = (240, 240, 240)
GRAY_COLOR = (160, 160, 175)
GOLD_COLOR = (255, 215, 0)
CARD_COLOR = (50, 55, 75)
CARD_SELECTED_COLOR = (75, 85, 125)

GAME_DIR = Path(__file__).parent
if getattr(sys, "frozen", False):
    # запущено как .exe: картинки и звуки распакованы во временную папку,
    # а рекорды храним рядом с самим .exe, чтобы они не пропадали
    ASSETS = Path(sys._MEIPASS) / "assets"
    DATA_DIR = Path(sys.executable).parent
else:
    ASSETS = GAME_DIR / "assets"
    DATA_DIR = GAME_DIR

pygame.init()
try:
    # SCALED: игра рисуется в 800×600, а окно можно растянуть или включить полный экран (F11) —
    # картинка увеличится видеокартой без потери чёткости
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.SCALED | pygame.RESIZABLE)
except pygame.error:
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Прыжки Сларка")

tiny_font = pygame.font.SysFont("arial", 16, bold=True)
small_font = pygame.font.SysFont("arial", 20)
font = pygame.font.SysFont("arial", 32)
card_font = pygame.font.SysFont("arial", 26, bold=True)
big_font = pygame.font.SysFont("arial", 64)


def load_image(name):
    return pygame.image.load(ASSETS / name).convert_alpha()


def load_sound(name, volume=1.0):
    """Загружает звук. Если звука нет (например, нет колонок), игра всё равно работает."""
    try:
        sound = pygame.mixer.Sound(ASSETS / name)
        sound.set_volume(volume)
        return sound
    except (pygame.error, FileNotFoundError):
        return None


def play(sound):
    if sound:
        sound.play()


def draw_text(text, fnt, y, color=TEXT_COLOR):
    """Рисует текст по центру экрана по горизонтали."""
    surface = fnt.render(text, True, color)
    screen.blit(surface, (WIDTH // 2 - surface.get_width() // 2, y))


def draw_wrapped(text, fnt, color, rect, y):
    """Рисует текст внутри rect по центру, перенося слова. Возвращает y под текстом."""
    lines = []
    line = ""
    for word in text.split():
        test = f"{line} {word}".strip()
        if fnt.size(test)[0] > rect.width - 24 and line:
            lines.append(line)
            line = word
        else:
            line = test
    lines.append(line)
    for line in lines:
        surface = fnt.render(line, True, color)
        screen.blit(surface, (rect.centerx - surface.get_width() // 2, y))
        y += fnt.get_linesize()
    return y


def draw_button(rect, text, is_selected):
    pygame.draw.rect(screen, CARD_SELECTED_COLOR if is_selected else CARD_COLOR, rect, border_radius=12)
    pygame.draw.rect(screen, GOLD_COLOR if is_selected else GRAY_COLOR, rect, 3, border_radius=12)
    surface = font.render(text, True, TEXT_COLOR)
    screen.blit(surface, surface.get_rect(center=rect.center))


def dim_screen(alpha):
    """Затемняет всё, что уже нарисовано (для окон поверх игры)."""
    overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, alpha))
    screen.blit(overlay, (0, 0))
