r"""Создаёт фоновую музыку: assets/music_valley.ogg.

Звучит как старая приставка Nintendo (NES): два «квадратных» голоса с разной скважностью, 4-битный
треугольник для баса и шумовой канал для ударных. Мелодия — бесшовная петля.

Запуск: .venv\Scripts\python.exe tools\make_music.py

Сначала пишется .wav, потом (если установлен ffmpeg) он жмётся в .ogg и удаляется — .ogg в 13 раз
легче, а игра одинаково хорошо играет и .ogg, и .wav.
"""
import math
import random
import shutil
import struct
import subprocess
import wave
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"
RATE = 22050

NOTE_INDEX = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6,
              "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}
CHORDS = {"maj": (0, 4, 7), "min": (0, 3, 7), "7": (0, 4, 7, 10)}
# 4-битный треугольник приставки: 32 ступеньки от 15 до 0 и обратно
TRIANGLE = [(15 - i if i < 16 else i - 16) / 7.5 - 1 for i in range(32)]


def midi(name):
    """'C#5' -> номер ноты MIDI."""
    return NOTE_INDEX[name[:-1]] + 12 * (int(name[-1]) + 1)


def freq(note):
    return 440.0 * 2 ** ((note - 69) / 12)


def parse(melody):
    """'D5.4 A4.2 -.2' -> [(нота или None, длительность в шестнадцатых), ...]."""
    result = []
    for token in melody.split():
        name, steps = token.split(".")
        result.append((None if name == "-" else midi(name), int(steps)))
    return result


def chord(name):
    """'Dm' / 'Bb' / 'A7' -> ноты аккорда от корня в 3-й октаве."""
    for suffix, quality in (("m", "min"), ("7", "7")):
        if name.endswith(suffix) and name[:-1] in NOTE_INDEX:
            return [48 + NOTE_INDEX[name[:-1]] + i for i in CHORDS[quality]]
    return [48 + NOTE_INDEX[name] + i for i in CHORDS["maj"]]


class Song:
    def __init__(self, bpm, bars):
        self.step = 60 / bpm / 4                       # длительность шестнадцатой, сек
        self.length = round(bars * 16 * self.step * RATE)
        self.buffer = [0.0] * self.length
        self.noise_state = 1

    def pos(self, step):
        return round(step * self.step * RATE)

    def add(self, start, samples):
        """Добавляет звук в петлю; то, что вылезло за конец, звучит в её начале — стык не слышен."""
        n = self.length
        buf = self.buffer
        for i, s in enumerate(samples):
            buf[(start + i) % n] += s

    # --- голоса ---

    def pulse(self, step, steps, note, volume, duty=0.5, gate=0.9, decay=3.0, sustain=0.55,
              vibrato=0.0, slide_from=None):
        """«Квадратный» голос: огибающая как у приставки — ступеньками по 1/15 громкости."""
        n = int(steps * self.step * RATE * gate)
        release = int(RATE * 0.02)
        f0 = freq(note)
        phase, out = 0.0, []
        for i in range(n + release):
            t = i / RATE
            f = f0
            if slide_from is not None and t < 0.08:
                f = freq(slide_from + (note - slide_from) * t / 0.08)
            if vibrato and t > 0.18:
                f *= 2 ** (vibrato * math.sin(2 * math.pi * 5.5 * t) / 12)
            phase = (phase + f / RATE) % 1.0
            env = sustain + (1 - sustain) * math.exp(-t * decay)
            if i >= n:
                env *= 1 - (i - n) / release
            env = math.floor(env * 15 + 0.5) / 15
            out.append((1.0 if phase < duty else -1.0) * env * volume)
        self.add(self.pos(step), out)

    def triangle(self, step, steps, note, volume, gate=0.95):
        """Треугольник: у приставки у него нет громкости — звучит ровно, потом обрывается."""
        n = int(steps * self.step * RATE * gate)
        f = freq(note)
        phase, out = 0.0, []
        for i in range(n):
            phase = (phase + f / RATE) % 1.0
            fade = min(1.0, (n - i) / 60)             # без щелчка в конце
            out.append(TRIANGLE[int(phase * 32)] * volume * fade)
        self.add(self.pos(step), out)

    def kick(self, step, volume):
        """Бочка из треугольника с быстро падающей высотой — обычный приём в играх NES."""
        n = int(RATE * 0.11)
        phase, out = 0.0, []
        for i in range(n):
            t = i / n
            phase = (phase + (170 - 120 * t) / RATE) % 1.0
            out.append(TRIANGLE[int(phase * 32)] * volume * (1 - t))
        self.add(self.pos(step), out)

    def noise(self, step, length, volume, rate=11000, short=False, swell=False):
        """Шумовой канал: 15-битный сдвиговый регистр, как в приставке (short — «металлический» режим)."""
        n = int(RATE * length)
        out, acc = [], 0.0
        tap = 6 if short else 1
        value = 1.0
        for i in range(n):
            acc += rate / RATE
            while acc >= 1:
                acc -= 1
                bit = (self.noise_state ^ (self.noise_state >> tap)) & 1
                self.noise_state = (self.noise_state >> 1) | (bit << 14)
                value = 1.0 if self.noise_state & 1 else -1.0
            t = i / n
            env = math.sin(math.pi * t) if swell else (1 - t) ** 2
            out.append(value * volume * math.floor(env * 15 + 0.5) / 15)
        self.add(self.pos(step), out)

    # --- партии ---

    def melody(self, text, volume, echo=None, start=0, **kw):
        """Мелодия; echo=(задержка в шестнадцатых, громкость) — эхо вторым голосом, как делали на NES."""
        step = start
        for note, steps in parse(text):
            if note is not None:
                self.pulse(step, steps, note, volume, **kw)
                if echo:
                    self.pulse(step + echo[0], steps, note, volume * echo[1], **kw)
            step += steps

    def write(self, name):
        peak = max(abs(s) for s in self.buffer) or 1.0
        scale = 0.85 / peak
        with wave.open(str(ASSETS / name), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(RATE)
            f.writeframes(b"".join(struct.pack("<h", int(s * scale * 32767)) for s in self.buffer))
        print(f"{name}: {self.length / RATE:.1f} с")
        compress(name)


def compress(name):
    """Жмёт готовый .wav в .ogg (во много раз меньше) и убирает .wav — в репозитории лежит только ogg.
    Если ffmpeg не установлен, wav остаётся как есть: игра умеет играть и из wav."""
    wav, ogg = ASSETS / name, ASSETS / (Path(name).stem + ".ogg")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ffmpeg не найден — оставляю", name)
        return
    before = wav.stat().st_size
    subprocess.run([ffmpeg, "-loglevel", "error", "-i", str(wav), "-c:a", "libvorbis",
                    "-qscale", "5", "-map_metadata", "-1", str(ogg), "-y"], check=True)
    wav.unlink()
    print(f"{ogg.name}: {ogg.stat().st_size / 1048576:.2f} МБ вместо {before / 1048576:.2f} МБ")


# --- Долина замка: мрачная готика, ре минор ---

def valley():
    chords = "Dm Dm Bb Bb Gm Gm A7 A7 Dm C Bb A7 Gm Dm Eb A7".split()
    song = Song(bpm=108, bars=len(chords))
    lead = ("D5.4 A4.2 D5.2 F5.4 E5.2 D5.2   C#5.2 D5.2 E5.4 A4.8 "
            "D5.4 Bb4.2 D5.2 F5.4 G5.2 F5.2  F5.2 E5.2 D5.4 Bb4.8 "
            "G5.4 F5.2 E5.2 D5.4 Bb4.2 G4.2  A4.2 Bb4.2 D5.4 G5.8 "
            "A5.4 G5.2 F5.2 E5.4 C#5.4       A4.2 C#5.2 E5.2 G5.2 A5.8 "
            "F5.6 E5.2 D5.4 A5.4             G5.6 F5.2 E5.4 C5.4 "
            "F5.6 E5.2 D5.4 Bb4.4            C#5.4 E5.4 A5.8 "
            "Bb5.6 A5.2 G5.4 D5.4            A5.6 G5.2 F5.4 D5.4 "
            "Eb5.4 G5.4 Bb5.4 G5.4           C#5.4 E5.4 A4.8")
    song.melody(lead, 0.26, duty=0.25, decay=2.5, sustain=0.5, vibrato=0.25)
    for bar, name in enumerate(chords):
        notes = chord(name)
        root = notes[0] - 12 if notes[0] >= 52 else notes[0]
        base = bar * 16
        # бас качается октавами восьмыми — как в замковых уровнях старых игр
        for i in range(8):
            song.triangle(base + i * 2, 2, root - 12 if i % 2 == 0 else root, 0.34, gate=0.8)
        # «клавесин»: быстрое ломаное арпеджио тихим узким голосом
        arp = [notes[0] + 12, notes[1] + 12, notes[2] + 12, notes[1] + 12]
        for i in range(16):
            song.pulse(base + i, 1, arp[i % 4], 0.08, duty=0.125, gate=0.7, decay=8, sustain=0.3)
        # глухой удар на первую долю, тихий шелест на слабые восьмые
        song.kick(base, 0.35)
        song.kick(base + 8, 0.25)
        for i in (2, 6, 10, 14):
            song.noise(base + i, 0.05, 0.05, rate=14000)
        if bar % 4 == 3:
            song.noise(base + 12, 0.18, 0.09, rate=3500)
    song.write("music_valley.wav")


valley()
print("Готово:", ASSETS)
