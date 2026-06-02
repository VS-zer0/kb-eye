"""
EyeNormalizer — выделение области глаза из кадра и геометрическая
нормализация с компенсацией крена (roll-compensation).
"""
from __future__ import annotations
import cv2
import numpy as np
 
# Индексы контура левого и правого глаза в MediaPipe Face Mesh (468 точек)
LEFT_EYE_INDICES  = [362, 385, 387, 263, 373, 380]
RIGHT_EYE_INDICES = [33,  160, 158, 133, 153, 144]
 
TARGET_SIZE = 64    # целевой размер нормализованного изображения
EYE_PADDING = 0.15  # отступ от ограничивающего прямоугольника
 
 
class EyeNormalizer:
    """
    Извлекает изображение глаза из кадра и выполняет:
    1. Вычисление bbox с отступом EYE_PADDING.
    2. Геометрический поворот на -roll_deg (компенсация крена).
    3. Ресайз до TARGET_SIZE × TARGET_SIZE.
    4. Конвертацию в оттенки серого.
    5. Нормализацию пикселей в [0, 1].
    """
 
    def extract_and_normalize(
        self,
        frame: np.ndarray,
        landmarks,
        roll_deg: float,
        use_left: bool = True,
    ) -> np.ndarray | None:
        """
        Возвращает np.ndarray формы (TARGET_SIZE, TARGET_SIZE, 1) dtype=float32
        или None при ошибке.
        """
        indices = LEFT_EYE_INDICES if use_left else RIGHT_EYE_INDICES
        h, w    = frame.shape[:2]
 
        pts = np.array([
            [int(landmarks[i].x * w), int(landmarks[i].y * h)]
            for i in indices
        ], dtype=np.int32)
 
        x, y, bw, bh = cv2.boundingRect(pts)
        px, py = int(bw * EYE_PADDING), int(bh * EYE_PADDING)
        x1, y1 = max(x - px, 0), max(y - py, 0)
        x2, y2 = min(x + bw + px, w), min(y + bh + py, h)
        if x2 <= x1 or y2 <= y1:
            return None
 
        crop = frame[y1:y2, x1:x2].copy()
        ew, eh = crop.shape[1], crop.shape[0]
 
        # Roll-нормализация через аффинный поворот
        M = cv2.getRotationMatrix2D((float(ew // 2), float(eh // 2)),
                                    angle=-roll_deg, scale=1.0)
        normalized = cv2.warpAffine(crop, M, (ew, eh),
                                    flags=cv2.INTER_LINEAR,
                                    borderMode=cv2.BORDER_REPLICATE)
 
        normalized = cv2.resize(normalized, (TARGET_SIZE, TARGET_SIZE),
                                interpolation=cv2.INTER_AREA)
        gray   = cv2.cvtColor(normalized, cv2.COLOR_BGR2GRAY)
        result = gray.astype(np.float32) / 255.0
        return result[..., np.newaxis]   # (64, 64, 1)
