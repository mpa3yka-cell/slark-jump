"""Создаёт звуки, которых не было в игровой платформе: assets/throw.wav (свист брошенного кинжала).

Запуск: .venv\\Scripts\\python.exe tools\\make_sounds.py
"""
import math
import random
import struct
import wave
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "assets"
RATE = 22050


def save(name, samples):
    with wave.open(str(ASSETS / name), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, s)) * 32767)) for s in samples))


def throw_sound():
    """Свист: шум, который становится выше и затихает, плюс лёгкий металлический «дзынь»."""
    rng = random.Random(3)
    n = int(RATE * 0.22)
    samples, low = [], 0.0
    for i in range(n):
        t = i / n
        smooth = 0.25 + 0.6 * t                # чем дальше, тем «светлее» шум
        low = low * (1 - smooth) + rng.uniform(-1, 1) * smooth
        envelope = min(1.0, t * 12) * (1 - t) ** 1.5
        ring = math.sin(2 * math.pi * 2400 * i / RATE) * max(0.0, 0.25 - t) * 0.6
        samples.append((low * 0.55 + ring) * envelope)
    save("throw.wav", samples)


throw_sound()
print("Готово:", ASSETS / "throw.wav")
