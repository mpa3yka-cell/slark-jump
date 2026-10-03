"""Фоновая музыка: один длинный бесшовный трек music_valley.ogg на все зоны.

Трек создаёт tools/make_music.py. Если звука нет (нет колонок или файла), игра работает молча.
"""
import pygame

from common import ASSETS

VOLUME = 0.5      # музыка тише звуков, чтобы прыжки и взрывы было слышно
FILES = ("music_valley.ogg", "music_valley.wav")   # ogg весит в 13 раз меньше, wav — запасной вариант


class Music:
    def __init__(self):
        self.enabled = True
        self.loaded = False
        self.playing = False
        if not pygame.mixer.get_init():
            return
        for name in FILES:
            try:
                pygame.mixer.music.load(str(ASSETS / name))
            except (pygame.error, FileNotFoundError):
                continue
            pygame.mixer.music.set_volume(VOLUME)
            self.loaded = True
            break

    def play(self, zone=None):
        """Запускает трек, если он ещё не играет; звать можно каждый кадр. Зона не важна — трек один на всех."""
        if self.enabled and self.loaded and not self.playing:
            pygame.mixer.music.play(loops=-1)
            self.playing = True

    def toggle(self):
        """Клавиша M: выключить или снова включить музыку."""
        self.enabled = not self.enabled
        if self.enabled:
            self.play()
        elif self.playing:
            pygame.mixer.music.stop()
            self.playing = False
