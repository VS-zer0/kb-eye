#!/usr/bin/env python3
"""
gaze_demo.py — калибровка и визуализация взгляда через gaze_service

Запуск:
    python gaze_demo.py
    python gaze_demo.py --exe ./gaze_service.exe --port 5765 --camera 0

Зависимости:
    pip install pygame opencv-python mediapipe numpy
"""
import argparse
import json
import math
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

import cv2
from mediapipe.python.solutions import face_mesh as _mp_face_mesh
import numpy as np
import pygame

# ─── Цвета ───────────────────────────────────────────────────────────────────
BG           = (  0,   0,   0)
PANEL_BG     = ( 10,  10,  10)
PANEL_BRD    = ( 35,  35,  35)
CURSOR_C     = (  0, 255, 136)
CURSOR_DIM   = (  0,  55,  30)
CALIB_DOT    = (255, 255, 255)
CALIB_RING   = (255, 107,   0)
CALIB_DONE   = (  0, 210,  90)
LANDMARK_C   = (  0, 255, 136)
MESH_C       = (  0,  45,  22)
TEXT         = (180, 180, 180)
TEXT_HL      = (255, 255, 255)
TEXT_DIM     = ( 70,  70,  70)
ON_SCR       = (  0, 210,  90)
OFF_SCR      = (240,  90,   0)


# ─── Вспомогательная функция: цвет между двумя цветами ───────────────────────
def lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


# ─── Поток: лицевые ориентиры через собственный захват камеры ─────────────────
class FaceThread(threading.Thread):
    """
    Открывает камеру независимо от gaze_service и рисует ориентиры MediaPipe.
    Если камера недоступна — работает в режиме 3D-каркаса на основе head_pose.
    """
    CONTOUR_IDS = [
        10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288,
        397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136,
        172, 58,  132, 93,  234, 127, 162, 21,  54,  103, 67,  109,
    ]
    EYE_L = [362, 385, 387, 263, 373, 380]
    EYE_R = [33,  160, 158, 133, 153, 144]
    NOSE  = [1, 2, 5, 4, 195]
    LIPS  = [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291,
             308, 324, 318, 402, 317, 14, 87, 178, 88, 95, 78]

    def __init__(self, camera_id: int, out_size=(220, 160)):
        super().__init__(daemon=True)
        self.camera_id = camera_id
        self.out_w, self.out_h = out_size
        self.surface: pygame.Surface | None = None
        self.available = False
        self.running   = True
        self._lock     = threading.Lock()

    def stop(self):
        self.running = False

    def get_surface(self):
        with self._lock:
            return self.surface

    def run(self):
        cap = cv2.VideoCapture(self.camera_id)
        if not cap.isOpened():
            return
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  320)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)

        fm = _mp_face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.available = True

        while self.running:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.02)
                continue

            frame = cv2.flip(frame, 1)
            h, w  = frame.shape[:2]
            rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res   = fm.process(rgb)

            # Тёмный фон вместо сырого кадра — визуальный стиль
            canvas = np.zeros((h, w, 3), dtype=np.uint8)
            canvas[:] = (10, 10, 10)

            if res.multi_face_landmarks:
                lms = res.multi_face_landmarks[0].landmark

                def px(idx):
                    return int(lms[idx].x * w), int(lms[idx].y * h)

                # Сетка полного меша (тонкие линии)
                for conn in _mp_face_mesh.FACEMESH_TESSELATION:
                    cv2.line(canvas, px(conn[0]), px(conn[1]),
                             (0, 40, 20), 1, cv2.LINE_AA)

                # Контур лица
                for i in range(len(self.CONTOUR_IDS) - 1):
                    cv2.line(canvas, px(self.CONTOUR_IDS[i]),
                             px(self.CONTOUR_IDS[i+1]),
                             (0, 100, 55), 1, cv2.LINE_AA)

                # Глаза
                for group in (self.EYE_L, self.EYE_R):
                    pts = np.array([px(i) for i in group], np.int32)
                    cv2.polylines(canvas, [pts], True, (0, 200, 100), 1, cv2.LINE_AA)

                # Нос
                pts = np.array([px(i) for i in self.NOSE], np.int32)
                cv2.polylines(canvas, [pts], False, (0, 180, 90), 1, cv2.LINE_AA)

                # Губы
                pts = np.array([px(i) for i in self.LIPS], np.int32)
                cv2.polylines(canvas, [pts], True, (0, 160, 80), 1, cv2.LINE_AA)

                # Ключевые точки (яркие кружки)
                for idx in [1, 33, 263, 61, 291, 199]:
                    x, y = px(idx)
                    cv2.circle(canvas, (x, y), 3, (0, 255, 136), -1, cv2.LINE_AA)

            # Масштабирование в out_size
            small = cv2.resize(canvas, (self.out_w, self.out_h))

            # BGR → RGB → pygame Surface
            surf = pygame.surfarray.make_surface(
                np.transpose(small, (1, 0, 2)))

            with self._lock:
                self.surface = surf

        cap.release()
        fm.close()


# ─── 3D-каркас головы (запасной режим без камеры) ────────────────────────────

# Вершины упрощённой головы (в нормированном пространстве –1..1)
def _oval(cx, cy, cz, rx, ry, n=20):
    pts = []
    for i in range(n):
        a = 2 * math.pi * i / n
        pts.append([cx + rx * math.cos(a), cy + ry * math.sin(a), cz])
    return pts

_HEAD_RINGS = [
    _oval(0,  0.40, 0, 0.55, 0.65, 24),   # лоб
    _oval(0,  0.10, 0, 0.70, 0.70, 24),   # средний ряд
    _oval(0, -0.25, 0, 0.65, 0.65, 24),   # скулы
    _oval(0, -0.60, 0, 0.45, 0.45, 24),   # подбородок
]
_EYE_L_3D = _oval(-0.25, 0.12, 0.52, 0.14, 0.09, 12)
_EYE_R_3D = _oval( 0.25, 0.12, 0.52, 0.14, 0.09, 12)
_NOSE_3D  = [[0, 0.05, 0.65], [-0.1, -0.15, 0.60], [0.1, -0.15, 0.60], [0, 0.05, 0.65]]
_MOUTH_3D = _oval(0, -0.32, 0.58, 0.20, 0.06, 14)


def _rot_point(p, rx, ry, rz):
    """Вращение вокруг X, Y, Z (в радианах)."""
    x, y, z = p
    # X (pitch)
    y2 = y * math.cos(rx) - z * math.sin(rx)
    z2 = y * math.sin(rx) + z * math.cos(rx)
    y, z = y2, z2
    # Y (yaw)
    x2 = x * math.cos(ry) + z * math.sin(ry)
    z2 = -x * math.sin(ry) + z * math.cos(ry)
    x, z = x2, z2
    # Z (roll)
    x2 = x * math.cos(rz) - y * math.sin(rz)
    y2 = x * math.sin(rz) + y * math.cos(rz)
    return x2, y2, z2


def _proj(p, cx, cy, scale=60, fov=2.5):
    x, y, z = p
    d = fov / (fov + z + 1.5)
    return int(cx + x * scale * d), int(cy - y * scale * d)


def draw_head_wireframe(surf: pygame.Surface, yaw, pitch, roll, rect: pygame.Rect):
    cx = rect.centerx
    cy = rect.centery
    sc = rect.width * 0.36

    rx = math.radians(pitch)
    ry = math.radians(yaw)
    rz = math.radians(roll)

    def draw_loop(pts, color, closed=True):
        screen_pts = [_proj(_rot_point(p, rx, ry, rz), cx, cy, sc) for p in pts]
        if len(screen_pts) > 1:
            pygame.draw.lines(surf, color, closed, screen_pts, 1)

    # Кольца головы
    for ring in _HEAD_RINGS:
        draw_loop(ring, MESH_C)

    # Вертикальные рёбра между кольцами
    for i in range(len(_HEAD_RINGS) - 1):
        r0, r1 = _HEAD_RINGS[i], _HEAD_RINGS[i + 1]
        step = len(r0) // 8
        for j in range(0, len(r0), step):
            p0 = _proj(_rot_point(r0[j], rx, ry, rz), cx, cy, sc)
            p1 = _proj(_rot_point(r1[j], rx, ry, rz), cx, cy, sc)
            pygame.draw.line(surf, MESH_C, p0, p1, 1)

    # Глаза, нос, рот
    draw_loop(_EYE_L_3D, LANDMARK_C)
    draw_loop(_EYE_R_3D, LANDMARK_C)
    draw_loop(_MOUTH_3D, LANDMARK_C)

    # Ось носа (маленькая точка)
    nose_tip = _proj(_rot_point([0, 0, 0.75], rx, ry, rz), cx, cy, sc)
    pygame.draw.circle(surf, LANDMARK_C, nose_tip, 3)


# ─── TCP-клиент GTM ───────────────────────────────────────────────────────────
class GtmClient:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self._sock: socket.socket | None = None
        self._lock  = threading.Lock()
        self.queue: deque = deque(maxlen=256)
        self._thread: threading.Thread | None = None
        self.connected = False

    def connect(self, retries=15, delay=0.4) -> bool:
        for _ in range(retries):
            try:
                s = socket.create_connection((self.host, self.port), timeout=2)
                s.settimeout(None)
                self._sock = s
                self.connected = True
                self._thread = threading.Thread(
                    target=self._read_loop, daemon=True)
                self._thread.start()
                return True
            except OSError:
                time.sleep(delay)
        return False

    def send(self, obj: dict):
        if not self._sock:
            return
        try:
            with self._lock:
                self._sock.sendall(
                    (json.dumps(obj, ensure_ascii=False) + '\n').encode())
        except OSError:
            pass

    def _read_loop(self):
        buf = b''
        while True:
            try:
                chunk = self._sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b'\n' in buf:
                    line, buf = buf.split(b'\n', 1)
                    try:
                        self.queue.append(json.loads(line.decode()))
                    except json.JSONDecodeError:
                        pass
            except OSError:
                break
        self.connected = False

    def pop_all(self) -> list[dict]:
        msgs = []
        while self.queue:
            msgs.append(self.queue.popleft())
        return msgs


# ─── Рендер вспомогательных функций ──────────────────────────────────────────
def draw_glow(surf, color, center, radius, alpha=80):
    """Простое свечение через несколько концентрических полупрозрачных кругов."""
    glow = pygame.Surface((radius * 4, radius * 4), pygame.SRCALPHA)
    for r in range(radius * 2, 0, -1):
        a = int(alpha * (1 - r / (radius * 2)) ** 2)
        pygame.draw.circle(glow, (*color, a),
                           (radius * 2, radius * 2), r)
    surf.blit(glow, (center[0] - radius * 2, center[1] - radius * 2),
              special_flags=pygame.BLEND_RGBA_ADD)


def draw_panel(surf, rect, title=None, font=None):
    pygame.draw.rect(surf, PANEL_BG,  rect, border_radius=8)
    pygame.draw.rect(surf, PANEL_BRD, rect, 1, border_radius=8)
    if title and font:
        lbl = font.render(title, True, TEXT_DIM)
        surf.blit(lbl, (rect.x + 10, rect.y + 8))


def bar(surf, rect, value, color_lo, color_hi):
    pygame.draw.rect(surf, PANEL_BRD, rect, border_radius=3)
    fill = rect.inflate(-2, -2)
    fill.width = max(4, int(fill.width * value))
    col = lerp_color(color_lo, color_hi, value)
    pygame.draw.rect(surf, col, fill, border_radius=2)


# ─── Главная функция ──────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--exe',    default='./gaze_service.exe')
    ap.add_argument('--port',   type=int, default=5765)
    ap.add_argument('--host',   default='127.0.0.1')
    ap.add_argument('--camera', type=int, default=0)
    args = ap.parse_args()

    # ── Запуск gaze_service ───────────────────────────────────────────────────
    exe_path = Path(args.exe)
    proc = None
    if exe_path.exists():
        proc = subprocess.Popen(
            [str(exe_path), '--port', str(args.port),
             '--camera', str(args.camera)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f'[demo] Запущен {exe_path} (pid={proc.pid})')
    else:
        print(f'[demo] {exe_path} не найден — ожидаем уже запущенный сервис')

    # ── Pygame ────────────────────────────────────────────────────────────────
    pygame.init()
    info  = pygame.display.Info()
    W, H  = info.current_w, info.current_h
    surf  = pygame.display.set_mode((W, H), pygame.NOFRAME)
    pygame.display.set_caption('Gaze Demo')
    clock = pygame.time.Clock()

    font_s = pygame.font.SysFont('Consolas', 13)
    font_m = pygame.font.SysFont('Consolas', 16)
    font_l = pygame.font.SysFont('Consolas', 22, bold=True)
    font_xl= pygame.font.SysFont('Consolas', 32, bold=True)

    # ── Камера для лицевого блока ─────────────────────────────────────────────
    FACE_W, FACE_H = 220, 160
    face_thread = FaceThread(args.camera, (FACE_W, FACE_H))
    face_thread.start()
    time.sleep(0.3)  # дадим время FaceThread открыть камеру

    # ── TCP-клиент ────────────────────────────────────────────────────────────
    gtm = GtmClient(args.host, args.port)
    print('[demo] Подключаемся к GTM...')
    if not gtm.connect(retries=20, delay=0.5):
        print('[demo] Не удалось подключиться. Завершение.')
        pygame.quit()
        if proc:
            proc.terminate()
        sys.exit(1)
    print('[demo] Подключено.')

    # Сообщаем GTM размер экрана и запускаем калибровку
    gtm.send({'type': 'set_screen_bounds',
              'width_px': W, 'height_px': H, 'dpi': 96})
    gtm.send({'type': 'start_calibration'})

    # ── Состояние ─────────────────────────────────────────────────────────────
    state = 'CALIBRATING'   # CALIBRATING → RUNNING

    calib_pt   = None        # {'x':, 'y':, 'index':, 'total':}
    calib_dwell= 0.0         # время фиксации текущей точки (сек)
    calib_msg  = ''
    DWELL_TIME = 1.5

    gaze_x, gaze_y = 0.5, 0.5
    confidence     = 0.0
    on_screen      = True
    head_pose      = {'yaw': 0.0, 'pitch': 0.0, 'roll': 0.0}
    calib_accuracy = None

    trail: deque = deque(maxlen=35)   # [(sx, sy, age)]
    trail_timer  = 0.0

    # Панели
    PANEL_PAD = 14
    INFO_W, INFO_H = 260, 160
    info_rect = pygame.Rect(W - INFO_W - PANEL_PAD,
                            H - INFO_H - PANEL_PAD,
                            INFO_W, INFO_H)
    face_rect = pygame.Rect(PANEL_PAD,
                            H - FACE_H - PANEL_PAD,
                            FACE_W, FACE_H)

    running = True
    t_last  = time.time()

    while running:
        dt = time.time() - t_last
        t_last = time.time()

        # ── События ──────────────────────────────────────────────────────────
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            if ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_ESCAPE, pygame.K_q):
                    running = False
                if ev.key == pygame.K_r and state == 'RUNNING':
                    # Перекалибровка
                    gtm.send({'type': 'start_calibration'})
                    state       = 'CALIBRATING'
                    calib_pt    = None
                    calib_msg   = ''
                    trail.clear()

        # ── Разбор сообщений GTM ──────────────────────────────────────────────
        for msg in gtm.pop_all():
            t = msg.get('type')

            if t == 'calibration_point':
                calib_pt    = msg
                calib_dwell = 0.0

            elif t == 'calibration_complete':
                calib_accuracy = msg.get('accuracy_cm')
                calib_msg = (f'Калибровка завершена  '
                             f'±{calib_accuracy:.1f} см' if calib_accuracy
                             else 'Калибровка завершена')
                state    = 'RUNNING'
                calib_pt = None

            elif t == 'module_status':
                if msg.get('state') == 'error':
                    calib_msg = 'Ошибка захвата камеры'

            elif t == 'gaze_update':
                gaze_x     = msg.get('x', 0.5)
                gaze_y     = msg.get('y', 0.5)
                confidence = msg.get('confidence', 0.0)
                on_screen  = msg.get('on_screen', True)
                hp         = msg.get('head_pose', {})
                head_pose  = {
                    'yaw':   hp.get('yaw',   0.0),
                    'pitch': hp.get('pitch', 0.0),
                    'roll':  hp.get('roll',  0.0),
                }

        # ── Экранные координаты взгляда ───────────────────────────────────────
        gx = int(gaze_x * W)
        gy = int(gaze_y * H)

        # ── Хвост взгляда ─────────────────────────────────────────────────────
        if state == 'RUNNING':
            trail_timer += dt
            if trail_timer > 0.04:
                trail_timer = 0.0
                trail.appendleft((gx, gy, 0.0))
            trail = deque(
                [(x, y, age + dt) for x, y, age in trail],
                maxlen=35)

        # ── Обновление дрожания калибровочной точки ───────────────────────────
        if calib_pt and state == 'CALIBRATING':
            calib_dwell += dt

        # ════════════════════════════════════════════════════════════════════
        # РЕНДЕР
        # ════════════════════════════════════════════════════════════════════
        surf.fill(BG)

        if state == 'CALIBRATING':
            # ── Заголовок ─────────────────────────────────────────────────────
            title = font_xl.render('КАЛИБРОВКА', True, TEXT)
            surf.blit(title, (W // 2 - title.get_width() // 2, 40))

            hint = font_s.render(
                'Смотрите на белую точку  ·  ESC — выход', True, TEXT_DIM)
            surf.blit(hint, (W // 2 - hint.get_width() // 2, 88))

            if calib_pt:
                px = int(calib_pt['x'] * W)
                py = int(calib_pt['y'] * H)
                idx   = calib_pt.get('index', 0)
                total = calib_pt.get('total', 25)

                # Прогресс-дуга вокруг точки
                progress = min(calib_dwell / DWELL_TIME, 1.0)
                RING_R   = 36
                DOT_R    = 10

                # Свечение
                draw_glow(surf, CALIB_RING, (px, py), RING_R * 2, 40)

                # Кольцо прогресса (рисуем дугами)
                ring_surf = pygame.Surface((RING_R * 2 + 8, RING_R * 2 + 8),
                                           pygame.SRCALPHA)
                end_angle = -90 + 360 * progress
                pygame.draw.arc(ring_surf, (*CALIB_RING, 200),
                                (4, 4, RING_R * 2, RING_R * 2),
                                math.radians(-90),
                                math.radians(end_angle),
                                4)
                surf.blit(ring_surf,
                          (px - RING_R - 4, py - RING_R - 4))

                # Белый кружок
                done_col = lerp_color(CALIB_DOT, CALIB_DONE, progress)
                pygame.draw.circle(surf, done_col, (px, py), DOT_R)
                pygame.draw.circle(surf, BG, (px, py), DOT_R - 4)
                pygame.draw.circle(surf, done_col, (px, py), 4)

                # Счётчик
                cnt = font_m.render(f'{idx + 1} / {total}', True, TEXT_DIM)
                surf.blit(cnt, (W // 2 - cnt.get_width() // 2, H - 80))

        else:  # RUNNING
            # ── Хвост ─────────────────────────────────────────────────────────
            for tx, ty, age in list(trail)[1:]:
                max_age = 1.2
                if age > max_age:
                    continue
                alpha   = 1.0 - age / max_age
                r       = max(2, int(8 * alpha))
                col     = lerp_color(BG, CURSOR_DIM, alpha ** 0.5)
                pygame.draw.circle(surf, col, (tx, ty), r)

            # ── Курсор взгляда ────────────────────────────────────────────────
            if confidence > 0.1:
                draw_glow(surf, CURSOR_C, (gx, gy), 50, int(60 * confidence))
                pygame.draw.circle(surf, CURSOR_C, (gx, gy), 10)
                pygame.draw.circle(surf, BG, (gx, gy), 6)
                pygame.draw.circle(surf, CURSOR_C, (gx, gy), 3)
            else:
                pygame.draw.circle(surf, TEXT_DIM, (gx, gy), 8, 1)

            # Подсказка
            hint = font_s.render(
                'R — перекалибровать  ·  ESC — выход', True, TEXT_DIM)
            surf.blit(hint, (W // 2 - hint.get_width() // 2, H - 44))

        # ── Сообщение об окончании калибровки ────────────────────────────────
        if calib_msg:
            msg_surf = font_m.render(calib_msg, True, CALIB_DONE)
            surf.blit(msg_surf,
                      (W // 2 - msg_surf.get_width() // 2, H // 2 - 60))

        # ── Лицевая панель (нижний левый угол) ───────────────────────────────
        draw_panel(surf, face_rect, 'ЛИЦО', font_s)
        inner_face = face_rect.inflate(-2, -2)

        face_surf = face_thread.get_surface()
        if face_surf is not None:
            # Масштабируем к внутренней области панели
            fs = pygame.transform.scale(face_surf, inner_face.size)
            surf.blit(fs, inner_face.topleft)
            pygame.draw.rect(surf, PANEL_BRD, face_rect, 1, border_radius=8)
        else:
            # Запасной режим: 3D-каркас из head_pose
            draw_head_wireframe(
                surf,
                head_pose['yaw'],
                head_pose['pitch'],
                head_pose['roll'],
                inner_face,
            )
            mode_lbl = font_s.render('3D  (камера занята)', True, TEXT_DIM)
            surf.blit(mode_lbl, (face_rect.x + 6, face_rect.bottom - 18))

        # ── Информационная панель (нижний правый угол) ────────────────────────
        draw_panel(surf, info_rect, 'ДАННЫЕ', font_s)

        ix = info_rect.x + 12
        iy = info_rect.y + 26

        # Статус
        s_col  = ON_SCR if on_screen else OFF_SCR
        s_text = 'НА ЭКРАНЕ' if on_screen else 'НА КЛАВИАТУРЕ'
        if state == 'CALIBRATING':
            s_col, s_text = TEXT_DIM, 'КАЛИБРОВКА'
        lbl = font_m.render(s_text, True, s_col)
        surf.blit(lbl, (ix, iy))
        iy += 28

        # Уверенность
        surf.blit(font_s.render('Уверенность', True, TEXT_DIM), (ix, iy))
        iy += 15
        bar_rect = pygame.Rect(ix, iy, info_rect.width - 24, 10)
        bar(surf, bar_rect, confidence, (180, 40, 40), (0, 210, 90))
        pct = font_s.render(f'{confidence*100:.0f}%', True, TEXT)
        surf.blit(pct, (bar_rect.right - pct.get_width(), iy - 1))
        iy += 22

        # Углы головы
        for label, val in [
            ('Рыскание (yaw)',   head_pose['yaw']),
            ('Тангаж  (pitch)',  head_pose['pitch']),
            ('Крен    (roll)',   head_pose['roll']),
        ]:
            surf.blit(font_s.render(label, True, TEXT_DIM), (ix, iy))
            vt = font_s.render(f'{val:+.1f}°', True, TEXT_HL)
            surf.blit(vt, (info_rect.right - vt.get_width() - 12, iy))
            iy += 18

        # Позиция взгляда
        iy += 4
        surf.blit(font_s.render('Взгляд x / y', True, TEXT_DIM), (ix, iy))
        pos = font_s.render(f'{gaze_x:.3f}  {gaze_y:.3f}', True, TEXT_HL)
        surf.blit(pos, (info_rect.right - pos.get_width() - 12, iy))

        pygame.display.flip()
        clock.tick(60)

    # ── Завершение ────────────────────────────────────────────────────────────
    face_thread.stop()
    pygame.quit()
    if proc:
        proc.terminate()
    print('[demo] Завершено.')


if __name__ == '__main__':
    main()