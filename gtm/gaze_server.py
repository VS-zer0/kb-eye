"""
GazeServer — асинхронный TCP-сервер GTM.
Поддерживает до 4 одновременных подписчиков.
Протокол: JSON UTF-8, каждое сообщение завершено '\n'.
"""
from __future__ import annotations
import asyncio
import json
import time
import logging
from dataclasses import dataclass
 
from head_pose_estimator import HeadPose
 
MAX_CLIENTS = 4
log = logging.getLogger("gtm.server")
 
 
@dataclass
class ScreenBounds:
    width_px:  int   = 1920
    height_px: int   = 1080
    dpi:       float = 96.0
 
 
class GazeServer:
    def __init__(self, capture_service) -> None:
        self._svc    = capture_service
        self._clients: list[asyncio.StreamWriter] = []
        self._lock   = asyncio.Lock()
        self._bounds = ScreenBounds()
        self._prev_on_screen: bool | None = None
        self._loop:  asyncio.AbstractEventLoop | None = None
        self._svc.on_gaze_update = self._handle_gaze_update
 
    async def start(self, host: str = "127.0.0.1", port: int = 5765) -> None:
        self._loop   = asyncio.get_event_loop()
        self._server = await asyncio.start_server(
            self._handle_client, host, port)
        log.info(f"[GTM] Server on {host}:{port}")
        async with self._server:
            await self._server.serve_forever()
 
    # ── Обработка нового подключения ──────────────────────────────────────
 
    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        peer = writer.get_extra_info("peername")
        log.info(f"[GTM] Client connected: {peer}")
        async with self._lock:
            if len(self._clients) >= MAX_CLIENTS:
                writer.close(); await writer.wait_closed(); return
            self._clients.append(writer)
        await self._send(writer, {"type": "module_status", "state": "active"})
        try:
            while True:
                data = await reader.readline()
                if not data: break
                await self._handle_command(data.decode().strip())
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            async with self._lock:
                if writer in self._clients: self._clients.remove(writer)
            writer.close(); await writer.wait_closed()
            log.info(f"[GTM] Client disconnected: {peer}")
 
    # ── Обработка входящих команд ─────────────────────────────────────────
 
    async def _handle_command(self, raw: str) -> None:
        try: msg = json.loads(raw)
        except json.JSONDecodeError: return
        cmd = msg.get("type")
        if cmd == "start_calibration":
            await self._broadcast({"type": "module_status", "state": "calibrating"})
            asyncio.create_task(self._run_calibration())
        elif cmd == "set_screen_bounds":
            self._bounds = ScreenBounds(
                width_px  = msg.get("width_px",  1920),
                height_px = msg.get("height_px", 1080),
                dpi       = msg.get("dpi",        96.0),
            )
 
    # ── Публикация обновлений взгляда ─────────────────────────────────────
 
    def _handle_gaze_update(
        self, gx: float, gy: float, conf: float,
        on_screen: bool, pose: HeadPose,
    ) -> None:
        """Вызывается из потока захвата; планирует broadcast в event-loop."""
        ts = int(time.time() * 1000)
        msg = {
            "type":        "gaze_update",
            "x":           round(gx,   4),
            "y":           round(gy,   4),
            "confidence":  round(conf, 3),
            "on_screen":   on_screen,
            "head_pose":   {"yaw":   round(pose.yaw,   2),
                            "pitch": round(pose.pitch, 2),
                            "roll":  round(pose.roll,  2)},
            "timestamp_ms": ts,
        }
        if self._prev_on_screen != on_screen:
            self._prev_on_screen = on_screen
            status = {"type": "gaze_status", "on_screen": on_screen, "timestamp": ts}
            asyncio.run_coroutine_threadsafe(
                self._broadcast(status), self._loop)
        asyncio.run_coroutine_threadsafe(
            self._broadcast(msg), self._loop)
 
    # ── Процедура калибровки 5×5 ──────────────────────────────────────────
 
    async def _run_calibration(self) -> None:
        grid_n, dwell = 5, 1.5
        for row in range(grid_n):
            for col in range(grid_n):
                tx, ty = (col + 0.5) / grid_n, (row + 0.5) / grid_n
                await self._broadcast({
                    "type": "calibration_point",
                    "x": tx, "y": ty,
                    "index": row * grid_n + col,
                    "total": grid_n * grid_n,
                })
                self._svc.start_calibration_sample(tx, ty)
                await asyncio.sleep(dwell)
                self._svc.stop_calibration_sample()
 
        history = await asyncio.get_event_loop().run_in_executor(
            None, self._svc.train)
        val_mae = history.get("val_mae", [None])[-1]
        acc_cm  = round(val_mae * 30.0, 1) if val_mae else None
        await self._broadcast({
            "type": "calibration_complete",
            "accuracy_cm": acc_cm,
        })
        await self._broadcast({"type": "module_status", "state": "active"})
 
    # ── Вспомогательные методы ────────────────────────────────────────────
 
    async def _broadcast(self, obj: dict) -> None:
        data = (json.dumps(obj, ensure_ascii=False) + "\n").encode()
        async with self._lock:
            dead = []
            for w in self._clients:
                try:   w.write(data); await w.drain()
                except: dead.append(w)
            for w in dead: self._clients.remove(w)
 
    @staticmethod
    async def _send(writer: asyncio.StreamWriter, obj: dict) -> None:
        writer.write((json.dumps(obj, ensure_ascii=False) + "\n").encode())
        await writer.drain()
