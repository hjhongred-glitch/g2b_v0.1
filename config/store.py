# -*- coding: utf-8 -*-
"""
설정 파일 경로 관리 및 keyring 기반 비밀정보 저장소.

platformdirs.user_data_dir()를 사용하므로 스크립트 폴더에는 아무것도 쓰지 않는다.
"""
from __future__ import annotations

import logging
from pathlib import Path

import keyring
import keyring.errors
from platformdirs import user_data_dir

from config.model import AppConfig, LogConfig

logger = logging.getLogger(__name__)

# ── 앱 데이터 디렉터리 ────────────────────────────────────────────────────────
_APP_NAME = "조달청알리미"
_APP_AUTHOR = "KR"

DATA_DIR = Path(user_data_dir(_APP_NAME, _APP_AUTHOR))
CONFIG_FILE = DATA_DIR / "config.json"
HISTORY_FILE = DATA_DIR / "sent_history.csv"
LOG_FILE = DATA_DIR / "app.log"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_log_file(log_cfg: LogConfig | None = None) -> Path:
    """로그 설정에 따른 실제 로그 파일 경로 반환."""
    if log_cfg and log_cfg.log_dir:
        d = Path(log_cfg.log_dir)
        d.mkdir(parents=True, exist_ok=True)
        return d / "app.log"
    return LOG_FILE


# ── keyring 래퍼 ─────────────────────────────────────────────────────────────
_SVC = _APP_NAME   # keyring 서비스 이름

# keyring username 키
_KEY_API = "api_key"
_KEY_GMAIL_PW = "gmail_app_password"


def get_api_key() -> str:
    return keyring.get_password(_SVC, _KEY_API) or ""


def set_api_key(value: str) -> None:
    if value:
        keyring.set_password(_SVC, _KEY_API, value)
    else:
        _delete_secret(_KEY_API)


def get_gmail_password() -> str:
    return keyring.get_password(_SVC, _KEY_GMAIL_PW) or ""


def set_gmail_password(value: str) -> None:
    if value:
        keyring.set_password(_SVC, _KEY_GMAIL_PW, value)
    else:
        _delete_secret(_KEY_GMAIL_PW)


def _delete_secret(username: str) -> None:
    try:
        keyring.delete_password(_SVC, username)
    except keyring.errors.PasswordDeleteError:
        pass


# ── 설정 로드 / 저장 ──────────────────────────────────────────────────────────

def load_config() -> AppConfig:
    ensure_dirs()
    cfg = AppConfig.load(CONFIG_FILE)
    logger.debug("설정 로드: %s", CONFIG_FILE)
    return cfg


def save_config(cfg: AppConfig) -> None:
    ensure_dirs()
    cfg.save(CONFIG_FILE)
    logger.debug("설정 저장: %s", CONFIG_FILE)


# ── 유효성 검사 ───────────────────────────────────────────────────────────────

def validate_config(cfg: AppConfig) -> list[str]:
    """설정 누락/오류 항목 목록 반환. 빈 리스트면 OK."""
    errors: list[str] = []
    if not get_api_key():
        errors.append("API 키가 설정되지 않았습니다.")
    if cfg.enable_email:
        if not cfg.email.sender:
            errors.append("발신자 이메일 주소가 비어있습니다.")
        if not cfg.email.recipients:
            errors.append("수신자 이메일 주소가 비어있습니다.")
        if not get_gmail_password():
            errors.append("Gmail 앱 비밀번호가 설정되지 않았습니다.")
    if not cfg.keywords:
        errors.append("키워드가 하나도 없습니다.")
    if not any(svc.enabled for svc in cfg.api_services):
        errors.append("활성화된 API 서비스가 없습니다.")
    return errors
