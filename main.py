"""«Прыжки Сларка» — отдельная игра: меню, одиночная игра, сетевая дуэль и таблица рекордов."""
import json

import pygame

from common import WIDTH, HEIGHT, FPS, TEXT_COLOR, GRAY_COLOR, GOLD_COLOR, DATA_DIR, screen, small_font, font, big_font
import duel
import pixel_art as px
from jump_background import Background, PIXELS_PER_METER
from jump_game import JumpGame, art, outlined_text

RECORDS_FILE = DATA_DIR / "records.json"
MAX_RECORDS = 10
MAX_NAME_LENGTH = 12
MENU_ITEMS = ["Играть", "Сетевая дуэль", "Рекорды", "Выход"]
BUTTON_COLOR, BUTTON_SELECTED = (46, 32, 78), (92, 58, 140)

clock = pygame.time.Clock()
pygame.display.set_caption("Прыжки Сларка")
pygame.display.set_icon(art.icon)
pygame.key.stop_text_input()  # ввод текста включаем только на экране имени


# --- Рекорды ---

def load_records():
    try:
        data = json.loads(RECORDS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        data = {}
    return data.get("records", []), data.get("last_name", "")


def save_records():
    data = {"last_name": player_name, "records": records}
    RECORDS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def add_record(height):
    """Добавляет результат. Возвращает место (1, 2, ...) или None, если не попал в десятку."""
    entry = {"name": player_name, "score": height}
    records.append(entry)
    records.sort(key=lambda r: r["score"], reverse=True)
    del records[MAX_RECORDS:]
    save_records()
    for place, r in enumerate(records, start=1):
        if r is entry:
            return place
    return None


def best_score():
    return records[0]["score"] if records else 0


# --- Меню ---

def menu_rects():
    return [pygame.Rect(WIDTH // 2 - 150, 300 + i * 66, 300, 52) for i in range(len(MENU_ITEMS))]


def draw_pixel_button(rect, text, selected):
    """Кнопка в пиксельном стиле: тёмный контур, светлая кромка сверху, у выбранной — оранжевая рамка."""
    pygame.draw.rect(screen, px.OUTLINE, rect.inflate(6, 6))
    pygame.draw.rect(screen, px.RIM_HERO if selected else (120, 96, 160), rect.inflate(2, 2))
    pygame.draw.rect(screen, BUTTON_SELECTED if selected else BUTTON_COLOR, rect)
    pygame.draw.rect(screen, (150, 112, 200) if selected else (74, 54, 110), (rect.x, rect.y, rect.width, 4))
    label = outlined_text(text, font, TEXT_COLOR if selected else GRAY_COLOR)
    screen.blit(label, label.get_rect(center=rect.center))


def menu_action(index):
    global state, running
    if index == 0:
        open_name_input("game")
    elif index == 1:
        open_name_input("net")
    elif index == 2:
        state = "records"
    else:
        running = False


def open_name_input(purpose):
    global state, name_text, name_purpose
    name_text = player_name
    name_purpose = purpose
    state = "name"
    pygame.key.start_text_input()


def confirm_name():
    global player_name, state, net_screen
    player_name = name_text.strip()
    save_records()  # запоминаем имя до следующего запуска
    pygame.key.stop_text_input()
    if name_purpose == "net":
        net_screen = duel.NetScreen(player_name)
        state = "net"
    else:
        start_game()


def start_game():
    global state, game, last_place, new_record
    game = JumpGame(player_name, best_score())
    last_place = None
    new_record = False
    state = "play"


def finish_game():
    global state, new_record, last_place
    new_record = game.height_m > best_score()
    last_place = add_record(game.height_m)
    state = "over"


# --- Отрисовка ---

def draw_backdrop():
    """Живой фон меню: небо медленно «проезжает» все зоны — от леса до космоса."""
    backdrop.draw(screen, backdrop_climbed)
    backdrop.draw_front(screen, backdrop_climbed)
    shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    shade.fill((10, 6, 24, 90))
    screen.blit(shade, (0, 0))


def draw_title(text, y=40):
    title = outlined_text(text, big_font, GOLD_COLOR)
    screen.blit(title, title.get_rect(midtop=(WIDTH // 2, y)))


def draw_hero(center, scale=2):
    """Большой анимированный Сларк: покачивается, хвост и шипы шевелятся."""
    frame = art.hero["right"][0, 0][int(ticks / 6) % len(art.hero["right"][0, 0])]
    image = pygame.transform.scale_by(frame.image, scale)  # без сглаживания — пиксели остаются чёткими
    bob = round(pygame.math.Vector2(0, 1).rotate(ticks * 3).y * 3) * scale
    screen.blit(image, image.get_rect(center=(center[0], center[1] + bob)))


def draw_menu():
    draw_title("ПРЫЖКИ СЛАРКА")
    draw_hero((WIDTH // 2, 200))
    for i, (text, rect) in enumerate(zip(MENU_ITEMS, menu_rects())):
        draw_pixel_button(rect, text, i == menu_selected)
    record = f"Рекорд: {best_score()} м    " if best_score() else ""
    hint = outlined_text(f"{record}Стрелки + Enter или мышь    F11 — полный экран", small_font, GRAY_COLOR)
    screen.blit(hint, hint.get_rect(center=(WIDTH // 2, HEIGHT - 20)))


def draw_name_input():
    draw_title("Сетевая дуэль" if name_purpose == "net" else "ПРЫЖКИ СЛАРКА")
    label = outlined_text("Как вас зовут?", font, TEXT_COLOR)
    screen.blit(label, label.get_rect(center=(WIDTH // 2, 235)))
    field = pygame.Rect(WIDTH // 2 - 200, 270, 400, 56)
    pygame.draw.rect(screen, px.OUTLINE, field.inflate(6, 6))
    pygame.draw.rect(screen, px.RIM_HERO, field.inflate(2, 2))
    pygame.draw.rect(screen, BUTTON_COLOR, field)
    cursor = "|" if pygame.time.get_ticks() // 500 % 2 == 0 else " "
    text = font.render(name_text + cursor, False, TEXT_COLOR)
    screen.blit(text, text.get_rect(midleft=(field.x + 16, field.centery)))
    hint = outlined_text("Enter — дальше    Esc — назад", small_font, GRAY_COLOR)
    screen.blit(hint, hint.get_rect(center=(WIDTH // 2, 370)))


def draw_records():
    draw_title("Рекорды")
    board = pygame.Rect(150, 130, WIDTH - 300, 390)
    pygame.draw.rect(screen, px.OUTLINE, board.inflate(6, 6))
    pygame.draw.rect(screen, (22, 14, 40), board)
    if not records:
        label = outlined_text("Пока пусто — сыграйте первую игру!", font, GRAY_COLOR)
        screen.blit(label, label.get_rect(center=board.center))
    for row, r in enumerate(records):
        y = board.y + 16 + row * 36
        color = GOLD_COLOR if last_place == row + 1 else TEXT_COLOR
        for text, x in ((f"{row + 1}.", board.x + 20), (r["name"], board.x + 70), (f"{r['score']} м", board.right - 130)):
            screen.blit(outlined_text(text, font, color), (x, y))
    hint = outlined_text("Esc или Enter — назад", small_font, GRAY_COLOR)
    screen.blit(hint, hint.get_rect(center=(WIDTH // 2, HEIGHT - 30)))


def draw_game_over():
    shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    shade.fill((10, 6, 24, 160))
    screen.blit(shade, (0, 0))
    draw_title("Игра окончена", HEIGHT // 2 - 150)
    for text, y, color in ((f"Высота: {game.height_m} м", HEIGHT // 2 - 40, TEXT_COLOR),
                           ("Новый рекорд!" if new_record else
                            f"Место в рекордах: {last_place}" if last_place else "", HEIGHT // 2 + 5, GOLD_COLOR),
                           ("R — ещё раз    Esc — в меню", HEIGHT // 2 + 80, TEXT_COLOR)):
        if text:
            label = outlined_text(text, font, color)
            screen.blit(label, label.get_rect(center=(WIDTH // 2, y)))


# --- Запуск ---

records, player_name = load_records()
name_text = ""
name_purpose = "game"
menu_selected = 0
game = None
net_screen = None
new_record = False
last_place = None
backdrop = Background()
backdrop_climbed = 0
ticks = 0
# "menu", "name", "records", "play", "over", "net" (сетевой дуэлью управляет net_screen из duel.py)
state = "menu"
running = True

while running:
    ticks += 1
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
            pygame.display.toggle_fullscreen()

        elif state == "menu":
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    menu_selected = (menu_selected - 1) % len(MENU_ITEMS)
                elif event.key == pygame.K_DOWN:
                    menu_selected = (menu_selected + 1) % len(MENU_ITEMS)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    menu_action(menu_selected)
                elif event.key == pygame.K_ESCAPE:
                    running = False
            elif event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
                for i, rect in enumerate(menu_rects()):
                    if rect.collidepoint(event.pos):
                        menu_selected = i
                        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                            menu_action(i)

        elif state == "name":
            if event.type == pygame.TEXTINPUT:
                name_text = (name_text + event.text)[:MAX_NAME_LENGTH]
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_BACKSPACE:
                    name_text = name_text[:-1]
                elif event.key == pygame.K_RETURN and name_text.strip():
                    confirm_name()
                elif event.key == pygame.K_ESCAPE:
                    pygame.key.stop_text_input()
                    state = "menu"

        elif state == "records":
            if (event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_RETURN)) \
                    or event.type == pygame.MOUSEBUTTONDOWN:
                state = "menu"

        elif state == "play":
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                game.over = True  # Esc — закончить досрочно (результат сохранится)
            else:
                game.handle_event(event)  # бросок кинжала

        elif state == "over":
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:
                    start_game()
                elif event.key == pygame.K_ESCAPE:
                    state = "menu"

        elif state == "net":
            net_screen.handle_event(event)

    # логика
    if state == "play":
        game.update()
        if game.over:
            finish_game()
    elif state == "net":
        net_screen.update()
        if net_screen.finished:
            net_screen.close()
            state = "menu"
    else:
        # фон меню: медленно поднимаемся сквозь все зоны и начинаем заново
        backdrop_climbed += 3
        if backdrop_climbed > 1300 * PIXELS_PER_METER:
            backdrop_climbed = 0
            backdrop = Background()  # начинаем путь заново — облака и туманности строятся с нуля
        backdrop.update(backdrop_climbed)
        backdrop.banner_timer = 0  # названия зон в меню не показываем

    # отрисовка
    if state in ("play", "over"):
        game.draw()
        if state == "over":
            draw_game_over()
    elif state == "net":
        net_screen.draw()
    else:
        draw_backdrop()
        if state == "menu":
            draw_menu()
        elif state == "name":
            draw_name_input()
        elif state == "records":
            draw_records()

    pygame.display.flip()
    clock.tick(FPS)

if net_screen:
    net_screen.close()
pygame.quit()
