"""Фоновая музыка: одна мелодия music_valley.ogg для всех зон."""
import pygame
from pathlib import Path

ASSETS = Path(__file__).resolve().parent / "assets"
FILES = ("music_valley.ogg", "music_valley.wav")   # ogg весит в 13 раз меньше, wav — запасной вариант


class Music:
    def __init__(self):
        self.enabled = False
        self._load()

    def _load(self):
        for name in FILES:
            path = ASSETS / name
            if path.exists():
                pygame.mixer.music.load(str(path))
                pygame.mixer.music.set_volume(0.5)
                return

    def toggle(self):
        """Включить/выключить музыку."""
        self.enabled = not self.enabled
        if self.enabled:
            pygame.mixer.music.play(loops=-1)
        else:
            pygame.mixer.music.stop()

    def play(self, zone):
        """Для совместимости с оригинальным интерфейсом — зона игнорируется,
        так как используется одна мелодия для всех зон."""
        pass
