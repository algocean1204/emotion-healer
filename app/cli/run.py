"""API 서버를 띄움. 화면은 nginx나 vite 개발 서버가 따로 서빙함."""

from __future__ import annotations

import logging
import os

import uvicorn

from app import guide

# 기본은 루프백임. 0.0.0.0 이면 같은 Wi-Fi의 누구나 nginx를 건너뛰고 직접 때림.
# web 컨테이너(:8080) 연결 시에만 HEALER_HOST=0.0.0.0 으로 개방
DEFAULT_HOST = "127.0.0.1"
PORT = 8000


def run() -> None:
    # 앱 로거에 핸들러가 없으면 시각도 레벨도 없이 stderr 로 떨어짐
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    name = guide.load_shared("healer_service.json").get("name", "")
    host = os.getenv("HEALER_HOST", DEFAULT_HOST)
    exposure = "루프백만" if host.startswith("127.") else f"{host} — 외부에서 닿습니다"
    print(
        f"{name} API — http://127.0.0.1:{PORT}  ({exposure})\n"
        "화면: cd frontend && npm run dev (:5173)\n"
        "도커 화면(:8080)을 쓰려면 HEALER_HOST=0.0.0.0 으로 다시 띄우세요\n"
    )
    uvicorn.run("app.main:app", host=host, port=PORT, log_level="warning")
