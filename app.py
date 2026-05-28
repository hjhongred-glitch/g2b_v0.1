# -*- coding: utf-8 -*-
"""
조달청 입찰공고 알리미 — GUI 진입점.

구동 순서:
  1. 설정 로드
  2. 로깅 초기화 (RotatingFileHandler, 설정 기반)
  3. APScheduler 시작 (백그라운드 스레드)
  4. 시스템 트레이 아이콘 초기화 (pystray, 백그라운드 스레드)
  5. Flet 앱 실행 (메인 스레드)
"""
from __future__ import annotations

import logging
import logging.handlers
import platform
import sys
import threading
from pathlib import Path

import flet as ft

from config import store as cfg_store
from config.model import AppConfig
from scheduler.job import AlertScheduler
from ui.app_ui import build_app

# ─────────────────────────────────────────────────────────────────────────────
# 로깅 설정
# ─────────────────────────────────────────────────────────────────────────────

def _setup_logging(cfg: AppConfig) -> None:
    cfg_store.ensure_dirs()
    log_cfg = cfg.log
    fmt = logging.Formatter(log_cfg.log_format, datefmt="%Y-%m-%d %H:%M:%S")
    level = getattr(logging, log_cfg.log_level, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    root.addHandler(ch)

    log_file = cfg_store.get_log_file(log_cfg)
    fh = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=log_cfg.log_max_bytes,
        backupCount=log_cfg.log_backup_count,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)


# ─────────────────────────────────────────────────────────────────────────────
# 시스템 트레이 (pystray)
# ─────────────────────────────────────────────────────────────────────────────

def _start_tray(scheduler: AlertScheduler, page_holder: list) -> None:
    """
    pystray 트레이 아이콘을 별도 데몬 스레드에서 실행.

    macOS는 NSWindow(AppKit)를 메인 스레드에서만 생성할 수 있어
    백그라운드 스레드에서 pystray를 실행하면 NSInternalInconsistencyException이 발생한다.
    → macOS에서는 트레이를 완전히 비활성화하고 앱은 정상 동작.

    page_holder[0] 에 ft.Page가 주입된 후 트레이가 활성화된다.
    """
    if platform.system() == "Darwin":
        logging.debug("macOS: AppKit 메인 스레드 제약으로 시스템 트레이 비활성화")
        return

    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        logging.warning("pystray 또는 Pillow 미설치 — 시스템 트레이 비활성화")
        return

    # 단순한 파란 원 아이콘 생성
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, 60, 60], fill=(26, 115, 232, 255))
    draw.ellipse([20, 16, 44, 36], fill="white")
    draw.rectangle([24, 36, 40, 48], fill="white")

    def show_window(_icon=None, _item=None) -> None:
        page = page_holder[0] if page_holder else None
        if page:
            page.window.visible = True
            page.window.to_front()
            page.update()

    def quit_app(_icon=None, _item=None) -> None:
        scheduler.shutdown()
        icon.stop()
        page = page_holder[0] if page_holder else None
        if page:
            page.window.destroy()

    menu = pystray.Menu(
        pystray.MenuItem("조달청 알리미 열기", show_window, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("종료", quit_app),
    )
    try:
        icon = pystray.Icon("조달청알리미", img, "조달청 알리미", menu)
        icon.run_detached()
        logging.info("시스템 트레이 아이콘 시작")
    except Exception as exc:
        logging.warning("시스템 트레이 초기화 실패: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    # 설정 먼저 로드 → 로깅에 설정 적용
    cfg = cfg_store.load_config()
    _setup_logging(cfg)

    log = logging.getLogger(__name__)
    log.info("=" * 50)
    log.info("조달청 알리미 GUI 시작")

    scheduler = AlertScheduler()

    errors = cfg_store.validate_config(cfg)
    if errors:
        log.warning("설정 미완료 — 스케줄러를 시작하지 않습니다: %s", errors)
    else:
        scheduler.start(cfg.schedule_hour, cfg.schedule_minute)

    page_holder: list = []

    tray_thread = threading.Thread(
        target=_start_tray, args=(scheduler, page_holder), daemon=True
    )
    tray_thread.start()

    raw_main = build_app(scheduler)

    def main_with_page_capture(page: ft.Page) -> None:
        page_holder.append(page)
        raw_main(page)

    ft.run(main_with_page_capture)

    scheduler.shutdown()
    log.info("조달청 알리미 종료")


if __name__ == "__main__":
    main()
