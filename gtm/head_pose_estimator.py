"""
HeadPoseEstimator — оценка 6-DOF позы головы методом solvePnP.
Использует 6 опорных анатомических ориентиров MediaPipe Face Mesh.
"""
from __future__ import annotations
import numpy as np
import cv2
from dataclasses import dataclass
 
 
# Антропометрически усреднённые 3D-координаты 6 ориентиров (мм)
FACE_3D_MODEL = np.array([
    [   0.0,    0.0,    0.0],   # кончик носа       (index 1)
    [   0.0, -330.0,  -65.0],   # подбородок        (index 152)
    [-225.0,  170.0, -135.0],   # уголок левого глаза (index 263)
    [ 225.0,  170.0, -135.0],   # уголок правого глаза (index 33)
    [-150.0, -150.0, -125.0],   # левый уголок рта  (index 287)
    [ 150.0, -150.0, -125.0],   # правый уголок рта (index 57)
], dtype=np.float64)
 
LANDMARK_INDICES = [1, 152, 263, 33, 287, 57]
 
 
@dataclass
class HeadPose:
    roll:  float = 0.0   # крен (градусы)
    yaw:   float = 0.0   # рыскание (градусы)
    pitch: float = 0.0   # тангаж (градусы)
    tx:    float = 0.0   # нормированное горизонтальное смещение
    ty:    float = 0.0   # нормированное вертикальное смещение
 
 
class HeadPoseEstimator:
    """
    Оценивает позу головы по 2D-проекции 6 ориентиров через cv2.solvePnP.
    Матрица камеры формируется динамически при первом вызове estimate().
    """
 
    def __init__(self) -> None:
        self._camera_matrix: np.ndarray | None = None
        self._dist_coeffs = np.zeros((4, 1), dtype=np.float64)
 
    def _build_camera_matrix(self, w: int, h: int) -> np.ndarray:
        f = float(w)
        return np.array([[f, 0, w/2], [0, f, h/2], [0, 0, 1]], dtype=np.float64)
 
    def estimate(self, landmarks, frame_w: int, frame_h: int) -> HeadPose | None:
        if self._camera_matrix is None:
            self._camera_matrix = self._build_camera_matrix(frame_w, frame_h)
 
        face_2d = np.array([
            [landmarks[i].x * frame_w, landmarks[i].y * frame_h]
            for i in LANDMARK_INDICES
        ], dtype=np.float64)
 
        ok, rvec, tvec = cv2.solvePnP(
            FACE_3D_MODEL, face_2d,
            self._camera_matrix, self._dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not ok:
            return None
 
        R, _ = cv2.Rodrigues(rvec)
        roll, yaw, pitch = self._rotation_matrix_to_euler(R)
        tx = float(tvec[0][0]) / frame_w
        ty = float(tvec[1][0]) / frame_h
        return HeadPose(roll=roll, yaw=yaw, pitch=pitch, tx=tx, ty=ty)
 
    @staticmethod
    def _rotation_matrix_to_euler(R: np.ndarray) -> tuple[float, float, float]:
        """ZYX-разложение матрицы вращения в градусах (roll, yaw, pitch)."""
        sy = np.sqrt(R[0, 0]**2 + R[1, 0]**2)
        if sy > 1e-6:
            roll  = np.degrees(np.arctan2( R[2, 1],  R[2, 2]))
            pitch = np.degrees(np.arctan2(-R[2, 0],  sy))
            yaw   = np.degrees(np.arctan2( R[1, 0],  R[0, 0]))
        else:
            roll  = np.degrees(np.arctan2(-R[1, 2],  R[1, 1]))
            pitch = np.degrees(np.arctan2(-R[2, 0],  sy))
            yaw   = 0.0
        return roll, yaw, pitch
