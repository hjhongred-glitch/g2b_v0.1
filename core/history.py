# -*- coding: utf-8 -*-
"""
발송 이력 관리 모듈.

sent_history.csv를 읽고 쓰는 기능만 담당한다.
파일 경로는 호출 측(config/store)이 platformdirs로 결정해 주입한다.
"""
from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_HEADER = ["공고번호", "공고명", "발송일시"]


def load_sent_ids(history_path: Path) -> set[str]:
    """이미 발송한 공고번호 집합을 반환."""
    if not history_path.exists():
        return set()

    sent: set[str] = set()
    try:
        with history_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            next(reader, None)          # 헤더 스킵
            for row in reader:
                if row and row[0]:
                    sent.add(row[0])
    except Exception as exc:
        logger.warning("이력 파일 읽기 실패: %s", exc)

    logger.debug("이력 로드: %d건", len(sent))
    return sent


def append_sent(history_path: Path, notices: list[dict]) -> None:
    """발송 완료된 공고를 이력 파일에 추가."""
    if not notices:
        return

    write_header = not history_path.exists()
    try:
        history_path.parent.mkdir(parents=True, exist_ok=True)
        with history_path.open("a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(_HEADER)
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for n in notices:
                writer.writerow([n.get("공고번호", ""), n.get("공고명", ""), now_str])
        logger.info("이력 추가: %d건", len(notices))
    except Exception as exc:
        logger.error("이력 파일 쓰기 실패: %s", exc)
