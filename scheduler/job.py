# -*- coding: utf-8 -*-
"""
APScheduler 기반 내부 스케줄러.

OS 스케줄러(작업 스케줄러/launchd)에 의존하지 않는다.
앱이 실행 중인 동안 매일 설정된 시각에 자동으로 공고를 조회·발송한다.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from config.model import AppConfig
from config import store as cfg_store
from core import api, filter as flt, history, mailer

logger = logging.getLogger(__name__)

# 작업 ID — 스케줄러 내부 식별자
_JOB_ID = "daily_check"


# ---------------------------------------------------------------------------
# 메인 작업 — 공고 조회 → 필터 → 발송
# ---------------------------------------------------------------------------

class JobResult:
    """단일 실행 결과."""
    def __init__(self) -> None:
        self.ran_at: datetime = datetime.now()
        self.total_fetched: int = 0
        self.new_count: int = 0
        self.api_failed: int = 0   # 실패한 API 엔드포인트 수
        self.sent: bool = False
        self.saved_file: str = ""
        self.error: str = ""

    def summary(self) -> str:
        if self.error:
            return f"오류: {self.error}"
        if self.new_count == 0:
            if self.api_failed > 0:
                return f"API 오류 {self.api_failed}개 — 조회 불완전 (서버 오류 또는 키 확인 필요)"
            return "신규 공고 없음"
        parts = [f"신규 {self.new_count}건"]
        if self.api_failed > 0:
            parts.append(f"API 오류 {self.api_failed}개")
        if self.sent:
            parts.append("이메일 발송")
        if self.saved_file:
            parts.append("파일 저장")
        return " / ".join(parts)


def run_job(cfg: AppConfig | None = None) -> JobResult:
    """
    공고 조회·필터·발송 전체 흐름 실행.

    cfg가 None이면 store에서 최신 설정을 읽어 사용한다.
    (스케줄 실행 시마다 최신 설정을 반영하기 위해)
    """
    result = JobResult()
    if cfg is None:
        cfg = cfg_store.load_config()

    api_key = cfg_store.get_api_key()
    errors = cfg_store.validate_config(cfg)
    if errors:
        result.error = " / ".join(errors)
        logger.error("설정 오류로 작업 중단: %s", result.error)
        return result

    # 조회 기간
    now = datetime.now()
    from_dt = (now - timedelta(hours=cfg.lookback_hours)).strftime("%Y%m%d%H%M")
    to_dt = now.strftime("%Y%m%d%H%M")
    logger.info("조회 기간: %s ~ %s  키워드: %s", from_dt, to_dt, cfg.keywords)

    try:
        # 1. API 조회
        notices, result.api_failed = api.fetch_all(
            api_key, cfg.api_services, from_dt, to_dt,
        )
        result.total_fetched = len(notices)

        # 2. 이력 로드 + 필터링
        sent_ids = history.load_sent_ids(cfg_store.HISTORY_FILE)
        new_notices = flt.filter_notices(notices, cfg.keywords, sent_ids)
        result.new_count = len(new_notices)

        if not new_notices:
            logger.info("신규 공고 없음 — 발송 생략")
            return result

        # 공고일시 내림차순 정렬
        new_notices.sort(key=lambda x: x.get("공고일시", ""), reverse=True)

        # 3. 이메일 발송
        if cfg.enable_email:
            gmail_pw = cfg_store.get_gmail_password()
            mailer.send_email(
                sender=cfg.email.sender,
                app_password=gmail_pw,
                recipients=cfg.email.recipients,
                notices=new_notices,
                keywords=cfg.keywords,
            )
            result.sent = True

        # 4. 파일 저장
        if cfg.output.enable_file:
            result.saved_file = mailer.save_to_file(
                new_notices, cfg.keywords, cfg.output, cfg_store.DATA_DIR
            )

        # 5. OS 알림
        if cfg.enable_os_notification:
            mailer.send_os_notification(
                title="조달청 알리미",
                message=f"신규 공고 {result.new_count}건이 도착했습니다.",
            )

        # 6. 이력 저장
        history.append_sent(cfg_store.HISTORY_FILE, new_notices)

    except Exception as exc:
        result.error = str(exc)
        logger.exception("작업 실행 중 오류")

    return result


# ---------------------------------------------------------------------------
# 스케줄러 관리
# ---------------------------------------------------------------------------

class AlertScheduler:
    """APScheduler BackgroundScheduler 래퍼."""

    def __init__(self) -> None:
        self._scheduler = BackgroundScheduler(timezone="Asia/Seoul")
        self._on_complete: Callable[[JobResult], None] | None = None

    def set_on_complete(self, callback: Callable[[JobResult], None]) -> None:
        """작업 완료 시 호출할 콜백 등록 (UI 업데이트용)."""
        self._on_complete = callback

    def _wrapped_job(self) -> None:
        result = run_job()
        logger.info("스케줄 작업 완료: %s", result.summary())
        if self._on_complete:
            try:
                self._on_complete(result)
            except Exception as exc:
                logger.warning("콜백 실행 오류: %s", exc)

    def start(self, hour: int = 9, minute: int = 0) -> None:
        if self._scheduler.running:
            return
        self._scheduler.add_job(
            self._wrapped_job,
            trigger=CronTrigger(hour=hour, minute=minute, timezone="Asia/Seoul"),
            id=_JOB_ID,
            replace_existing=True,
            misfire_grace_time=3600,   # 최대 1시간 지연 허용
        )
        self._scheduler.start()
        logger.info("스케줄러 시작: 매일 %02d:%02d", hour, minute)

    def reschedule(self, hour: int, minute: int) -> None:
        """실행 시각 변경 (앱 재시작 없이 즉시 반영)."""
        if not self._scheduler.running:
            self.start(hour, minute)
            return
        self._scheduler.reschedule_job(
            _JOB_ID,
            trigger=CronTrigger(hour=hour, minute=minute, timezone="Asia/Seoul"),
        )
        logger.info("스케줄 변경: 매일 %02d:%02d", hour, minute)

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("스케줄러 종료")

    @property
    def next_run_time(self) -> datetime | None:
        job = self._scheduler.get_job(_JOB_ID)
        return job.next_run_time if job else None

    @property
    def is_running(self) -> bool:
        return self._scheduler.running
