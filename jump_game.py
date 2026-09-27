"""Игра «Прыжки Сларка»: прыгайте по платформам всё выше.

Уровень собирается из «структур»: лестниц, мостов с крипами, цепочек движущихся платформ,
лифтов, исчезающих платформ, батутов и минных полей. Чем выше — тем сложнее.
Графика — в jump_art.py, фон и погода — в jump_background.py, сетевая дуэль — в duel.py.

Для дуэли важно, чтобы у обоих игроков был одинаковый мир:
- уровень строится своим генератором случайных чисел self.rng с общим «зерном» (seed);
- всё, что движется, считается по формуле от времени self.t, а не «шаг за шагом».
"""
import math
import random

import pygame

from common import WIDTH, HEIGHT, TEXT_COLOR, GRAY_COLOR, GOLD_COLOR, screen, small_font, font, load_sound, play
import jump_art
import pixel_art as px
from jump_art import CREEP_W, CREEP_H, FAMILIAR_W, FAMILIAR_H, MINE_W, MINE_H, FRAMES
from jump_background import Background, BIOMES, biome_index, PIXELS_PER_METER

# --- Настройки ---
GRAVITY = 0.45
JUMP_SPEED = -12.5       # обычный прыжок (поднимает примерно на 170 пикселей)
SPRING_SPEED = -21       # пружина и батут
STOMP_SPEED = -11        # подскок после прыжка на врага
ROCKET_SPEED = -15       # скорость полёта на ракете
ROCKET_TIME = 150        # сколько кадров летит ракета (60 кадров = 1 секунда)
SHADOW_TIME = 360        # сколько кадров длится «Теневой танец»
MOVE_SPEED = 6.5
CAMERA_LINE = HEIGHT * 0.4  # если герой выше этой линии, камера едет вверх
DEATH_FRAMES = 55        # сколько кадров показываем взрыв перед концом игры
DAGGER_SPEED = -16       # кинжал летит вверх быстрее, чем Сларк прыгает
DAGGER_COOLDOWN = 21     # кадров между бросками (0,35 секунды)
MAX_DAGGERS = 3          # сколько кинжалов может быть в воздухе одновременно
THROW_KEYS = (pygame.K_UP, pygame.K_w, pygame.K_SPACE)

PLAYER_W, PLAYER_H = 22, 42   # хитбокс героя (картинка больше: хвост, плавник, шипы капюшона)
BRIDGE_WIDTHS = (200, 220, 240)  # ширина мостов — из готового набора, чтобы картинки делались заранее
PLATFORM_W, PLATFORM_H = 90, 16
MIN_GAP, MAX_GAP = 55, 145    # расстояние между платформами по высоте (MAX_GAP < высоты прыжка)
MAX_DX = 250                  # насколько следующая платформа может быть в стороне
SPRING_GAP = 380              # после батута следующая платформа может быть так высоко
SAFE_HEIGHT = 40              # первые метры без врагов
VANISH_FRAMES = 20            # за сколько кадров растворяется исчезающая платформа

SHADOW_COLOR = (170, 100, 255)
ROCKET_COLOR = (180, 110, 230)     # цвет «Крыльев тьмы» на шкале времени

art = jump_art.Art()
BONUS_IMAGES = {"spring": art.spring[0], "rocket": art.rocket, "shadow": art.shadow_orb[0]}

jump_sound = load_sound("jump.wav")
spring_sound = load_sound("spring.wav")
rocket_sound = load_sound("rocket.wav", volume=0.6)
shadow_sound = load_sound("shadow.wav")
boom_sound = load_sound("boom.wav")
stomp_sound = load_sound("catch.wav", volume=0.5)
crack_sound = load_sound("boom.wav", volume=0.2)
thunder_sound = load_sound("boom.wav", volume=0.35)
throw_sound = load_sound("throw.wav", volume=0.6)
mine_boom_sound = load_sound("boom.wav", volume=0.5)


def clamp(value, low, high):
    return max(low, min(high, value))


def back_and_forth(distance, span):
    """Где окажется то, что ездит туда-обратно по отрезку [0, span], пройдя путь distance.
    Возвращает (позиция, направление: 1 — вперёд, -1 — назад)."""
    if span <= 0:
        return 0.0, 1
    m = distance % (2 * span)
    return (m, 1) if m <= span else (2 * span - m, -1)


class JumpGame:
    def __init__(self, player_name, best, seed=None, view_extra=0):
        self.player_name = player_name
        self.best = best  # лучшая высота из таблицы рекордов
        # генератор только для построения уровня: у двух игроков с одним seed уровень одинаковый
        self.rng = random.Random(seed)
        self.t = 0              # время с начала попытки, в кадрах
        self.next_id = 0        # у каждой платформы и врага свой номер — по нему сообщаем о событиях
        self.events = []        # что произошло за кадр (для отправки сопернику)
        # позиция хитбокса героя хранится в дробных числах — так движение плавнее
        self.x = WIDTH / 2 - PLAYER_W / 2
        self.y = HEIGHT - 160.0
        self.vx = 0.0
        self.vy = JUMP_SPEED
        self.facing_left = False
        self.climbed = 0        # сколько пикселей проехала камера вверх
        self.rocket_timer = 0
        self.shadow_timer = 0
        self.platforms = []
        self.enemies = []
        self.particles = []
        self.trail = []         # теневые следы «Теневого танца»
        self.popups = []        # надписи «100 м!»
        self.hint_timer = 300   # подсказка про кинжал внизу экрана в начале игры (5 секунд)
        self.daggers = []       # брошенные кинжалы: {"x", "y", "visual"} (visual — кинжал соперника в дуэли)
        self.dagger_cooldown = 0
        self.next_milestone = 100
        self.anim = 0.0
        self.squash = 0.0       # сплющивание при приземлении (1 — сильно, 0 — нет)
        self.shake = 0
        self.dying = 0
        self.over = False
        # view_extra — насколько выше обычного экрана видно (в дуэли каждая половина экрана выше)
        self.view_extra = view_extra
        self.background = Background(lookahead=view_extra)
        self.canvas = pygame.Surface((WIDTH, HEIGHT + view_extra))

        # первая платформа прямо под героем
        self.top_y = HEIGHT - 60      # высота самой верхней платформы основного пути
        self.last_x = WIDTH / 2 - PLATFORM_W / 2
        self.add_platform(self.last_x, self.top_y, "normal")
        self.generate()

    # --- для платформы ---

    @property
    def height_m(self):
        return int(self.climbed / PIXELS_PER_METER)

    def record(self):
        return {"score": self.height_m}

    def summary(self):
        return f"Высота: {self.height_m} м"

    # --- создание уровня ---

    def new_id(self):
        self.next_id += 1
        return self.next_id

    def height_at(self, y):
        """На какой высоте (в метрах) окажется точка экрана с координатой y."""
        return (self.climbed + HEIGHT - y) / PIXELS_PER_METER

    def add_platform(self, x, y, kind="normal", width=PLATFORM_W, bonus=None, move_range=0):
        rng = self.rng
        biome = BIOMES[biome_index(self.height_at(y))]["id"]
        min_x, max_x = 0, WIDTH - width
        if kind == "moving" and move_range:
            min_x, max_x = max(0, x - move_range), min(WIDTH - width, x + move_range)
        span = max_x - min_x
        direction = rng.choice((-1, 1))
        platform = {
            "id": self.new_id(),
            "rect": pygame.Rect(int(x), int(y), width, PLATFORM_H),
            "kind": kind,  # normal, moving, elevator, breaking, vanishing, trampoline
            "image": art.platform(kind, biome, width),
            # движущиеся: ездят между min_x и max_x; start — где на этом пути они в момент t = 0
            "min_x": min_x, "max_x": max_x, "speed": rng.uniform(1.5, 2.5),
            "start": (x - min_x) if direction > 0 else 2 * span - (x - min_x),
            # лифты: base_y — середина хода, range — насколько отъезжают вверх и вниз
            "base_y": float(y), "phase": rng.uniform(0, math.tau), "range": move_range,
            "prev_top": int(y),
            "broken": False, "break_t": 0, "fade": 0,
            "bonus": bonus, "bonus_x": rng.randint(8, width - 38), "spring_timer": 0,
        }
        self.platforms.append(platform)
        return platform

    def place_next(self, gap, dx_max=MAX_DX, width=PLATFORM_W):
        """Место для следующей платформы основного пути: до неё всегда можно допрыгнуть,
        и над ней нет мины."""
        y = self.top_y - gap
        mines = [e for e in self.enemies if e["kind"] == "mine" and y - 60 < e["rect"].centery < self.top_y + 60]
        for _ in range(15):
            x = clamp(self.last_x + self.rng.randint(-dx_max, dx_max), 0, WIDTH - width)
            if all(abs(x + width / 2 - m["rect"].centerx) > 130 for m in mines):
                break
        return x, y

    def add_path(self, x, y, kind="normal", width=PLATFORM_W, bonus=None, move_range=0):
        platform = self.add_platform(x, y, kind, width, bonus, move_range)
        self.top_y = y
        self.last_x = x
        return platform

    def max_gap(self, d):
        return int(MIN_GAP + 20 + (MAX_GAP - MIN_GAP - 20) * d)

    def random_bonus(self):
        roll = self.rng.random()
        return "spring" if roll < 0.05 else "rocket" if roll < 0.07 else "shadow" if roll < 0.09 else None

    def generate(self):
        """Достраивает уровень вверх структурами, пока он не заполнит экран с запасом."""
        first_new = len(self.platforms)
        self.build_patterns()
        for p in self.platforms[first_new:]:
            self.place_platform(p)  # новые движущиеся платформы сразу на своё место

    def build_patterns(self):
        while self.top_y > -HEIGHT:
            h = self.height_at(self.top_y)
            d = min(h / 1000, 1)  # сложность от 0 до 1
            if h < 15:
                self.pattern_single(d)
                continue
            danger = 1 if h > SAFE_HEIGHT else 0
            patterns = [
                (self.pattern_single, 5),
                (self.pattern_staircase, 2),
                (self.pattern_trampoline, 0.8),
                (self.pattern_moving_chain, 0.4 + 2 * d),
                (self.pattern_elevator, 0.3 + 1.5 * d),
                (self.pattern_vanishing, 0.3 + 1.5 * d),
                (self.pattern_bridge, 1.5 * danger),
                (self.pattern_minefield, (0.4 + 2 * d) * danger),
                (self.pattern_familiar, (0.4 + 1.5 * d) * danger),
            ]
            functions, weights = zip(*patterns)
            self.rng.choices(functions, weights)[0](d)

    # --- структуры ---

    def pattern_single(self, d):
        """Одна платформа, иногда движущаяся, иногда с бонусом и обманкой рядом."""
        rng = self.rng
        x, y = self.place_next(rng.randint(MIN_GAP, self.max_gap(d)))
        kind = "moving" if rng.random() < 0.1 + 0.3 * d else "normal"
        self.add_path(x, y, kind, bonus=self.random_bonus())
        if rng.random() < 0.15 + 0.2 * d:
            fake_x = (x + rng.randint(200, WIDTH - 200)) % (WIDTH - PLATFORM_W)
            self.add_platform(fake_x, y + rng.randint(-25, 25), "breaking")

    def pattern_staircase(self, d):
        """Лестница: несколько платформ подряд, шагающих в одну сторону."""
        rng = self.rng
        direction = rng.choice((-1, 1))
        steps = rng.randint(4, 6)
        for i in range(steps):
            x = self.last_x + direction * rng.randint(90, 150)
            if not 0 <= x <= WIDTH - PLATFORM_W:
                direction = -direction
                x = self.last_x + direction * rng.randint(90, 150)
            x = clamp(x, 0, WIDTH - PLATFORM_W)
            # последняя ступенька всегда обычная — с неё можно прыгать сколько угодно
            kind = "vanishing" if i < steps - 1 and rng.random() < 0.25 * d else "normal"
            self.add_path(x, self.top_y - rng.randint(60, 95), kind)

    def pattern_bridge(self, d):
        """Широкий мост, по которому ходит крип. Прыгните на него сверху!"""
        width = self.rng.choice(BRIDGE_WIDTHS)
        x, y = self.place_next(self.rng.randint(70, 115), dx_max=150, width=width)
        bridge = self.add_path(x, y, "normal", width=width)
        self.add_creep(bridge, d)

    def pattern_moving_chain(self, d):
        """Цепочка платформ, которые ездят навстречу друг другу."""
        rng = self.rng
        speed = rng.uniform(1.5, 2.2 + d)
        direction = rng.choice((-1, 1))
        for _ in range(rng.randint(3, 4)):
            x, y = self.place_next(rng.randint(70, 110), dx_max=160)
            platform = self.add_path(x, y, "moving", move_range=rng.randint(90, 150))
            span = platform["max_x"] - platform["min_x"]
            offset = x - platform["min_x"]
            platform["speed"] = speed
            platform["start"] = offset if direction > 0 else 2 * span - offset
            direction = -direction

    def pattern_elevator(self, d):
        """Лифт: платформа ездит вверх-вниз. Следующая платформа — над его верхней точкой."""
        rng = self.rng
        amplitude = rng.randint(50, 80)
        x, _ = self.place_next(0, dx_max=180)
        lowest = self.top_y - rng.randint(70, MAX_GAP - 10)
        center = lowest - amplitude
        self.add_platform(x, center, "elevator", move_range=amplitude)
        self.last_x = x
        self.top_y = center - amplitude + 15  # от верхней точки — с небольшим запасом

    def pattern_vanishing(self, d):
        """Исчезающие платформы: на каждую можно прыгнуть только один раз."""
        rng = self.rng
        for _ in range(rng.randint(3, 5)):
            x, y = self.place_next(rng.randint(60, 100), dx_max=180)
            self.add_path(x, y, "vanishing")
        # в конце — обычная платформа: после неё может быть лифт, которого нужно дождаться
        x, y = self.place_next(rng.randint(60, 100), dx_max=180)
        self.add_path(x, y, "normal")

    def pattern_trampoline(self, d):
        """Батут подбрасывает очень высоко, а по пути могут висеть мины."""
        rng = self.rng
        x, y = self.place_next(rng.randint(60, 110), dx_max=180)
        self.add_path(x, y, "trampoline")
        big_gap = rng.randint(260, SPRING_GAP)
        if self.height_at(y) > SAFE_HEIGHT:
            center = x + PLATFORM_W / 2
            for _ in range(rng.randint(1, 3)):
                side = rng.choice((-1, 1))
                mx = center + side * rng.randint(170, 320)
                if not 25 <= mx <= WIDTH - 25:
                    mx = center - side * rng.randint(170, 320)
                self.add_mine(clamp(mx, 25, WIDTH - 25), y - rng.randint(80, big_gap - 40))
        x2, y2 = self.place_next(big_gap, dx_max=200)
        self.add_path(x2, y2, "normal", bonus=self.random_bonus())

    def pattern_minefield(self, d):
        """Несколько платформ, а сбоку от каждой — мина."""
        rng = self.rng
        for _ in range(3):
            x, y = self.place_next(rng.randint(70, self.max_gap(d)))
            self.add_path(x, y, "normal")
            center = x + PLATFORM_W / 2
            side = rng.choice((-1, 1))
            mx = center + side * rng.randint(170, 300)
            if not 25 <= mx <= WIDTH - 25:
                mx = center - side * rng.randint(170, 300)
            self.add_mine(clamp(mx, 25, WIDTH - 25), y - rng.randint(60, 110))

    def pattern_familiar(self, d):
        """Обычная платформа, а над ней пролетает горгулья."""
        self.pattern_single(d)
        self.add_familiar(self.top_y - self.rng.randint(50, 100), d)

    # --- враги ---

    def add_creep(self, platform, d):
        rng = self.rng
        limit = platform["rect"].width - CREEP_W
        self.enemies.append({
            "id": self.new_id(), "kind": "creep", "platform": platform,
            "start": rng.uniform(0, 2 * limit), "speed": rng.uniform(0.6, 0.9 + 0.7 * d),
            "offset": 0.0, "dir": 1, "anim": 0.0,
            # хитбокс — только тело крипа, без щита и дубинки
            "rect": pygame.Rect(0, 0, CREEP_W - 24, CREEP_H - 14),
        })
        self.place_enemy(self.enemies[-1])

    def add_mine(self, x, y):
        rect = pygame.Rect(0, 0, MINE_W - 14, MINE_H - 14)
        rect.center = (int(x), int(y))
        self.enemies.append({"id": self.new_id(), "kind": "mine", "rect": rect,
                             "phase": self.rng.uniform(0, 3), "anim": 0.0})

    def add_familiar(self, y, d):
        rng = self.rng
        self.enemies.append({
            "id": self.new_id(), "kind": "familiar",
            "start": rng.uniform(0, 2 * (WIDTH - 60)), "speed": rng.uniform(1.5, 2.5 + 1.5 * d),
            "phase": rng.uniform(0, math.tau), "base_y": float(y), "dir": 1, "anim": 0.0,
            "rect": pygame.Rect(0, 0, FAMILIAR_W - 26, FAMILIAR_H - 22),
        })
        self.place_enemy(self.enemies[-1])

    def update_enemies(self):
        for e in self.enemies[:]:
            if e["kind"] == "creep" and e["platform"] not in self.platforms:
                self.enemies.remove(e)
                continue
            self.place_enemy(e)

    def place_enemy(self, e):
        """Ставит врага туда, где он в момент self.t (вызывается и сразу при создании —
        иначе новый враг на кадр появлялся бы в левом верхнем углу)."""
        t = self.t
        if e["kind"] == "creep":
            platform = e["platform"]
            e["offset"], e["dir"] = back_and_forth(e["start"] + t * e["speed"], platform["rect"].width - CREEP_W)
            e["anim"] = t * 0.12 * e["speed"]
            e["rect"].midbottom = (platform["rect"].x + e["offset"] + CREEP_W / 2, platform["rect"].top)
        elif e["kind"] == "familiar":
            pos, e["dir"] = back_and_forth(e["start"] + t * e["speed"], WIDTH - 60)
            e["anim"] = e["phase"] + t * 0.18
            e["rect"].center = (int(30 + pos), math.floor(e["base_y"] + math.sin(e["phase"] + t * 0.126) * 10))
        else:
            e["anim"] = e["phase"] + t / 60

    def kill_enemy(self, enemy):
        self.enemies.remove(enemy)
        self.events.append(("kill", enemy["id"]))
        colors = {"creep": [(170, 60, 45), (120, 115, 130), (230, 220, 200)],
                  "familiar": [(110, 120, 140), (150, 160, 180), (80, 85, 100)],
                  "mine": [(255, 170, 40), (255, 80, 40), (120, 110, 100)]}[enemy["kind"]]
        self.burst(enemy["rect"].centerx, enemy["rect"].centery, colors, 24, 5)

    # --- эффекты (здесь обычный random: искры и дым у игроков могут отличаться) ---

    def burst(self, x, y, colors, count, speed, gravity=0.15):
        for _ in range(count):
            angle = random.uniform(0, math.tau)
            s = random.uniform(1, speed)
            life = random.randint(20, 45)
            self.particles.append({"x": x, "y": y, "vx": math.cos(angle) * s, "vy": math.sin(angle) * s,
                                   "life": life, "max": life, "color": random.choice(colors),
                                   "size": random.uniform(2, 5), "gravity": gravity})

    def dust(self, x, y):
        for side in (-1, 1):
            for _ in range(4):
                life = random.randint(12, 22)
                self.particles.append({"x": x + side * 8, "y": y, "vx": side * random.uniform(0.5, 2.5),
                                       "vy": random.uniform(-1.2, -0.2), "life": life, "max": life,
                                       "color": (215, 215, 230), "size": random.uniform(2, 3.5), "gravity": 0.03})

    def smoke(self):
        """Шлейф «Крыльев тьмы»: фиолетовые искры сыплются вниз."""
        player = self.player_rect()
        life = random.randint(20, 35)
        self.particles.append({"x": player.centerx + random.uniform(-10, 10), "y": player.bottom,
                               "vx": random.uniform(-0.6, 0.6), "vy": random.uniform(1, 3), "life": life,
                               "max": life, "color": random.choice([(160, 90, 200), (206, 146, 236), (82, 34, 112)]),
                               "size": random.uniform(3, 6), "gravity": 0})

    def update_particles(self):
        for p in self.particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["vy"] += p["gravity"]
            p["vx"] *= 0.97
            p["life"] -= 1
        self.particles = [p for p in self.particles if p["life"] > 0]
        for t in self.trail:
            t["life"] -= 1
        self.trail = [t for t in self.trail if t["life"] > 0]
        for popup in self.popups:
            popup["life"] -= 1
        self.popups = [p for p in self.popups if p["life"] > 0]

    def update_effects(self):
        """Дым ракеты и теневые следы — и у своего Сларка, и у Сларка соперника."""
        if self.rocket_timer > 0 and self.t % 2 == 0:
            self.smoke()
        if self.shadow_timer > 0 and self.t % 3 == 0:
            self.trail.append({"frame": self.hero_frame(), "x": self.x, "y": self.y, "life": 15})

    def die(self, sound=True):
        self.dying = DEATH_FRAMES
        self.shake = 14
        if sound:
            play(boom_sound)
        center = self.player_rect().center
        self.burst(*center, [(255, 220, 90), (255, 140, 40), (90, 80, 160), (40, 175, 195)], 50, 7, gravity=0.08)

    # --- игровой цикл ---

    def handle_event(self, event):
        """Бег — через зажатые клавиши в update(), а бросок кинжала — по нажатию."""
        if event.type == pygame.KEYDOWN and event.key in THROW_KEYS:
            self.throw_dagger()

    # --- кинжалы ---

    def throw_dagger(self):
        if self.over or self.dying or self.dagger_cooldown > 0 or len(self.daggers) >= MAX_DAGGERS:
            return
        player = self.player_rect()
        x, y = player.centerx, player.top - 6
        self.daggers.append({"x": x, "y": float(y), "visual": False})
        self.dagger_cooldown = DAGGER_COOLDOWN
        self.events.append(("dagger", [x, y, self.climbed]))  # сопернику — чтобы он увидел бросок
        self.squash = max(self.squash, 0.3)                       # маленькая «отдача»
        play(throw_sound)

    def update_daggers(self):
        if self.dagger_cooldown > 0:
            self.dagger_cooldown -= 1
        for d in self.daggers[:]:
            d["y"] += DAGGER_SPEED
            if d["y"] < -HEIGHT:  # улетел далеко вверх
                self.daggers.remove(d)
                continue
            if d["visual"]:
                continue  # кинжал соперника только рисуем: кого он убил, соперник сообщит сам
            blade = pygame.Rect(d["x"] - 4, int(d["y"]), 8, 26)
            for e in self.enemies:
                if blade.colliderect(e["rect"]):
                    self.kill_enemy(e)
                    play(mine_boom_sound if e["kind"] == "mine" else stomp_sound)
                    if e["kind"] == "mine":
                        self.shake = max(self.shake, 5)
                    self.daggers.remove(d)
                    break

    def player_rect(self):
        return pygame.Rect(int(self.x), int(self.y), PLAYER_W, PLAYER_H)

    def bonus_rect(self, platform):
        image = BONUS_IMAGES[platform["bonus"]]
        rect = platform["rect"]
        return image.get_rect(x=rect.x + platform["bonus_x"], bottom=rect.top + 2)

    def invulnerable(self):
        return self.rocket_timer > 0 or self.shadow_timer > 0

    def update(self):
        self.anim += 1 / 60
        self.background.update(self.climbed)
        if self.background.thunder:
            play(thunder_sound)
        self.update_particles()
        self.shake = max(0, self.shake - 1)
        if self.over:
            return
        self.t += 1
        self.hint_timer = max(0, self.hint_timer - 1)
        self.update_daggers()
        if self.dying:
            # пока идёт взрыв, мир продолжает двигаться
            self.update_platforms()
            self.update_enemies()
            self.dying -= 1
            if self.dying == 0:
                self.over = True
            return

        # движение влево-вправо (плавный разгон)
        keys = pygame.key.get_pressed()
        target = 0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            target -= MOVE_SPEED
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            target += MOVE_SPEED
        self.vx += (target - self.vx) * 0.25
        if abs(self.vx) > 0.5:
            self.facing_left = self.vx < 0
        self.x += self.vx
        # ушёл за левый край — появляется справа, и наоборот
        center = self.x + PLAYER_W / 2
        if center < 0:
            self.x += WIDTH
        elif center > WIDTH:
            self.x -= WIDTH

        # движение вверх-вниз
        old_bottom = self.y + PLAYER_H
        if self.rocket_timer > 0:
            self.rocket_timer -= 1
            self.vy = ROCKET_SPEED
            if self.rocket_timer == 0:
                self.vy = -6  # после ракеты ещё немного летим вверх
        else:
            self.vy += GRAVITY
        self.y += self.vy
        if self.shadow_timer > 0:
            self.shadow_timer -= 1
        self.squash *= 0.82
        self.update_effects()

        self.update_platforms()
        self.update_enemies()
        if self.vy > 0 and self.rocket_timer == 0:
            self.check_landing(old_bottom)
        self.check_pickups()
        self.check_enemies(old_bottom)
        self.move_camera()

        if self.height_m >= self.next_milestone:
            self.popups.append({"text": f"{self.next_milestone} м!", "life": 90})
            self.next_milestone += 100

        # упал вниз за экран
        if self.y > HEIGHT + 40 and not self.dying:
            self.over = True
            play(boom_sound)

    def place_platform(self, p):
        """Ставит движущуюся платформу или лифт туда, где они в момент self.t."""
        if p["kind"] == "moving":
            pos, _ = back_and_forth(p["start"] + self.t * p["speed"], p["max_x"] - p["min_x"])
            p["rect"].x = int(p["min_x"] + pos)
        elif p["kind"] == "elevator":
            # floor, а не int: int округляет отрицательные числа «не в ту сторону», и у соперника
            # лифт мог бы оказаться на пиксель в другом месте
            p["rect"].y = math.floor(p["base_y"] + math.sin(p["phase"] + self.t * 0.025) * p["range"])

    def update_platforms(self):
        for p in self.platforms:
            rect = p["rect"]
            p["prev_top"] = rect.top
            if p["broken"]:
                p["break_t"] += 1
                if p["break_t"] > 0:  # у зеркала отсчёт начинается с -1 (см. apply_event)
                    rect.y += 2 + p["break_t"] * 0.35
                continue
            self.place_platform(p)
            if p["fade"]:
                p["fade"] += 1
            if p["spring_timer"]:
                p["spring_timer"] -= 1
        # int(): у зеркала растворение идёт с добавкой 0.001 (см. apply_event) — сравниваем по целой части
        self.platforms = [p for p in self.platforms
                          if int(p["fade"]) <= VANISH_FRAMES and p["rect"].top < HEIGHT + 60]

    def check_landing(self, old_bottom):
        player = self.player_rect()
        feet_left, feet_right = player.left + 3, player.right - 3
        for p in self.platforms:
            rect = p["rect"]
            if p["broken"] or p["fade"]:
                continue
            # ноги были над платформой в прошлом кадре, а теперь дошли до неё
            if not (old_bottom <= p["prev_top"] + 2 and rect.top <= player.bottom):
                continue
            if feet_right < rect.left or feet_left > rect.right:
                continue
            if p["kind"] == "breaking":
                self.break_platform(p)  # не отталкивает — просто ломается
                play(crack_sound)
                self.events.append(("break", p["id"]))
                continue
            self.y = rect.top - PLAYER_H
            if p["kind"] == "trampoline":
                self.vy = SPRING_SPEED
                play(spring_sound)
            elif p["bonus"] == "spring" and player.colliderect(self.bonus_rect(p).inflate(10, 10)):
                self.vy = SPRING_SPEED
                p["spring_timer"] = 12
                self.events.append(("spring", p["id"]))
                play(spring_sound)
            else:
                self.vy = JUMP_SPEED
                play(jump_sound)
            if p["kind"] == "vanishing":
                p["fade"] = 1
                self.events.append(("vanish", p["id"]))
            self.squash = 1.0
            self.dust(player.centerx, rect.top)
            return

    def break_platform(self, platform):
        platform["broken"] = True
        rect = platform["rect"]
        self.burst(rect.centerx, rect.centery, [(135, 92, 58), (165, 118, 75)], 10, 3)

    def check_pickups(self):
        player = self.player_rect()
        for p in self.platforms:
            if p["bonus"] in ("rocket", "shadow") and player.colliderect(self.bonus_rect(p)):
                if p["bonus"] == "rocket":
                    self.rocket_timer = ROCKET_TIME
                    play(rocket_sound)
                else:
                    self.shadow_timer = SHADOW_TIME
                    play(shadow_sound)
                self.pick_bonus(p)
                self.events.append(("pickup", p["id"]))

    def pick_bonus(self, platform):
        self.burst(*self.bonus_rect(platform).center, [(255, 255, 200), (200, 160, 255)], 16, 4, gravity=0)
        platform["bonus"] = None

    def check_enemies(self, old_bottom):
        hitbox = self.player_rect().inflate(-6, -6)  # чуть меньше — чтобы касания были честными
        for e in self.enemies[:]:
            if not hitbox.colliderect(e["rect"]):
                continue
            if self.invulnerable():
                self.kill_enemy(e)  # Сларк проходит сквозь врага и уничтожает его
            elif e["kind"] != "mine" and self.vy > 0 and old_bottom <= e["rect"].top + 14:
                # прыжок сверху на крипа или горгулью
                self.kill_enemy(e)
                self.vy = STOMP_SPEED
                self.squash = 1.0
                play(stomp_sound)
            else:
                self.die()
                return

    def move_camera(self):
        shift = int(CAMERA_LINE - self.y)  # целое число, чтобы всё сдвигалось одинаково
        if shift > 0:
            self.shift_world(shift)

    def shift_world(self, shift):
        """Камера поднялась на shift пикселей: всё на экране съезжает вниз, сверху достраиваем уровень."""
        self.y += shift
        self.climbed += shift
        self.top_y += shift
        for p in self.platforms:
            p["rect"].y += shift
            p["base_y"] += shift
            p["prev_top"] += shift
        for e in self.enemies:
            e["rect"].y += shift  # и крипы тоже — иначе на кадр отстают от своего моста
            if e["kind"] == "familiar":
                e["base_y"] += shift
        for p in self.particles:
            p["y"] += shift
        for t in self.trail:
            t["y"] += shift
        for d in self.daggers:
            d["y"] += shift
        self.enemies = [e for e in self.enemies if e["rect"].top < HEIGHT + 60]
        self.generate()

    # --- сетевая дуэль: состояние своего Сларка и «зеркало» соперника ---

    def state_message(self):
        """Всё, что нужно сопернику, чтобы нарисовать нашего Сларка."""
        return {"t": self.t, "climbed": self.climbed, "x": round(self.x, 1), "y": round(self.y, 1),
                "vy": round(self.vy, 2), "left": self.facing_left, "rocket": self.rocket_timer,
                "shadow": self.shadow_timer, "dying": self.dying, "squash": round(self.squash, 2),
                "over": self.over}

    def apply_remote(self, state):
        """Зеркало: ставим Сларка туда, где он у соперника, и двигаем камеру так же."""
        shift = int(state["climbed"] - self.climbed)
        if shift > 0:
            self.shift_world(shift)
        self.t = state["t"] - 1  # update_mirror прибавит 1 — мир окажется ровно в момент сообщения
        self.x, self.y, self.vy = state["x"], state["y"], state["vy"]
        self.facing_left = state["left"]
        self.rocket_timer, self.shadow_timer = state["rocket"], state["shadow"]
        self.squash = state["squash"]
        if state["dying"] and not self.dying:
            self.die(sound=False)
        self.dying = state["dying"]
        self.over = state["over"]

    def apply_event(self, kind, object_id):
        """Зеркало: у соперника что-то сломалось, исчезло или было сбито — повторяем у себя."""
        if kind == "dagger":
            # соперник бросил кинжал; если наша камера ещё не догнала его камеру — поправляем высоту
            x, y, climbed = object_id
            self.daggers.append({"x": x, "y": float(y - (climbed - self.climbed)), "visual": True})
            return
        if kind == "kill":
            for e in self.enemies:
                if e["id"] == object_id:
                    self.kill_enemy(e)
                    return
            return
        for p in self.platforms:
            if p["id"] == object_id:
                if kind == "break" and not p["broken"]:
                    self.break_platform(p)
                    p["break_t"] = -1  # как с растворением: догоняем соперника ровно в тот же кадр
                elif kind == "vanish":
                    # у соперника растворение началось после шага анимации платформ, а здесь шаг
                    # ещё впереди — начинаем «почти с нуля», чтобы оба растворились в один кадр
                    p["fade"] = p["fade"] or 0.001
                elif kind == "spring":
                    p["spring_timer"] = 12
                elif kind == "pickup" and p["bonus"]:
                    self.pick_bonus(p)
                return

    def update_mirror(self):
        """Кадр зеркала: сама физика идёт у соперника, здесь только анимации и движение мира."""
        self.anim += 1 / 60
        self.t += 1  # между сообщениями время идёт само, с новым сообщением — сверяется
        self.background.update(self.climbed)
        self.update_particles()
        self.shake = max(0, self.shake - 1)
        self.update_effects()
        self.update_platforms()
        self.update_enemies()
        self.update_daggers()
        self.events.clear()  # зеркалу нечего отправлять

    # --- анимация героя ---

    def pose(self):
        return "rise" if self.vy < -1.5 or self.rocket_timer else "fall"

    def side(self):
        return "left" if self.facing_left else "right"

    def frame_index(self):
        return int(self.anim * 10) % FRAMES

    def hero_frame(self):
        """Кадр героя: сплющен после приземления, вытянут в быстром полёте, наклонён при беге вбок."""
        if self.squash > 0.55:
            level = -2
        elif self.squash > 0.2:
            level = -1
        elif self.rocket_timer or self.vy < -8:
            level = 2
        elif self.vy < -3 or self.vy > 9:
            level = 1
        else:
            level = 0
        lean = 1 if abs(self.vx) > 2.5 else 0  # кадры «влево» отражены, так что 1 — всегда вперёд
        return art.hero[self.side()][level, lean][self.frame_index()]

    # --- отрисовка ---

    def draw(self):
        """Обычная одиночная игра: мир на весь экран, тряска и счёт."""
        self.draw_world(self.canvas)
        offset = (random.randint(-self.shake, self.shake), random.randint(-self.shake, self.shake)) \
            if self.shake else (0, 0)
        screen.fill((0, 0, 0))
        screen.blit(self.canvas, offset)
        self.draw_hud()

    def draw_world(self, canvas):
        """Рисует мир на canvas. Если canvas выше экрана, сверху видно больше (для дуэли)."""
        oy = canvas.get_height() - HEIGHT  # на сколько сдвинуть всё вниз
        self.background.draw(canvas, self.climbed, oy)
        self.draw_platforms(canvas, oy)
        self.draw_enemies(canvas, oy)
        for d in self.daggers:
            image = art.dagger
            pos = (d["x"] - image.get_width() // 2, int(d["y"]) + oy)
            canvas.blit(art.dagger_glow, (pos[0] - 7, pos[1] - 4), special_flags=pygame.BLEND_RGB_ADD)
            canvas.blit(image, pos)
            for i in (1, 2):  # след: пара «теней» позади
                canvas.fill((150, 68, 18), (d["x"] - 1, pos[1] + image.get_height() + i * 6, 2, 3))
        for t in self.trail:
            frame = t["frame"]
            image = shadow_silhouette(frame.image)
            image.set_alpha(t["life"] * 9)
            canvas.blit(image, (round(t["x"] + PLAYER_W / 2 - frame.anchor_x), round(t["y"] + PLAYER_H - frame.feet_y + oy)))
        if not self.dying and not self.over:
            self.draw_player(canvas, oy)
        for p in self.particles:
            size = round(p["size"] * p["life"] / p["max"])
            if size >= 1:  # частицы — квадратные «пиксели»
                canvas.fill(p["color"], (int(p["x"]) - size // 2, int(p["y"] + oy) - size // 2, size, size))
        self.background.draw_front(canvas, self.climbed, oy)

    def draw_platforms(self, canvas, oy):
        for p in self.platforms:
            rect = p["rect"]
            image = p["image"]
            x, y = rect.x - 1, rect.y - 4 + oy  # картинка с контуром на пиксель шире
            if p["broken"]:
                # две половинки разлетаются и крутятся
                half = image.get_width() // 2
                t = p["break_t"]
                for i, sub in enumerate((image.subsurface((0, 0, half, image.get_height())),
                                         image.subsurface((half, 0, image.get_width() - half, image.get_height())))):
                    side = -1 if i == 0 else 1
                    rotated = pygame.transform.rotate(sub, -side * (t * 4 // 15) * 15)  # поворот ступеньками
                    canvas.blit(rotated, (x + i * half + side * t * 1.5, y))
                continue
            if p["fade"]:
                image = image.copy()
                image.set_alpha(int(255 * (1 - p["fade"] / VANISH_FRAMES)))
            elif p["kind"] == "vanishing":
                image.set_alpha(190 if int(self.anim * 4 + p["phase"]) % 2 else 240)
            canvas.blit(image, (x, y))
            if p["bonus"]:
                bonus_rect = self.bonus_rect(p).move(0, oy)
                bob = round(math.sin(self.anim * 3 + p["phase"]) * 2)
                if p["bonus"] == "spring":
                    canvas.blit(art.spring[1 if p["spring_timer"] else 0], bonus_rect.move(-2, 2))
                elif p["bonus"] == "rocket":
                    canvas.blit(art.rocket, bonus_rect.move(-2, bob))
                else:
                    canvas.blit(art.shadow_orb[int(self.anim * 12) % FRAMES], bonus_rect.move(-2, bob))

    def draw_enemies(self, canvas, oy):
        for e in self.enemies:
            rect = e["rect"].move(0, oy)
            frame = int(e["anim"] * 1.4) % FRAMES
            if e["kind"] == "creep":
                image = art.creep["right" if e["dir"] > 0 else "left"][frame]
                canvas.blit(image, image.get_rect(midbottom=(rect.centerx, rect.bottom + 5)))
            elif e["kind"] == "familiar":
                image = art.familiar["right" if e["dir"] > 0 else "left"][frame]
                canvas.blit(image, image.get_rect(center=(rect.centerx, rect.centery - 2)))
            else:
                light_on = int(e["anim"] * 2) % 2 == 0  # лампочка мигает раз в секунду
                if light_on:
                    glow = art.mine_glow
                    canvas.blit(glow, glow.get_rect(center=(rect.centerx, rect.centery - 8)),
                                special_flags=pygame.BLEND_RGB_ADD)
                image = art.mine[1 if light_on else 0]
                canvas.blit(image, image.get_rect(center=(rect.centerx, rect.centery + 2)))

    def draw_player(self, canvas, oy):
        player = self.player_rect().move(0, oy)
        frame = self.hero_frame()
        image = frame.image
        left = player.centerx - frame.anchor_x
        top = player.bottom - frame.feet_y

        if self.rocket_timer > 0:
            # «Крылья тьмы»: за спиной машут крылья летучей мыши, вокруг — фиолетовое сияние
            canvas.blit(art.rocket_glow, art.rocket_glow.get_rect(center=player.center),
                        special_flags=pygame.BLEND_RGB_ADD)
            wings = art.flight_wings[int(self.anim * 16) % FRAMES]
            canvas.blit(wings, wings.get_rect(center=(player.centerx, player.y + 12)))
        if self.shadow_timer > 0:
            if self.shadow_timer > 90 or self.shadow_timer // 8 % 2 == 0:  # мигает, когда кончается
                aura = art.shadow_glow
                canvas.blit(aura, aura.get_rect(center=player.center), special_flags=pygame.BLEND_RGB_ADD)
            image = image.copy()
            image.set_alpha(150)

        # у края экрана рисуем «вторую половину» героя с другой стороны
        offsets = [0]
        if left < 0:
            offsets.append(WIDTH)
        if left + image.get_width() > WIDTH:
            offsets.append(-WIDTH)
        for dx in offsets:
            canvas.blit(image, (left + dx, top))

    def draw_timer_bar(self, y, label, timer, total, color):
        screen.blit(outlined_text(label, small_font, color), (WIDTH - 192, y))
        bar = pygame.Rect(WIDTH - 190, y + 26, 170, 8)
        pygame.draw.rect(screen, px.OUTLINE, bar.inflate(4, 4))
        pygame.draw.rect(screen, (60, 60, 80), bar)
        pygame.draw.rect(screen, color, (bar.x, bar.y, int(bar.width * timer / total), bar.height))

    def draw_hud(self):
        screen.blit(outlined_text(f"Высота: {self.height_m} м", font, TEXT_COLOR), (10, 8))
        screen.blit(outlined_text(f"Рекорд: {max(self.best, self.height_m)} м", font, GOLD_COLOR), (10, 44))
        screen.blit(outlined_text(self.player_name, small_font, GRAY_COLOR), (10, 84))
        y = 10
        if self.rocket_timer > 0:
            self.draw_timer_bar(y, "Крылья тьмы", self.rocket_timer, ROCKET_TIME, ROCKET_COLOR)
            y += 46
        if self.shadow_timer > 0:
            self.draw_timer_bar(y, "Теневой танец", self.shadow_timer, SHADOW_TIME, SHADOW_COLOR)
        for popup in self.popups:
            text = outlined_text(popup["text"], font, GOLD_COLOR)
            text.set_alpha(min(255, popup["life"] * 6))
            screen.blit(text, text.get_rect(center=(WIDTH // 2, HEIGHT * 0.22 - (90 - popup["life"]) // 2)))
        if self.hint_timer:
            hint = outlined_text("↑ / W / Пробел — бросить кинжал", font, GOLD_COLOR)
            hint.set_alpha(min(255, self.hint_timer * 5))
            screen.blit(hint, hint.get_rect(center=(WIDTH // 2, HEIGHT - 40)))


_silhouettes = {}


def shadow_silhouette(image):
    """Фиолетовый силуэт кадра героя — для теневых следов «Теневого танца» (кадры запоминаем)."""
    key = id(image)
    if key not in _silhouettes:
        _silhouettes[key] = px.silhouette(image, (150, 90, 255, 255))
    return _silhouettes[key]


def outlined_text(text, fnt, color):
    """Надпись в пиксельном стиле: без сглаживания и с тёмной обводкой — читается на любом фоне."""
    body = fnt.render(text, False, color)
    shadow = fnt.render(text, False, px.OUTLINE)
    result = pygame.Surface((body.get_width() + 4, body.get_height() + 4), pygame.SRCALPHA)
    for dx, dy in ((0, 2), (4, 2), (2, 0), (2, 4), (4, 4)):
        result.blit(shadow, (dx, dy))
    result.blit(body, (2, 2))
    return result


def prepare_platforms():
    """Картинки всех платформ готовим при запуске — чтобы игра не подтормаживала, встречая новую."""
    for biome in ("valley", "sunset", "clouds", "space"):
        for kind in ("normal", "moving", "elevator", "breaking", "vanishing", "trampoline"):
            art.platform(kind, biome, PLATFORM_W)
        for width in BRIDGE_WIDTHS:
            art.platform("normal", biome, width)


prepare_platforms()
