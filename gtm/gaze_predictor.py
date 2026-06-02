"""
GazePredictor — двухвходовая регрессионная CNN для предсказания
координат взгляда по изображению глаза и вектору позы головы.
"""
from __future__ import annotations
import os
import numpy as np
import tensorflow as tf
from tensorflow.keras import Input, Model
from tensorflow.keras.layers import (Conv2D, MaxPooling2D, BatchNormalization,
                                     Flatten, Dense, Dropout, Concatenate)
from tensorflow.keras.optimizers import Adam
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint
 
TARGET_SIZE = 64
MODEL_PATH  = "gaze_model.h5"
 
 
def _build_model() -> Model:
    # ── Ветвь изображения глаза ───────────────────────────────────────────
    eye = Input(shape=(TARGET_SIZE, TARGET_SIZE, 1), name="eye_image")
    x = Conv2D(32,  3, activation="relu", padding="same")(eye)
    x = MaxPooling2D()(x); x = BatchNormalization()(x)
    x = Conv2D(64,  3, activation="relu", padding="same")(x)
    x = MaxPooling2D()(x); x = BatchNormalization()(x)
    x = Conv2D(128, 3, activation="relu", padding="same")(x)
    x = MaxPooling2D()(x); x = BatchNormalization()(x)
    x = Flatten()(x)
    eye_feat = Dense(128, activation="relu")(x)
 
    # ── Ветвь вектора позы [yaw/90, pitch/90, tx, ty] ────────────────────
    pose      = Input(shape=(4,), name="head_pose")
    pose_feat = Dense(16, activation="relu")(pose)
 
    # ── Слияние и регрессионный выход ─────────────────────────────────────
    merged = Concatenate()([eye_feat, pose_feat])
    merged = Dense(64, activation="relu")(merged)
    merged = Dropout(0.5)(merged)
    output = Dense(2, name="gaze_xy")(merged)
 
    model = Model(inputs=[eye, pose], outputs=output)
    model.compile(optimizer=Adam(1e-3), loss="mse", metrics=["mae"])
    return model
 
 
class GazePredictor:
    def __init__(self, model_path: str = MODEL_PATH) -> None:
        self._model_path = model_path
        self._model: Model | None = None
        self._alpha  = 0.35
        self._prev_x = 0.5
        self._prev_y = 0.5
        if os.path.exists(model_path):
            self.load()
 
    # ── Обучение на данных калибровки ─────────────────────────────────────
 
    def train(self,
              eye_images: np.ndarray,   # (N, 64, 64, 1) float32
              pose_vecs:  np.ndarray,   # (N, 4)         float32
              targets:    np.ndarray,   # (N, 2)         float32 нормир.
              val_split:  float = 0.2,
              max_epochs: int   = 150,
              batch_size: int   = 32) -> dict:
        self._model = _build_model()
 
        # Лёгкая аугментация: гауссовский шум на признаках позы
        noise    = np.random.normal(0, 0.01, pose_vecs.shape).astype(np.float32)
        pose_aug = np.clip(pose_vecs + noise, -1.0, 1.0)
 
        history = self._model.fit(
            x={"eye_image": eye_images, "head_pose": pose_aug},
            y=targets,
            validation_split=val_split,
            epochs=max_epochs,
            batch_size=batch_size,
            callbacks=[
                EarlyStopping(monitor="val_loss", patience=12,
                              restore_best_weights=True),
                ModelCheckpoint(self._model_path, save_best_only=True,
                                monitor="val_loss"),
            ],
            verbose=1,
        )
        return history.history
 
    # ── Предсказание ──────────────────────────────────────────────────────
 
    def predict(self,
                eye_image: np.ndarray,  # (64, 64, 1)
                pose_vec:  np.ndarray   # (4,)
               ) -> tuple[float, float, float]:
        """Возвращает (x, y, confidence)."""
        if self._model is None:
            return 0.5, 0.5, 0.0
 
        raw = self._model.predict(
            {"eye_image": eye_image[np.newaxis],
             "head_pose": pose_vec[np.newaxis]},
            verbose=0,
        )[0]
 
        gx = float(np.clip(raw[0], 0.0, 1.0))
        gy = float(np.clip(raw[1], 0.0, 1.0))
 
        # EMA-сглаживание
        sx = self._alpha * gx + (1.0 - self._alpha) * self._prev_x
        sy = self._alpha * gy + (1.0 - self._alpha) * self._prev_y
        self._prev_x, self._prev_y = sx, sy
 
        # Уверенность как мера стабильности предсказания
        jitter = np.hypot(gx - sx, gy - sy)
        conf   = float(np.clip(1.0 - jitter * 4.0, 0.0, 1.0))
        return sx, sy, conf
 
    # ── Сохранение / загрузка ─────────────────────────────────────────────
 
    def save(self) -> None:
        if self._model: self._model.save(self._model_path)
 
    def load(self) -> bool:
        try:
            self._model = tf.keras.models.load_model(self._model_path)
            return True
        except Exception:
            self._model = None; return False
 
    @property
    def is_trained(self) -> bool:
        return self._model is not None
