"""Сетевая дуэль «Прыжков Сларка»: кто прыгнет выше из трёх попыток.

Как это устроено:
- Хост открывает порт PORT и ждёт. Заодно он слушает порт DISCOVERY_PORT и отвечает
  на вопрос «кто тут создал игру?».
- Второй игрок в лобби раз в секунду рассылает этот вопрос всем в сети (широковещательно)
  и показывает список ответивших хостов. Можно и ввести IP вручную.
- Хост выбирает «зёрна» (seed) для трёх попыток — у обоих игроков одинаковые уровни.
- 30 раз в секунду каждый отправляет, где его Сларк, плюс события: сломал платформу,
  сбил врага, подобрал бонус. Мир соперника каждый строит у себя сам по тому же зерну.
- Сообщения — строки JSON, по одной на строку; читает их фоновый поток, чтобы игра не подвисала.

Играть проще всего в одной сети (например, от одного Wi-Fi). Через интернет — нужен проброс порта
на роутере хоста или программа виртуальной сети (Radmin VPN, ZeroTier).
Важно: обычный VPN (например, AmneziaVPN) может забирать себе трафик домашней сети — тогда
игроки друг друга не видят. На время игры его нужно выключить.
"""
import json
import queue
import random
import re
import socket
import subprocess
import threading
import time

import pygame

from common import (WIDTH, HEIGHT, TEXT_COLOR, GRAY_COLOR, GOLD_COLOR, CARD_COLOR, DATA_DIR, screen,
                    small_font, font, big_font, draw_text, draw_button)
from jump_game import JumpGame

PORT = 50505
DISCOVERY_PORT = 50506    # сюда клиенты спрашивают «кто тут создал игру?»
GAME_TAG = "slark-duel"   # чтобы не путать наши сообщения с чужими
PROTOCOL = 5              # версия сетевой игры: у обоих игроков должна совпадать
                          # (5 — кинжалы: новое сообщение «кинжал брошен»)
ATTEMPTS = 3
SEND_EVERY = 2            # отправляем своё состояние каждые 2 кадра (30 раз в секунду)
PANEL_TOP = 44            # сверху полоска со счётом
PANEL_W, PANEL_H = WIDTH // 2, HEIGHT - PANEL_TOP
VIEW_EXTRA = PANEL_H * 2 - HEIGHT   # половина экрана в масштабе 1:2 видит мир на столько выше
COUNTDOWN = 180           # 3 секунды обратного отсчёта перед первой попыткой
PAUSE_BETWEEN = 150       # пауза между попытками
NETWORK_FILE = DATA_DIR / "network.json"  # последний IP, к которому подключались

RED_COLOR = (255, 110, 110)
GREEN_COLOR = (120, 230, 130)


# --- Сеть ---

class Connection:
    """Соединение с соперником: send() отправляет сообщение, receive() отдаёт всё, что пришло."""

    def __init__(self, sock, already_received=b""):
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # без задержек на мелких сообщениях
        sock.settimeout(None)
        self.sock = sock
        self.buffer = already_received  # то, что хост уже прочитал, пока проверял, кто подключился
        self.inbox = queue.Queue()
        self.alive = True
        threading.Thread(target=self._read_loop, daemon=True).start()

    def _read_loop(self):
        buffer = self.buffer
        try:
            while True:
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if line:
                        self.inbox.put(json.loads(line))
                data = self.sock.recv(65536)
                if not data:
                    break  # соперник закрыл соединение
                buffer += data
        except (OSError, ValueError):
            pass
        self.alive = False

    def send(self, message):
        if not self.alive:
            return
        try:
            self.sock.sendall((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
        except OSError:
            self.alive = False

    def receive(self):
        messages = []
        while not self.inbox.empty():
            messages.append(self.inbox.get_nowait())
        return messages

    def close(self):
        self.alive = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.sock.close()


def read_first_line(sock, timeout=3):
    """Читает из соединения байты до первого перевода строки (одно сообщение)."""
    sock.settimeout(timeout)
    data = b""
    while b"\n" not in data:
        chunk = sock.recv(4096)
        if not chunk or len(data) > 65536:
            raise OSError("соединение закрылось")
        data += chunk
    return data


class Host:
    """Открывает порт и в фоне ждёт второго игрока. Если порт занят — ошибка сразу в __init__.

    На «проверку связи» (сообщение probe) отвечает и продолжает ждать настоящего соперника."""

    def __init__(self, host_name=""):
        self.host_name = host_name
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.bind(("", PORT))
        self.server.listen(2)
        self.connection = None
        self.error = None
        self.closed = False
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        try:
            while not self.connection:
                sock, _ = self.server.accept()
                try:
                    data = read_first_line(sock)
                    first = json.loads(data.split(b"\n", 1)[0])
                except (OSError, ValueError):
                    sock.close()  # подключились и ничего не сказали — это не игрок
                    continue
                if first.get("type") == "probe":
                    reply = {"type": "probe_ok", "name": self.host_name, "protocol": PROTOCOL}
                    try:
                        sock.sendall((json.dumps(reply, ensure_ascii=False) + "\n").encode("utf-8"))
                    except OSError:
                        pass
                    sock.close()
                    continue
                self.connection = Connection(sock, already_received=data)
        except OSError as e:
            if not self.closed:
                self.error = str(e)
        finally:
            self.server.close()

    def close(self):
        self.closed = True
        self.server.close()


class Joiner:
    """Подключается к хосту в фоне (чтобы окно не зависало, пока идёт подключение)."""

    def __init__(self, address):
        self.connection = None
        self.error = None
        threading.Thread(target=self._connect, args=(address,), daemon=True).start()

    def _connect(self, address):
        try:
            sock = socket.create_connection((address, PORT), timeout=5)
            self.connection = Connection(sock)
        except OSError as e:
            self.error = friendly_error(e)


def friendly_error(error):
    """Понятное объяснение сетевой ошибки."""
    if isinstance(error, socket.timeout) or "timed out" in str(error):
        return ("Хост не ответил. Узнать причину поможет «Проверка связи» в меню сетевой дуэли "
                "(VPN, брандмауэр или роутер).")
    if getattr(error, "winerror", None) == 10013:
        return "Windows запретила подключение. Обычно так делает VPN — выключите его на время игры."
    if getattr(error, "winerror", None) == 10061:
        return "Компьютер найден, но игра на нём не ждёт подключения. Пусть хост нажмёт «Создать игру»."
    return str(error)


class Announcer:
    """Хост: отвечает на вопрос «кто тут создал игру?», чтобы появиться в лобби у других."""

    def __init__(self, host_name):
        self.host_name = host_name
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("", DISCOVERY_PORT))
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        # host_id — чтобы клиент, услышав нас сразу по нескольким адресам, показал одну строку
        reply = json.dumps({"tag": GAME_TAG, "type": "here", "name": self.host_name, "protocol": PROTOCOL,
                            "host_id": random.randrange(1, 2 ** 31)}).encode("utf-8")
        while self.running:
            try:
                data, address = self.sock.recvfrom(2048)
                message = json.loads(data)
                if message.get("tag") == GAME_TAG and message.get("type") == "find":
                    self.sock.sendto(reply, address)
            except (OSError, ValueError):
                if not self.running:
                    return

    def close(self):
        self.running = False
        self.sock.close()


class Finder:
    """Клиент: раз в секунду спрашивает всю сеть «кто тут создал игру?» и собирает ответы."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.bind(("", 0))
        self.hosts = {}          # номер хоста -> {"name", "protocol", "ips": {IP: время ответа}}
        self.own_ips = local_ips()
        self.last_ask = 0.0
        self.running = True
        threading.Thread(target=self._listen, daemon=True).start()

    def _listen(self):
        while self.running:
            try:
                data, (ip, _) = self.sock.recvfrom(2048)
                message = json.loads(data)
                if message.get("tag") == GAME_TAG and message.get("type") == "here":
                    host = self.hosts.setdefault(message.get("host_id", ip), {"ips": {}})
                    host["name"] = str(message.get("name", "?"))[:12]
                    host["protocol"] = message.get("protocol")
                    host["ips"][ip] = time.time()
            except (OSError, ValueError):
                if not self.running:
                    return

    def update(self):
        if time.time() - self.last_ask < 1:
            return
        self.last_ask = time.time()
        question = json.dumps({"tag": GAME_TAG, "type": "find"}).encode("utf-8")
        # «всем в сети», «всем в своей подсети» и «себе» (если хост на этом же компьютере)
        targets = {"255.255.255.255", "127.0.0.1"}
        targets.update(ip.rsplit(".", 1)[0] + ".255" for ip in self.own_ips)
        for target in targets:
            try:
                self.sock.sendto(question, (target, DISCOVERY_PORT))
            except OSError:
                pass

    def visible(self):
        """Хосты, которые отвечали в последние 3 секунды: список (лучший IP, данные хоста)."""
        now = time.time()
        own_prefixes = {ip.rsplit(".", 1)[0] for ip in self.own_ips}
        result = []
        for host in list(self.hosts.values()):
            fresh = [ip for ip, seen in list(host["ips"].items()) if now - seen < 3]
            if not fresh:
                continue
            # лучше всего: этот же компьютер, потом — адрес из нашей же сети, потом — любой
            fresh.sort(key=lambda ip: (not ip.startswith("127."), ip.rsplit(".", 1)[0] not in own_prefixes, ip))
            result.append((fresh[0], host))
        return sorted(result, key=lambda item: item[1]["name"])

    def close(self):
        self.running = False
        self.sock.close()


def local_ips():
    """IP-адреса этого компьютера в сетях (без служебных адресов 127.* и 169.254.*)."""
    ips = set()
    try:
        # «подключение» UDP ничего не отправляет, но показывает, через какой адрес мы выходим в сеть
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("10.255.255.255", 1))
        ips.add(probe.getsockname()[0])
        probe.close()
    except OSError:
        pass
    try:
        ips.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    return sorted(ip for ip in ips if not ip.startswith(("127.", "169.254.")))


def vpn_warning():
    """Проверяет, не забирает ли VPN трафик домашней сети. Возвращает текст предупреждения или None.

    Для каждого своего адреса смотрим: через какой адрес Windows отправила бы пакет
    соседу по этой же сети. Если не через этот — значит, маршрут перехватил кто-то другой (VPN)."""
    for ip in local_ips():
        if not ip.startswith(("192.168.", "10.", "172.")):
            continue
        prefix = ip.rsplit(".", 1)[0]
        neighbor = prefix + (".1" if not ip.endswith(".1") else ".2")
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            probe.connect((neighbor, 9))
            source = probe.getsockname()[0]
            probe.close()
        except OSError:
            continue
        if source.rsplit(".", 1)[0] != prefix:
            return (f"Похоже, VPN перехватывает домашнюю сеть {prefix}.*: пакеты туда идут через {source}. "
                    f"Выключите VPN на время игры, иначе соединение не установится.")
    return None


# --- Проверка связи с другом ---

def route_goes_elsewhere(address, own_ips):
    """Если адрес друга из нашей сети, а Windows отправила бы пакеты к нему с чужого адреса (VPN),
    возвращает этот чужой адрес. Иначе None."""
    if address.startswith("127."):
        return None
    prefix = address.rsplit(".", 1)[0]
    if not any(ip.rsplit(".", 1)[0] == prefix for ip in own_ips):
        return None  # адрес не из нашей сети — это проверит следующий шаг
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect((address, 9))
        source = probe.getsockname()[0]
        probe.close()
    except OSError:
        return None
    return None if source.rsplit(".", 1)[0] == prefix else source

def probe_host(address):
    """Стучимся в игру друга по TCP. Возвращает ("ok", имя), ("refused", None), ("timeout", None)
    или ("error", текст)."""
    try:
        sock = socket.create_connection((address, PORT), timeout=3)
    except OSError as e:
        code = getattr(e, "winerror", None)
        if isinstance(e, ConnectionRefusedError) or code == 10061:
            return "refused", None
        if isinstance(e, TimeoutError) or code == 10060:
            return "timeout", None
        return "error", friendly_error(e)
    try:
        sock.sendall((json.dumps({"type": "probe"}) + "\n").encode("utf-8"))
        reply = json.loads(read_first_line(sock).split(b"\n", 1)[0])
        return "ok", reply.get("name") if reply.get("type") == "probe_ok" else None
    except (OSError, ValueError):
        return "ok", None  # подключиться получилось, а ответ — старой версии игры
    finally:
        sock.close()


def ask_host_directly(address):
    """Спрашиваем «кто тут?» напрямую у адреса друга (как в лобби, но без рассылки всем)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(2)
    try:
        sock.sendto(json.dumps({"tag": GAME_TAG, "type": "find"}).encode("utf-8"), (address, DISCOVERY_PORT))
        data, _ = sock.recvfrom(2048)
        return json.loads(data).get("name")
    except (OSError, ValueError):
        return None
    finally:
        sock.close()


def knows_mac(address):
    """Узнал ли компьютер сетевой адрес (MAC) устройства друга. Это получается, даже если брандмауэр
    друга блокирует игру, — но не получается, если устройства друг друга вообще не видят."""
    try:
        output = subprocess.run(["arp", "-a", address], capture_output=True, timeout=5,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return re.search(rb"([0-9a-fA-F]{2}[-:]){5}[0-9a-fA-F]{2}", output) is not None


def router_answers(address):
    """Отвечает ли роутер (адрес .1 в той же сети). «Отказ» тоже считается ответом."""
    router = address.rsplit(".", 1)[0] + ".1"
    try:
        socket.create_connection((router, 80), timeout=2).close()
        return True
    except ConnectionRefusedError:
        return True
    except OSError as e:
        return getattr(e, "winerror", None) == 10061


class Diagnostics:
    """Проверяет по шагам путь до компьютера друга и объясняет, что не так."""

    def __init__(self, address):
        self.address = address
        self.steps = []          # (True — хорошо / False — плохо / None — просто сведения, текст)
        self.verdict = None      # итог простыми словами
        self.verdict_ok = False
        self.done = False
        threading.Thread(target=self._run, daemon=True).start()

    def step(self, ok, text):
        self.steps.append((ok, text))

    def finish(self, ok, text):
        self.verdict_ok = ok
        self.verdict = text
        self.done = True

    def _run(self):
        address = self.address
        own = local_ips()
        self.step(None, "Ваши адреса: " + (", ".join(own) if own else "нет"))
        if not own:
            return self.finish(False, "Компьютер не подключён к сети. Подключитесь к Wi-Fi.")

        intercepted = route_goes_elsewhere(address, own)
        self.step(not intercepted, "VPN не мешает" if not intercepted else
                  f"Путь к {address} идёт через {intercepted} — это VPN")
        if intercepted:
            return self.finish(False, "Выключите VPN (кнопка «Отключиться» в программе VPN) и проверьте снова.")

        own_networks = sorted({ip.rsplit(".", 1)[0] + ".*" for ip in own})
        same_network = address.startswith("127.") or address.rsplit(".", 1)[0] + ".*" in own_networks
        self.step(same_network, "Адрес друга из вашей сети" if same_network else
                  f"Адрес {address} не из ваших сетей ({', '.join(own_networks)})")

        if same_network and not address.startswith("127."):
            router = router_answers(address)
            self.step(router, "Роутер отвечает" if router else "Роутер не отвечает на порту 80 (не страшно)")

        status, name = probe_host(address)
        found = ask_host_directly(address)
        if status == "ok":
            self.step(True, f"Игра друга ждёт подключения{f' ({name})' if name else ''}")
            self.step(found is not None, "Поиск в лобби видит эту игру" if found is not None else
                      "Прямой запрос поиска остался без ответа")
            if found is None:
                return self.finish(True, "Подключиться можно: в «Найти игру» выберите «Ввести IP вручную» "
                                         f"и введите {address}.")
            return self.finish(True, "Всё в порядке! Игра должна появиться в «Найти игру».")
        if status == "refused":
            self.step(True, "Компьютер друга отвечает")
            self.step(False, "Игра на нём не ждёт подключения")
            return self.finish(False, "Пусть друг откроет «Сетевая дуэль» → «Создать игру» и не закрывает этот "
                                      "экран, а потом проверьте снова.")
        if status == "error":
            self.step(False, name or "Ошибка подключения")
            return self.finish(False, name or "Не удалось подключиться.")

        # таймаут: либо брандмауэр друга молча не пускает, либо компьютер друга вообще недоступен
        self.step(False, "Игра друга не отвечает (таймаут)")
        mac = knows_mac(address)
        if mac:
            self.step(True, "Компьютер друга в сети виден")
            return self.finish(False, "Компьютер друга в сети есть, но его брандмауэр не пускает игру. "
                                      "Запустите у друга allow_firewall.bat и проверьте, что его Wi-Fi — "
                                      "«частная сеть». Если друг включал VPN — пусть выключит.")
        self.step(False if mac is False else None, "Компьютер друга в сети не виден")
        if not same_network:
            return self.finish(False, "Похоже, вы в разных сетях. Проверьте, что оба подключены к одному Wi-Fi "
                                      "(не к гостевому) и что адрес друга введён правильно.")
        return self.finish(False, "Устройства не видят друг друга. Проверьте адрес друга (он на его экране "
                                  "«Создать игру»). Если адрес верный — в роутере, скорее всего, включена "
                                  "«изоляция клиентов» (AP isolation), или один из вас в гостевой сети.")


def load_last_address():
    try:
        return json.loads(NETWORK_FILE.read_text(encoding="utf-8")).get("last_address", "")
    except (FileNotFoundError, ValueError):
        return ""


def save_last_address(address):
    try:
        NETWORK_FILE.write_text(json.dumps({"last_address": address}), encoding="utf-8")
    except OSError:
        pass


def new_seeds():
    return [random.randrange(1, 2 ** 31) for _ in range(ATTEMPTS)]


# --- Дуэль ---

class DuelSession:
    def __init__(self, connection, my_name, is_host):
        self.conn = connection
        self.my_name = my_name
        self.opp_name = "Соперник"
        self.is_host = is_host
        # handshake — знакомимся, countdown — отсчёт, play — попытка, pause — между попытками,
        # wait — свои попытки кончились, ждём соперника, results — итоги
        self.phase = "handshake"
        self.seeds = None
        self.timer = 0
        self.attempt = 0
        self.my_results = []
        self.opp_results = []
        self.game = None
        self.mirror = None          # мир соперника, который строим у себя
        self.mirror_attempt = -1
        self.want_rematch = False
        self.opp_rematch = False
        self.disconnected = False
        self.version_error = False
        self.finished = False
        self.canvas = pygame.Surface((WIDTH, HEIGHT + VIEW_EXTRA))
        self.conn.send({"type": "hello", "name": my_name, "protocol": PROTOCOL})

    # --- ход матча ---

    def start_match(self, seeds):
        self.seeds = seeds
        self.attempt = 0
        self.my_results = []
        self.opp_results = []
        self.mirror = None
        self.mirror_attempt = -1
        self.want_rematch = self.opp_rematch = False
        self.game = JumpGame(self.my_name, 0, seed=seeds[0], view_extra=VIEW_EXTRA)
        self.phase = "countdown"
        self.timer = COUNTDOWN

    def start_attempt(self):
        self.game = JumpGame(self.my_name, 0, seed=self.seeds[self.attempt], view_extra=VIEW_EXTRA)
        self.phase = "play"

    def check_rematch(self):
        """Реванш начинает хост, когда оба нажали R."""
        if self.is_host and self.want_rematch and self.opp_rematch:
            seeds = new_seeds()
            self.conn.send({"type": "start", "seeds": seeds})
            self.start_match(seeds)

    def handle_message(self, msg):
        kind = msg.get("type")
        if kind == "hello":
            self.opp_name = msg.get("name", "Соперник")[:12]
            if msg.get("protocol") != PROTOCOL:
                # разные версии игры построили бы разные уровни — играть нельзя
                self.version_error = True
                self.disconnected = True
                return
            if self.is_host and self.seeds is None:
                seeds = new_seeds()
                self.conn.send({"type": "start", "seeds": seeds})
                self.start_match(seeds)
        elif kind == "start":
            self.start_match(msg["seeds"])
        elif kind == "state" and self.seeds:
            attempt = msg["attempt"]
            if attempt != self.mirror_attempt:
                # соперник начал новую попытку — строим его новый мир
                self.mirror = JumpGame(self.opp_name, 0, seed=self.seeds[attempt], view_extra=VIEW_EXTRA)
                self.mirror_attempt = attempt
            self.mirror.apply_remote(msg)
        elif kind == "event" and self.mirror and msg["attempt"] == self.mirror_attempt:
            self.mirror.apply_event(msg["kind"], msg["id"])
        elif kind == "attempt_end":
            if len(self.opp_results) == msg["attempt"]:
                self.opp_results.append(msg["height"])
        elif kind == "rematch":
            self.opp_rematch = True
            self.check_rematch()
        elif kind == "bye":
            self.disconnected = True

    def update(self):
        for msg in self.conn.receive():
            self.handle_message(msg)
        if not self.conn.alive:
            self.disconnected = True
        if self.mirror:
            self.mirror.update_mirror()

        if self.phase == "countdown":
            self.timer -= 1
            if self.timer <= 0:
                self.phase = "play"
        elif self.phase == "play":
            game = self.game
            game.update()
            for event_kind, object_id in game.events:
                self.conn.send({"type": "event", "attempt": self.attempt, "kind": event_kind, "id": object_id})
            game.events.clear()
            if game.t % SEND_EVERY == 0 or game.over:
                self.conn.send({"type": "state", "attempt": self.attempt, **game.state_message()})
            if game.over:
                self.my_results.append(game.height_m)
                self.conn.send({"type": "attempt_end", "attempt": self.attempt, "height": game.height_m})
                self.phase = "pause"
                self.timer = PAUSE_BETWEEN
        elif self.phase == "pause":
            self.game.update()  # догорают искры и взрыв
            self.timer -= 1
            if self.timer <= 0:
                self.attempt += 1
                if self.attempt < ATTEMPTS:
                    self.start_attempt()
                else:
                    self.phase = "wait"
        elif self.phase == "wait":
            if len(self.opp_results) >= ATTEMPTS or self.disconnected:
                self.phase = "results"

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return
        if self.phase == "play" and event.key != pygame.K_ESCAPE:
            self.game.handle_event(event)  # бросок кинжала
        if event.key == pygame.K_ESCAPE:
            self.conn.send({"type": "bye"})
            self.finished = True
        elif event.key == pygame.K_r and self.phase == "results" and not self.disconnected:
            self.want_rematch = True
            self.conn.send({"type": "rematch"})
            self.check_rematch()

    # --- отрисовка ---

    def draw(self):
        screen.fill((12, 10, 24))
        self.draw_panel(self.game, 0, mine=True)
        self.draw_panel(self.mirror, PANEL_W, mine=False)
        pygame.draw.line(screen, GOLD_COLOR, (PANEL_W, PANEL_TOP), (PANEL_W, HEIGHT), 3)
        self.draw_score_bar()

        if self.version_error:
            self.draw_center_message("У соперника другая версия игры. Esc — в меню", RED_COLOR)
            return
        if self.phase == "handshake":
            self.draw_center_message("Знакомимся с соперником...")
        elif self.phase == "countdown":
            number = self.timer // 60 + 1
            text = big_font.render(str(number), True, GOLD_COLOR)
            screen.blit(text, text.get_rect(center=(WIDTH // 2, HEIGHT // 2)))
            draw_text("Кто прыгнет выше из трёх попыток?", font, HEIGHT // 2 + 50)
        elif self.phase == "results":
            self.draw_results()
        if self.disconnected and self.phase != "results":
            # на половине соперника — свои попытки можно доиграть
            self.draw_center_message("Соперник отключился", RED_COLOR, center_x=PANEL_W + PANEL_W // 2)

    def draw_panel(self, game, x, mine):
        rect = pygame.Rect(x, PANEL_TOP, PANEL_W, PANEL_H)
        if game is None:
            pygame.draw.rect(screen, (20, 18, 38), rect)
            label = small_font.render("Соперник ещё не начал", True, GRAY_COLOR)
            screen.blit(label, label.get_rect(center=rect.center))
            return
        # мир рисуем на высокий холст и уменьшаем в 2 раза — видно больше пространства вверху
        game.draw_world(self.canvas)
        screen.blit(pygame.transform.smoothscale(self.canvas, rect.size), rect)

        attempt = self.attempt if mine else self.mirror_attempt
        results = self.my_results if mine else self.opp_results
        height = small_font.render(f"{game.height_m} м", True, TEXT_COLOR)
        badge = pygame.Surface((height.get_width() + 16, 28), pygame.SRCALPHA)
        badge.fill((0, 0, 0, 140))
        screen.blit(badge, (x + 8, PANEL_TOP + 8))
        screen.blit(height, (x + 16, PANEL_TOP + 11))
        info = small_font.render(f"Попытка {min(attempt, ATTEMPTS - 1) + 1}/{ATTEMPTS}", True, GRAY_COLOR)
        screen.blit(info, info.get_rect(topright=(x + PANEL_W - 12, PANEL_TOP + 11)))

        # поверх — итог попытки или ожидание
        finished_attempt = len(results) > attempt or (mine and self.phase in ("pause", "wait", "results"))
        if finished_attempt and results:
            shade = pygame.Surface(rect.size, pygame.SRCALPHA)
            shade.fill((0, 0, 0, 120))
            screen.blit(shade, rect)
            index = min(attempt, len(results) - 1)
            line1 = font.render(f"Попытка {index + 1}: {results[index]} м", True, GOLD_COLOR)
            screen.blit(line1, line1.get_rect(center=(rect.centerx, rect.centery - 20)))
            if len(results) >= ATTEMPTS:
                note = "Все попытки сыграны" if mine else "Соперник закончил"
            else:
                note = "Следующая попытка скоро..." if mine else "Соперник начинает следующую"
            line2 = small_font.render(note, True, TEXT_COLOR)
            screen.blit(line2, line2.get_rect(center=(rect.centerx, rect.centery + 18)))

    def draw_score_bar(self):
        pygame.draw.rect(screen, (22, 18, 42), (0, 0, WIDTH, PANEL_TOP))
        for x, name, results, align in ((12, self.my_name, self.my_results, "left"),
                                        (WIDTH - 12, self.opp_name, self.opp_results, "right")):
            cells = [str(r) for r in results] + ["—"] * (ATTEMPTS - len(results))
            best = max(results) if results else 0
            text = small_font.render(f"{name}:  {'  ·  '.join(cells)}   лучшая {best} м", True, TEXT_COLOR)
            rect = text.get_rect(midleft=(x, PANEL_TOP // 2)) if align == "left" else \
                text.get_rect(midright=(x, PANEL_TOP // 2))
            screen.blit(text, rect)
        vs = font.render("VS", True, GOLD_COLOR)
        screen.blit(vs, vs.get_rect(center=(WIDTH // 2, PANEL_TOP // 2)))

    def draw_center_message(self, text, color=TEXT_COLOR, center_x=WIDTH // 2):
        surface = font.render(text, True, color)
        box = surface.get_rect(center=(center_x, HEIGHT // 2)).inflate(40, 24)
        pygame.draw.rect(screen, (15, 12, 30), box, border_radius=12)
        pygame.draw.rect(screen, color, box, 2, border_radius=12)
        screen.blit(surface, surface.get_rect(center=box.center))

    def draw_results(self):
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((8, 6, 18, 235))
        screen.blit(shade, (0, 0))
        my_best = max(self.my_results, default=0)
        opp_best = max(self.opp_results, default=0)
        if my_best > opp_best:
            title, color = "Победа!", GREEN_COLOR
        elif my_best < opp_best:
            title, color = "Поражение", RED_COLOR
        else:
            title, color = "Ничья", GOLD_COLOR
        draw_text(title, big_font, 90, color)

        # таблица: имя, три попытки, лучшая
        columns = [170, 400, 470, 540, 630]
        y = 210
        for i, header in enumerate(["", "1", "2", "3", "Лучшая"]):
            if header:
                surf = small_font.render(header, True, GRAY_COLOR)
                screen.blit(surf, surf.get_rect(center=(columns[i], y)))
        for row, (name, results, best) in enumerate(((self.my_name, self.my_results, my_best),
                                                     (self.opp_name, self.opp_results, opp_best))):
            y = 260 + row * 50
            screen.blit(font.render(name, True, TEXT_COLOR), (columns[0] - 60, y - 18))
            cells = [str(r) for r in results] + ["—"] * (ATTEMPTS - len(results))
            for i, cell in enumerate(cells):
                surf = font.render(cell, True, TEXT_COLOR)
                screen.blit(surf, surf.get_rect(center=(columns[i + 1], y)))
            winner = best == max(my_best, opp_best) and my_best != opp_best
            surf = font.render(f"{best} м", True, GOLD_COLOR if winner else TEXT_COLOR)
            screen.blit(surf, surf.get_rect(center=(columns[4], y)))

        if self.disconnected:
            draw_text("Соперник отключился", small_font, 400, RED_COLOR)
            draw_text("Esc — в меню", font, 450)
        elif self.want_rematch:
            draw_text("Ждём, согласится ли соперник на реванш...", small_font, 410, GRAY_COLOR)
            draw_text("Esc — в меню", font, 450)
        else:
            if self.opp_rematch:
                draw_text(f"{self.opp_name} хочет реванш!", small_font, 410, GOLD_COLOR)
            draw_text("R — реванш    Esc — в меню", font, 450)


# --- Лобби: создать игру или найти чужую ---

def draw_wrapped_center(text, fnt, y, color, max_width=WIDTH - 80):
    """Текст по центру с переносом слов. Возвращает y под текстом."""
    lines, line = [], ""
    for word in text.split():
        if fnt.size(f"{line} {word}")[0] > max_width and line:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    lines.append(line)
    for text_line in lines:
        draw_text(text_line, fnt, y, color)
        y += fnt.get_linesize()
    return y


class NetScreen:
    """Все экраны сетевой игры. Когда finished == True — пора вернуться в главное меню."""

    BUTTONS = ["Создать игру", "Найти игру", "Проверка связи", "Назад"]
    MANUAL = "Ввести IP вручную"

    def __init__(self, player_name):
        self.player_name = player_name
        # choose — главный выбор, host — ждём соперника, lobby — список найденных игр,
        # manual — ввод IP, connecting — подключаемся, error — ошибка, duel — идёт дуэль,
        # diag_input — ввод адреса друга для проверки, diag — результаты проверки связи
        self.mode = "choose"
        self.diag = None
        self.own_ips = local_ips()
        self.selected = 0
        self.host = None
        self.announcer = None
        self.finder = None
        self.joiner = None
        self.session = None
        self.address = load_last_address()
        self.target_name = ""
        self.ips = []
        self.warning = None
        self.error = ""
        self.finished = False

    # --- переходы ---

    def choose(self, index):
        if index == 0:
            self.start_hosting()
        elif index == 1:
            self.finder = Finder()
            self.warning = vpn_warning()
            self.selected = 0
            self.mode = "lobby"
        elif index == 2:
            pygame.key.start_text_input()
            self.mode = "diag_input"
        else:
            self.finished = True

    def start_hosting(self):
        try:
            self.host = Host(self.player_name)
        except OSError as e:
            self.show_error(f"Не удалось открыть порт {PORT}: {e}. Может, игра уже создана в другом окне?")
            return
        try:
            self.announcer = Announcer(self.player_name)
        except OSError:
            self.announcer = None  # без лобби, но по IP подключиться всё равно можно
        self.ips = local_ips()
        self.warning = vpn_warning()
        self.mode = "host"

    def join(self, address, name=""):
        self.address = address
        self.target_name = name or address
        self.stop_finder()
        pygame.key.stop_text_input()
        self.joiner = Joiner(address)
        self.mode = "connecting"

    def stop_hosting(self):
        if self.host:
            self.host.close()
            self.host = None
        if self.announcer:
            self.announcer.close()
            self.announcer = None

    def stop_finder(self):
        if self.finder:
            self.finder.close()
            self.finder = None

    def show_error(self, text):
        self.stop_hosting()
        self.stop_finder()
        self.error = text
        self.mode = "error"

    def start_duel(self, connection, is_host):
        if is_host and self.announcer:
            self.announcer.close()  # игра началась — в лобби у других она больше не нужна
            self.announcer = None
        self.session = DuelSession(connection, self.player_name, is_host)
        self.mode = "duel"

    def back_to_choose(self):
        self.stop_hosting()
        self.stop_finder()
        pygame.key.stop_text_input()
        self.joiner = None
        self.selected = 0
        self.mode = "choose"

    # --- списки кнопок ---

    def menu_items(self):
        """Кнопки текущего экрана: (текст, действие)."""
        if self.mode == "choose":
            return [(text, lambda i=i: self.choose(i)) for i, text in enumerate(self.BUTTONS)]
        if self.mode == "lobby":
            items = []
            for ip, info in self.finder.visible()[:4]:
                label = f"{info['name']}  —  {ip}"
                if info["protocol"] != PROTOCOL:
                    label += "  (другая версия)"
                items.append((label, lambda ip=ip, name=info["name"]: self.join(ip, name)))
            items.append((self.MANUAL, self.open_manual))
            return items
        return []

    def item_rects(self):
        count = len(self.menu_items())
        width = 320 if self.mode == "choose" else 480
        return [pygame.Rect(WIDTH // 2 - width // 2, 200 + i * 68, width, 56) for i in range(count)]

    def open_manual(self):
        self.stop_finder()
        pygame.key.start_text_input()
        self.mode = "manual"

    # --- события и логика ---

    def handle_event(self, event):
        if self.mode == "duel":
            self.session.handle_event(event)
            if self.session.finished:
                self.finished = True
            return

        items = self.menu_items()
        if items:
            self.selected = min(self.selected, len(items) - 1)
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    self.selected = (self.selected - 1) % len(items)
                elif event.key == pygame.K_DOWN:
                    self.selected = (self.selected + 1) % len(items)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    items[self.selected][1]()
                elif event.key == pygame.K_ESCAPE:
                    if self.mode == "choose":
                        self.finished = True
                    else:
                        self.back_to_choose()
            elif event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
                for i, rect in enumerate(self.item_rects()):
                    if rect.collidepoint(event.pos):
                        self.selected = i
                        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                            items[i][1]()
                            return
            return

        if self.mode in ("manual", "diag_input"):
            if event.type == pygame.TEXTINPUT:
                # IP-адрес: цифры и точки (буквы — если подключаются по имени компьютера)
                allowed = "".join(ch for ch in event.text if ch.isalnum() or ch in ".-")
                self.address = (self.address + allowed)[:40]
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_BACKSPACE:
                    self.address = self.address[:-1]
                elif event.key == pygame.K_RETURN and self.address.strip():
                    if self.mode == "manual":
                        self.join(self.address.strip())
                    else:
                        pygame.key.stop_text_input()
                        save_last_address(self.address.strip())
                        self.diag = Diagnostics(self.address.strip())
                        self.mode = "diag"
                elif event.key == pygame.K_ESCAPE:
                    self.back_to_choose()
        elif self.mode == "diag" and event.type == pygame.KEYDOWN:
            if event.key == pygame.K_r and self.diag.done:
                self.diag = Diagnostics(self.diag.address)  # проверить снова
            elif event.key in (pygame.K_ESCAPE, pygame.K_RETURN):
                self.back_to_choose()
        elif event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_RETURN) \
                and self.mode in ("host", "connecting", "error"):
            if self.mode != "host" or event.key == pygame.K_ESCAPE:
                self.back_to_choose()

    def update(self):
        if self.mode == "host":
            if self.host.connection:
                self.start_duel(self.host.connection, is_host=True)
            elif self.host.error:
                self.show_error(f"Ошибка ожидания: {self.host.error}")
        elif self.mode == "lobby":
            self.finder.update()
        elif self.mode == "connecting":
            if self.joiner.connection:
                save_last_address(self.address)
                self.start_duel(self.joiner.connection, is_host=False)
            elif self.joiner.error:
                self.show_error(f"Не удалось подключиться к {self.target_name}. {self.joiner.error}")
        elif self.mode == "duel":
            self.session.update()

    def close(self):
        """Закрыть всё сетевое при выходе в меню."""
        pygame.key.stop_text_input()
        self.stop_hosting()
        self.stop_finder()
        if self.session:
            self.session.conn.close()

    # --- отрисовка ---

    def draw(self):
        if self.mode == "duel":
            self.session.draw()
            return
        screen.fill((30, 30, 40))
        draw_text("Сетевая дуэль", big_font, 50, GOLD_COLOR)
        draw_text("Прыжки Сларка: кто выше из трёх попыток", small_font, 128, GRAY_COLOR)

        for i, ((text, _), rect) in enumerate(zip(self.menu_items(), self.item_rects())):
            draw_button(rect, text, i == self.selected)

        if self.mode == "choose":
            if self.own_ips:
                draw_text("Ваш адрес в сети: " + ",  ".join(self.own_ips), small_font, 490, TEXT_COLOR)
            draw_text("Оба компьютера должны быть в одной сети (например, от одного Wi-Fi)", small_font, 525,
                      GRAY_COLOR)
        elif self.mode == "diag_input":
            draw_text("Проверка связи с другом", font, 180)
            draw_text("Адрес друга — он виден у друга на этом же экране («Ваш адрес в сети»)", small_font, 225,
                      GRAY_COLOR)
            field = pygame.Rect(WIDTH // 2 - 200, 270, 400, 60)
            pygame.draw.rect(screen, CARD_COLOR, field, border_radius=12)
            pygame.draw.rect(screen, GOLD_COLOR, field, 3, border_radius=12)
            cursor = "|" if pygame.time.get_ticks() // 500 % 2 == 0 else " "
            surface = font.render(self.address + cursor, True, TEXT_COLOR)
            screen.blit(surface, surface.get_rect(midleft=(field.x + 16, field.centery)))
            draw_text("Лучше, если друг сначала нажмёт «Создать игру».   Enter — проверить   Esc — назад",
                      small_font, 360, GRAY_COLOR)
        elif self.mode == "diag":
            self.draw_diagnostics()
        elif self.mode == "lobby":
            dots = "." * (pygame.time.get_ticks() // 500 % 4)
            found = len(self.finder.visible())
            status = f"Найдено игр: {found}" if found else f"Ищем игры в сети{dots}"
            draw_text(status, font, 160 - 4)
            if not found:
                draw_text("Попросите друга нажать «Создать игру» — она появится здесь сама", small_font, 480,
                          GRAY_COLOR)
        elif self.mode == "host":
            dots = "." * (pygame.time.get_ticks() // 500 % 4)
            draw_text(f"Ждём второго игрока{dots}", font, 200)
            if self.announcer:
                draw_text("Ваша игра видна в лобби: другу нужно нажать «Найти игру»", small_font, 250, TEXT_COLOR)
            if self.ips:
                draw_text("Если не находит — пусть введёт адрес вручную:", small_font, 290, GRAY_COLOR)
                draw_text("   ".join(self.ips[:3]), font, 320, GOLD_COLOR)
            draw_text("Esc — отмена", small_font, 555, GRAY_COLOR)
        elif self.mode == "manual":
            draw_text("IP-адрес хоста:", font, 210)
            field = pygame.Rect(WIDTH // 2 - 200, 270, 400, 60)
            pygame.draw.rect(screen, CARD_COLOR, field, border_radius=12)
            pygame.draw.rect(screen, GOLD_COLOR, field, 3, border_radius=12)
            cursor = "|" if pygame.time.get_ticks() // 500 % 2 == 0 else " "
            surface = font.render(self.address + cursor, True, TEXT_COLOR)
            screen.blit(surface, surface.get_rect(midleft=(field.x + 16, field.centery)))
            draw_text("Например: 192.168.1.5    Enter — подключиться    Esc — назад", small_font, 360, GRAY_COLOR)
        elif self.mode == "connecting":
            dots = "." * (pygame.time.get_ticks() // 500 % 4)
            draw_text(f"Подключаемся к {self.target_name}{dots}", font, 260)
            draw_text("Esc — отмена", small_font, 320, GRAY_COLOR)
        elif self.mode == "error":
            y = draw_wrapped_center(self.error, small_font, 220, RED_COLOR)
            draw_text("Enter или Esc — назад", font, max(y + 30, 420))

        # предупреждение про VPN — на экранах, где это может помешать
        if self.warning and self.mode in ("host", "lobby", "manual"):
            draw_wrapped_center(self.warning, small_font, 390 if self.mode == "host" else 410, RED_COLOR)

    def draw_diagnostics(self):
        diag = self.diag
        draw_text(f"Проверка связи с {diag.address}", font, 160)
        y = 205
        for ok, text in diag.steps:
            color = GREEN_COLOR if ok else RED_COLOR if ok is False else GRAY_COLOR
            pygame.draw.circle(screen, color, (130, y + 12), 7)
            screen.blit(small_font.render(text, True, TEXT_COLOR), (150, y))
            y += 30
        if not diag.done:
            dots = "." * (pygame.time.get_ticks() // 500 % 4)
            screen.blit(small_font.render(f"проверяем{dots}", True, GRAY_COLOR), (150, y))
            return
        box = pygame.Rect(60, y + 12, WIDTH - 120, 0)
        text_y = y + 24
        # итог — в рамке зелёного или красного цвета
        end_y = draw_wrapped_center(diag.verdict, small_font, text_y, TEXT_COLOR, max_width=WIDTH - 160)
        box.height = end_y - box.y + 12
        pygame.draw.rect(screen, GREEN_COLOR if diag.verdict_ok else RED_COLOR, box, 2, border_radius=10)
        draw_text("R — проверить снова    Esc — назад", small_font, min(end_y + 30, 565), GRAY_COLOR)
