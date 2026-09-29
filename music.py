"""Фоновая музыка: у каждой зоны своя 8-битная мелодия, на границе зон они плавно сменяют друг друга.

Мелодии создаёт tools/make_music.py. Если звука нет (нет колонок или файлов), игра работает молча.
"""
import pygame

from common import ASSETS

VOLUME = 0.45     # музыка тише звуков, чтобы прыжки и взрывы было слышно
FADE_MS = 1500    # за сколько старая мелодия затихает, а новая набирает громкость
TRACKS = ("valley", "sunset", "clouds", "space")   # id зон из jump_background.BIOMES


class Music:
    def __init__(self):
        self.enabled = True
        self.current = None     # какая мелодия должна звучать
        self.tracks = {}
        self.channels = []
        self.active = 0         # на каком из двух каналов играет текущая мелодия
        if not pygame.mixer.get_init():
            return
        # два отдельных канала только для музыки: пока один затихает, другой уже играет,
        # а звукам игры остаются остальные
        pygame.mixer.set_num_channels(max(pygame.mixer.get_num_channels(), 10))
        pygame.mixer.set_reserved(2)
        self.channels = [pygame.mixer.Channel(0), pygame.mixer.Channel(1)]
        for name in TRACKS:
            try:
                sound = pygame.mixer.Sound(ASSETS / f"music_{name}.wav")
            except (pygame.error, FileNotFoundError):
                continue
            sound.set_volume(VOLUME)
            self.tracks[name] = sound

    def play(self, name):
        """Включает мелодию зоны; если она уже играет — ничего не делает, так что звать можно каждый кадр."""
        if name != self.current:
            self.current = name
            self._start()

    def toggle(self):
        """Клавиша M: выключить или снова включить музыку."""
        self.enabled = not self.enabled
        if self.enabled:
            self._start()
        else:
            for channel in self.channels:
                channel.stop()

    def _start(self):
        if not self.enabled or not self.channels:
            return
        self.channels[self.active].fadeout(FADE_MS)
        sound = self.tracks.get(self.current)
        if sound:
            self.active = 1 - self.active
            self.channels[self.active].play(sound, loops=-1, fade_ms=FADE_MS)
