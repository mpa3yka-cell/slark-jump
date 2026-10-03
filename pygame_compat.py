"""Обёртка pygame поверх arcade для совместимости."""
import arcade
import math as _math
from dataclasses import dataclass
from typing import Tuple, List, Optional, Any

# Константы
EVENT_TYPE_WINDOW_CLOSE = arcade.EVENT_TYPE_CLOSE
EVENT_TYPE_KEY_PRESS = arcade.EVENT_TYPE_KEY_PRESS
EVENT_TYPE_KEY_RELEASE = arcade.EVENT_TYPE_KEY_RELEASE
EVENT_TYPE_TEXT_INPUT = arcade.EVENT_TYPE_TEXT_INPUT
EVENT_TYPE_MOUSE_MOTION = arcade.EVENT_TYPE_MOUSE_MOTION
EVENT_TYPE_MOUSE_BUTTON_PRESS = arcade.EVENT_TYPE_MOUSE_BUTTON_PRESS
EVENT_TYPE_MOUSE_BUTTON_RELEASE = arcade.EVENT_TYPE_MOUSE_BUTTON_RELEASE

# Клавиши
key = arcade.key

# Цвета для BLEND
BLEND_ADD = arcade.BLEND_ADD

# Инициализация
def init():
    arcade.init()

# Экран
_window = None

def get_screen():
    global _window
    return _window

def set_screen(win):
    global _window
    _window = win

# Surface - обёртка поверх arcade текстуры
class Surface:
    def __init__(self, width, height, srcalpha=False):
        self.width = width
        self.height = height
        self.has_alpha = srcalpha
        self._color = (0, 0, 0, 0) if srcalpha else (0, 0, 0)
        self._texture = None
        
    def get_width(self):
        return self.width
    
    def get_height(self):
        return self.height
    
    def get_size(self):
        return (self.width, self.height)
    
    def get_rect(self):
        return Rect(0, 0, self.width, self.height)
    
    def fill(self, color, rect=None, special_flags=None):
        # Заполняем цвет
        if isinstance(color, tuple) and len(color) == 4:
            self._color = color
        elif isinstance(color, tuple) and len(color) == 3:
            self._color = (*color, 255)
        else:
            self._color = (int(color), int(color), int(color), 255)
    
    def blit(self, source, dest, rect=None, special_flags=None):
        pass  # Отрисовка делается через arcade
    
    def subsurface(self, rect):
        return Surface(rect[2], rect[3])
    
    def copy(self):
        s = Surface(self.width, self.height, self.has_alpha)
        s._color = self._color
        return s
    
    def set_alpha(self, alpha):
        pass
    
    def get_at(self, pos):
        return self._color
    
    def set_at(self, pos, color):
        pass


# Rect - простой прямоугольник
@dataclass
class Rect:
    x: float
    y: float
    width: float
    height: float
    
    def __init__(self, x, y, w=None, h=None):
        if isinstance(x, tuple) and len(x) == 4:
            self.x, self.y, self.width, self.height = x
        else:
            self.x = x
            self.y = y
            self.width = w if w is not None else 0
            self.height = h if h is not None else 0
    
    def centerx(self):
        return self.x + self.width / 2
    
    def centery(self):
        return self.y + self.height / 2
    
    @property
    def center(self):
        return (self.centerx, self.centery)
    
    @center.setter
    def center(self, val):
        self.x = val[0] - self.width / 2
        self.y = val[1] - self.height / 2
    
    @property
    def midbottom(self):
        return (self.centerx, self.y + self.height)
    
    @midbottom.setter
    def midbottom(self, val):
        self.x = val[0] - self.width / 2
        self.y = val[1] - self.height
    
    @property
    def bottom(self):
        return self.y + self.height
    
    @bottom.setter
    def bottom(self, val):
        self.y = val - self.height
    
    @property
    def top(self):
        return self.y
    
    @top.setter
    def top(self, val):
        self.y = val
    
    @property
    def left(self):
        return self.x
    
    @left.setter
    def left(self, val):
        self.x = val
    
    @property
    def right(self):
        return self.x + self.width
    
    @right.setter
    def right(self, val):
        self.x = val - self.width
    
    @property
    def centery_top(self):
        return (self.centerx, self.y)
    
    def collidepoint(self, x, y=None):
        if y is None:
            x, y = x
        return self.x <= x < self.x + self.width and self.y <= y < self.y + self.height
    
    def colliderect(self, other):
        return (self.x < other.x + other.width and
                self.x + self.width > other.x and
                self.y < other.y + other.height and
                self.y + self.height > other.y)
    
    def inflate(self, dx, dy):
        return Rect(self.x - dx/2, self.y - dy/2, self.width + dx, self.height + dy)
    
    def move(self, dx, dy):
        return Rect(self.x + dx, self.y + dy, self.width, self.height)
    
    def copy(self):
        return Rect(self.x, self.y, self.width, self.height)


# Mixer - звук
_mixer_sounds = []

class mixer:
    @staticmethod
    def Sound(path):
        sound = arcade.load_sound(str(path))
        _mixer_sounds.append(sound)
        return sound
    
    music = None

    @staticmethod
    def unload():
        pass


# Font - шрифты
class font:
    @staticmethod
    def SysFont(name, size, bold=False):
        return Font(name, size, bold)
    
    @staticmethod
    def get_default():
        return font.SysFont("arial", 20)


class Font:
    def __init__(self, name, size, bold=False):
        self.name = name
        self.size = size
        self.bold = bold
    
    def render(self, text, antialias, color):
        # Возвращаем Surface с текстом
        s = Surface(100, 30, True)
        s._text = text
        s._color = color
        s._antialias = antialias
        # Устанавливаем размер
        s.width = len(text) * self.size * 0.6
        s.height = self.size * 1.2
        return s
    
    def size(self, text):
        return (len(text) * self.size * 0.6, self.size * 1.2)
    
    def get_linesize(self):
        return self.size


# Display
class display:
    @staticmethod
    def set_mode(size, flags=0, resizable=True):
        global _window
        w, h = size
        _window = arcade.Window(w, h, resizable=resizable)
        return _window
    
    @staticmethod
    def set_caption(title):
        global _window
        if _window:
            _window.title = title
    
    @staticmethod
    def set_icon(icon):
        pass
    
    @staticmethod
    def flip():
        global _window
        if _window:
            _window.update()
            _window.render()
    
    @staticmethod
    def toggle_fullscreen():
        global _window
        if _window:
            _window.set_fullscreen(not _window.fullscreen)


# Key
class key:
    _pressed = set()
    
    @staticmethod
    def get_pressed():
        return _key_state
    
    @staticmethod
    def stop_text_input():
        pass
    
    @staticmethod
    def start_text_input():
        pass


_key_state = {}

def get_events():
    return arcade.get_events()


# Time
class time:
    @staticmethod
    def get_ticks():
        return arcade.get_current_time() * 1000


# math
class math:
    tau = _math.tau
    sin = _math.sin
    cos = _math.cos
    floor = _math.floor
    ceil = _math.ceil
    radians = _math.radians
    degrees = _math.degrees
    pi = _math.pi
    sqrt = _math.sqrt
    pow = _math.pow
    log = _math.log
    log10 = _math.log10
    exp = _math.exp
    asin = _math.asin
    acos = _math.acos
    atan = _math.atan
    atan2 = _math.atan2
    hypot = _math.hypot
    isclose = _math.isclose
    dist = _math.dist


# transform
class transform:
    @staticmethod
    def scale_by(surface, factor):
        # Возвращаем новый Surface с увеличенным размером
        s = Surface(int(surface.width * factor), int(surface.height * factor), surface.has_alpha)
        return s
    
    @staticmethod
    def rotate(surface, angle):
        return Surface(surface.width, surface.height)


# draw
class draw:
    @staticmethod
    def rect(surf, color, rect, width=0, border_radius=0):
        pass
    
    @staticmethod
    def line(surf, color, start, end, width=1):
        pass
    
    @staticmethod
    def circle(surf, color, center, radius):
        pass
    
    @staticmethod
    def polygon(surf, points):
        pass
    
    @staticmethod
    def lines(surf, color, closed, points, width=1):
        pass


# PixelArray - работа с пикселями
class PixelArray:
    def __init__(self, surface):
        self.surface = surface
    
    def replace(self, old_color, new_color):
        pass
    
    def __del__(self):
        pass


# mixer
class mixer:
    @staticmethod
    def Sound(path):
        return arcade.load_sound(str(path))
    
    @staticmethod
    def music():
        pass
    
    @staticmethod
    def unload():
        pass


# get_events
def get_events():
    return arcade.get_events()


# init
def init():
    arcade.init()


# quit
def quit():
    global _window
    if _window:
        _window.close()
        _window = None


# image
class image:
    @staticmethod
    def load(path):
        return arcade.load_texture(str(path))


# mask
class mask:
    @staticmethod
    def from_surface(surface):
        return None
    
    @staticmethod
    def to_surface(mask_obj, setcolor=None, unsetcolor=None):
        return Surface(10, 10)


# Vector2
class Vector2:
    def __init__(self, x, y=0):
        self.x = x
        self.y = y
    
    def rotate(self, angle):
        rad = _math.radians(angle)
        cos_a = _math.cos(rad)
        sin_a = _math.sin(rad)
        return Vector2(self.x * cos_a - self.y * sin_a, self.x * sin_a + self.y * cos_a)
    
    def __mul__(self, other):
        return Vector2(self.x * other, self.y * other)
    
    def __rmul__(self, other):
        return self.__mul__(other)
    
    def __add__(self, other):
        return Vector2(self.x + other.x, self.y + other.y)
    
    def __sub__(self, other):
        return Vector2(self.x - other.x, self.y - other.y)
    
    def length(self):
        return _math.sqrt(self.x ** 2 + self.y ** 2)
    
    def normalize(self):
        l = self.length()
        if l > 0:
            return Vector2(self.x / l, self.y / l)
        return Vector2(0, 0)
    
    def dot(self, other):
        return self.x * other.x + self.y * other.y
    
    def __repr__(self):
        return f"Vector2({self.x}, {self.y})"
