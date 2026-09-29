"""Создаёт фоновую музыку для зон: assets/music_valley.wav, music_sunset.wav, music_clouds.wav, music_space.wav.

Звучит как старая приставка Nintendo (NES): два «квадратных» голоса с разной скважностью, 4-битный
треугольник для баса и шумовой канал для ударных. Каждая мелодия — бесшовная петля.

Запуск: .venv\\Scripts\\python.exe tools\\make_music.py
"""
import math
import random
import struct
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


# --- Кровавый закат: светлая, с надеждой, соль мажор ---

def sunset():
    chords = "G D Em C G D Em C C D Bm Em C D G D".split()
    song = Song(bpm=128, bars=len(chords))
    lead = ("B4.2 D5.2 G5.4 F#5.2 G5.2 A5.4   F#5.4 D5.4 A4.8 "
            "G5.2 F#5.2 E5.4 B4.2 E5.2 G5.4   E5.4 D5.2 C5.2 D5.8 "
            "B4.2 D5.2 G5.4 A5.2 B5.2 D6.4    C6.4 B5.2 A5.2 F#5.8 "
            "G5.4 A5.2 B5.2 E5.4 G5.4         A5.6 G5.2 E5.2 D5.6 "
            "E5.4 G5.4 C6.4 B5.4              A5.4 F#5.4 D5.4 A5.4 "
            "B5.6 A5.2 F#5.4 D5.4             G5.4 F#5.4 E5.4 B4.4 "
            "C5.2 E5.2 G5.4 C6.4 B5.2 A5.2    B5.4 A5.4 F#5.4 D5.4 "
            "G5.6 A5.2 B5.4 D6.4              C6.4 B5.4 A5.4 F#5.4")
    song.melody(lead, 0.24, duty=0.5, decay=2.0, sustain=0.6, vibrato=0.15)
    # подголосок на терцию ниже (по ладу соль мажор) на втором голосе
    harmony = [(None if n is None else n - (3 if (n % 12) in (11, 4, 6) else 4), s) for n, s in parse(lead)]
    step = 0
    for note, steps in harmony:
        if note is not None:
            song.pulse(step, steps, note, 0.09, duty=0.25, decay=2.0, sustain=0.5)
        step += steps
    for bar, name in enumerate(chords):
        notes = chord(name)
        root = notes[0] if notes[0] < 55 else notes[0] - 12
        base = bar * 16
        # бас прыгает «корень — квинта» четвертями с проходящей восьмой
        for i, off in enumerate((0, 7, 12, 7)):
            song.triangle(base + i * 4, 3, root - 12 + off, 0.34, gate=0.85)
        song.triangle(base + 14, 2, root - 12 + 4 if notes[1] - notes[0] == 4 else root - 12 + 3, 0.3, gate=0.8)
        # бодрые ударные: бочка на 1 и 3, «малый» из шума на 2 и 4, хэт восьмыми
        for i in (0, 8, 10):
            song.kick(base + i, 0.4)
        for i in (4, 12):
            song.noise(base + i, 0.12, 0.16, rate=6000)
        for i in range(0, 16, 2):
            song.noise(base + i, 0.03, 0.05, rate=15000, short=i % 4 == 2)
    song.write("music_sunset.wav")


# --- Над облаками: тихая и спокойная, фа мажор с лидийским си ---

def clouds():
    chords = "F G Em Am F G C C Dm Em F G F G Em Am".split()
    song = Song(bpm=76, bars=len(chords))
    lead = ("C5.4 F5.4 A5.8     B5.8 A5.4 G5.4     G5.12 E5.4        A5.16 "
            "C6.8 A5.4 F5.4     D6.8 B5.4 G5.4     E6.12 D6.4        C6.16 "
            "A5.4 F5.4 D5.8     B5.4 G5.4 E5.8     C6.4 A5.4 F5.4 A5.4   B5.12 D6.4 "
            "C6.8 A5.8          B5.8 G5.8          E5.8 G5.4 B5.4    A5.16")
    # мягкий голос и эхо — второй голос повторяет мелодию на три шестнадцатых позже и тише
    song.melody(lead, 0.17, echo=(3, 0.4), duty=0.5, gate=0.97, decay=1.2, sustain=0.45, vibrato=0.12)
    for bar, name in enumerate(chords):
        notes = chord(name)
        root = notes[0] if notes[0] < 53 else notes[0] - 12
        third, fifth = root + notes[1] - notes[0], root + 7
        base = bar * 16
        # «арфа» треугольником: неторопливое ломаное трезвучие восьмыми
        for i, note in enumerate((root - 12, fifth - 12, root, third, fifth, third, root, fifth - 12)):
            song.triangle(base + i * 2, 2, note, 0.26, gate=0.9)
        # вместо ударных — едва слышный ветер раз в два такта
        if bar % 2 == 0:
            song.noise(base, 3.0, 0.025, rate=1800, swell=True)
    song.write("music_clouds.wav")


# --- Звёздная бездна: космос, ми минор и далёкие аккорды ---

def space():
    chords = "Em Em C C Am Am B B Em Cm Em Cm Ab Ab B B".split()
    song = Song(bpm=92, bars=len(chords))
    lead = ("B4.8 E5.4 G5.4      F#5.8 E5.4 B4.4     C5.8 E5.4 G5.4     B5.12 G5.4 "
            "A5.8 C6.4 E6.4      D6.8 C6.4 B5.4      D#6.8 F#5.4 A5.4   B5.16 "
            "G5.8 B5.4 E6.4      Eb6.8 D6.4 C6.4     B5.8 G5.4 E5.4     G5.8 Eb5.4 C5.4 "
            "C6.8 Eb6.4 Ab5.4    G5.8 Eb5.4 C5.4     D#5.8 F#5.4 B5.4   A5.4 F#5.4 D#5.8")
    # голос с глубоким вибрато и подъездом к ноте — «инопланетный» звук
    step, previous = 0, None
    for note, steps in parse(lead):
        if note is not None:
            song.pulse(step, steps, note, 0.2, duty=0.25, gate=0.95, decay=1.0, sustain=0.6,
                       vibrato=0.45, slide_from=previous)
            previous = note
        step += steps
    rng = random.Random(7)
    for bar, name in enumerate(chords):
        notes = chord(name)
        root = notes[0] if notes[0] < 52 else notes[0] - 12
        base = bar * 16
        # мерцающее арпеджио вверх-вниз на две октавы — звёзды
        tones = [n + 12 * o for o in (1, 2) for n in notes[:3]]
        arp = tones + tones[-2:0:-1]
        for i in range(16):
            song.pulse(base + i, 1, arp[(bar * 16 + i) % len(arp)], 0.07, duty=0.125, gate=0.6,
                       decay=10, sustain=0.2)
        # низкий гул: длинная нота и её октава
        song.triangle(base, 12, root - 12, 0.32)
        song.triangle(base + 12, 4, root, 0.28, gate=0.9)
        # редкие «сигналы» высоко-высоко и космический шорох
        if bar % 2 == 1:
            song.pulse(base + 14, 1, notes[0] + 48, 0.05, duty=0.5, gate=0.5, decay=12, sustain=0.1)
        song.noise(base + rng.choice((4, 8, 12)), 0.04, 0.035, rate=18000, short=True)
        if bar % 4 == 0:
            song.noise(base, 4.0, 0.03, rate=900, swell=True)
    song.write("music_space.wav")


valley()
sunset()
clouds()
space()
print("Готово:", ASSETS)
