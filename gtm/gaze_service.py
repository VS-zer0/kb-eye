#!/usr/bin/env python3
"""
gaze_service.py — точка входа Модуля отслеживания взгляда (GTM).
 
Запуск:
    python gaze_service.py [--host 127.0.0.1] [--port 5765]
                           [--camera 0] [--model gaze_model.h5]
 
Топологии интеграции:
    Топология 2: TMK запускает данный процесс как дочерний и
                 подключается к порту GTM для получения gaze_update.
    Топология 3: Движок-хост подключается к GTM напрямую параллельно TMK.
    Топология 4: GTM используется без TMK любым подписчиком.
"""
import argparse
import asyncio
import logging
import threading
 
from gaze_predictor       import GazePredictor
from gaze_capture_service import GazeCaptureService
from gaze_server          import GazeServer
 
 
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="GTM — Gaze Tracking Module")
    p.add_argument("--host",   default="127.0.0.1")
    p.add_argument("--port",   type=int, default=5765)
    p.add_argument("--camera", type=int, default=0)
    p.add_argument("--model",  default="gaze_model.h5")
    return p.parse_args()
 
 
def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    args = parse_args()
 
    predictor = GazePredictor(model_path=args.model)
    capture   = GazeCaptureService(predictor, camera_id=args.camera)
    server    = GazeServer(capture)
 
    # Захват видео — блокирующий цикл OpenCV в отдельном потоке
    capture_thread = threading.Thread(
        target=capture.process_loop, daemon=True)
    capture_thread.start()
 
    # Асинхронный TCP-сервер в основном потоке
    try:
        asyncio.run(server.start(args.host, args.port))
    except KeyboardInterrupt:
        pass
    finally:
        capture.stop()
        capture_thread.join(timeout=2.0)
        logging.info("[GTM] Shutdown complete.")
 
 
if __name__ == "__main__":
    main()
