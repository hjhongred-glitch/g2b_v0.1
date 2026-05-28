# -*- coding: utf-8 -*-
"""
CLI 진입점.

작업 스케줄러나 cron에서 직접 실행할 때 사용한다.

사용법:
  python cli.py
  python cli.py --validate-only
"""
from __future__ import annotations

import argparse
import logging
import logging.handlers
import sys

from config import store as cfg_store
from config.model import AppConfig
from scheduler.job import run_job


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


def main() -> None:
    parser = argparse.ArgumentParser(description="조달청 입찰공고 알리미 CLI")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="설정 유효성만 확인하고 종료",
    )
    args = parser.parse_args()

    cfg = cfg_store.load_config()
    _setup_logging(cfg)

    log = logging.getLogger(__name__)
    log.info("=" * 50)
    log.info("조달청 알리미 CLI 실행 시작")

    errors = cfg_store.validate_config(cfg)
    if errors:
        for e in errors:
            log.error("[설정 오류] %s", e)
        log.error("설정을 완성한 후 다시 실행하세요. (앱에서 설정 탭 사용)")
        sys.exit(1)

    if args.validate_only:
        log.info("설정 검증 완료 — 이상 없음")
        return

    result = run_job(cfg)
    log.info("결과: %s", result.summary())

    if result.error:
        sys.exit(1)


if __name__ == "__main__":
    main()
