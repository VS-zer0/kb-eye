"""
GazeCaptureService — захват видеопотока и оркестрация конвейера:
Face Mesh → HeadPoseEstimator → EyeNormalizer → GazePredictor.
"""
from __future__ import annotations
import time
import numpy as np
import cv2
import mediapipe as mp
 
from head_pose_estimator import HeadPoseEstimator, HeadPose
from eye_normalizer      import EyeNormalizer
from gaze_predictor      import GazePredictor
 
# Порог по Y: ниже — взгляд на клавиатуру; выше — на экран
KEYBOARD_Y_THRESHOLD = 0.85
PITCH_CORRECTION     = 0.015  # коррекция на 1° тангажа
 
 
class GazeCaptureService:
    """
    Основной сервис обработки видео.
    Вызывающий код запускает process_loop() в отдельном потоке.
    """
 
    def __init__(self, predictor: GazePredictor, camera_id: int = 0) -> None:
        self._predictor  = predictor
        self._camera_id  = camera_id
        self._estimator  = HeadPoseEstimator()
        self._normalizer = EyeNormalizer()
        self._running    = False
 
        # Callback: вызывается при каждом обновлении
        self.on_gaze_update = None  # fn(x, y, conf, on_screen, pose)
 
        # Данные калибровки
        self._calib_samples:    list[tuple] = []
        self._collecting_calib: bool        = False
        self._calib_target:     tuple | None = None
 
        self._face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
 
    # ── Управление калибровкой ────────────────────────────────────────────
 
    def start_calibration_sample(self, tx: float, ty: float) -> None:
        self._collecting_calib = True
        self._calib_target     = (tx, ty)
 
    def stop_calibration_sample(self) -> None:
        self._collecting_calib = False
        self._calib_target     = None
 
    def train(self) -> dict:
        if not self._calib_samples:
            return {}
        eyes  = np.array([s[0] for s in self._calib_samples], dtype=np.float32)
        poses = np.array([s[1] for s in self._calib_samples], dtype=np.float32)
        tgts  = np.array([s[2] for s in self._calib_samples], dtype=np.float32)
        self._calib_samples.clear()
        return self._predictor.train(eyes, poses, tgts)
 
    def stop(self) -> None:
        self._running = False
 
    # ── Основной цикл ─────────────────────────────────────────────────────
 
    def process_loop(self) -> None:
        cap = cv2.VideoCapture(self._camera_id)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open camera {self._camera_id}")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH,  640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self._running = True
 
        while self._running:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.01); continue
 
            frame = cv2.flip(frame, 1)  # горизонтальное зеркало
            h, w  = frame.shape[:2]
            rgb   = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
 
            results = self._face_mesh.process(rgb)
            if not results.multi_face_landmarks:
                continue
            lms = results.multi_face_landmarks[0].landmark
 
            # Оценка позы головы
            pose = self._estimator.estimate(lms, w, h)
            if pose is None:
                continue
 
            # Roll-нормализованное изображение глаза
            eye_img = self._normalizer.extract_and_normalize(
                frame, lms, pose.roll, use_left=True)
            if eye_img is None:
                continue
 
            # Вектор признаков позы (нормализованный)
            pose_vec = np.array(
                [pose.yaw / 90.0, pose.pitch / 90.0, pose.tx, pose.ty],
                dtype=np.float32)
 
            # Сбор данных калибровки
            if self._collecting_calib and self._calib_target:
                self._calib_samples.append(
                    (eye_img, pose_vec,
                     np.array(self._calib_target, dtype=np.float32)))
 
            # Предсказание взгляда
            if not self._predictor.is_trained:
                continue
 
            gx, gy, conf = self._predictor.predict(eye_img, pose_vec)
 
            # Динамический порог on_screen с поправкой на тангаж
            threshold = KEYBOARD_Y_THRESHOLD + pose.pitch * PITCH_CORRECTION
            on_screen = gy < threshold
 
            if self.on_gaze_update:
                self.on_gaze_update(gx, gy, conf, on_screen, pose)
 
        cap.release()
        self._face_mesh.close()
