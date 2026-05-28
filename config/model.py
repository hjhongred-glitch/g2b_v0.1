# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

# 로그 포맷 프리셋
LOG_FORMAT_PRESETS: dict[str, str] = {
    "기본":   "[%(asctime)s] %(levelname)s  %(name)s — %(message)s",
    "간단":   "[%(asctime)s] %(message)s",
    "상세":   "[%(asctime)s] %(levelname)-8s %(name)s:%(lineno)d — %(message)s",
    "JSON":   '{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
    "직접입력": "",
}

LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR"]
OUTPUT_FORMATS = ["csv", "html"]

DEFAULT_API_BASE_URL = "http://apis.data.go.kr/1230000/BidPublicInfoService05"


# ── API 서비스 계층 모델 ──────────────────────────────────────────────────────

@dataclass
class EndpointConfig:
    """단일 엔드포인트 설정."""
    endpoint: str        # 함수명 (예: getBidPblancListInfoServcPPSSrch)
    category: str        # 분야 레이블 (예: 용역)
    enabled: bool = True
    extra_params: dict = field(default_factory=dict)  # 고정 추가 파라미터

    def to_dict(self) -> dict:
        return {
            "endpoint": self.endpoint,
            "category": self.category,
            "enabled": self.enabled,
            "extra_params": self.extra_params,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EndpointConfig":
        return cls(
            endpoint=d.get("endpoint", ""),
            category=d.get("category", ""),
            enabled=d.get("enabled", True),
            extra_params=d.get("extra_params", {}),
        )


@dataclass
class ApiServiceConfig:
    """하나의 API 서비스 (Base URL 1개 : 엔드포인트 N개)."""
    name: str
    base_url: str
    notice_type: str               # 공고유형 레이블 (예: 입찰공고)
    endpoints: list[EndpointConfig]
    enabled: bool = True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "base_url": self.base_url,
            "notice_type": self.notice_type,
            "enabled": self.enabled,
            "endpoints": [e.to_dict() for e in self.endpoints],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ApiServiceConfig":
        return cls(
            name=d.get("name", ""),
            base_url=d.get("base_url", DEFAULT_API_BASE_URL),
            notice_type=d.get("notice_type", "입찰공고"),
            enabled=d.get("enabled", True),
            endpoints=[EndpointConfig.from_dict(e) for e in d.get("endpoints", [])],
        )


def _default_api_services() -> list[ApiServiceConfig]:
    return [
        ApiServiceConfig(
            name="나라장터 입찰공고",
            base_url=DEFAULT_API_BASE_URL,
            notice_type="입찰공고",
            endpoints=[
                EndpointConfig("getBidPblancListInfoServcPPSSrch",    "용역"),
                EndpointConfig("getBidPblancListInfoThngPPSSrch",     "물품"),
                EndpointConfig("getBidPblancListInfoCnstwkPPSSrch",   "공사"),
            ],
        ),
        ApiServiceConfig(
            name="나라장터 사전규격공개",
            base_url=DEFAULT_API_BASE_URL,
            notice_type="사전규격공개",
            endpoints=[
                EndpointConfig("getPreStdBidPblancListInfoServcPPSSrch",  "용역"),
                EndpointConfig("getPreStdBidPblancListInfoThngPPSSrch",   "물품"),
                EndpointConfig("getPreStdBidPblancListInfoCnstwkPPSSrch", "공사"),
            ],
        ),
    ]


# ── 이메일 / 출력 / 로그 ──────────────────────────────────────────────────────

@dataclass
class EmailConfig:
    sender: str = ""
    recipients: list[str] = field(default_factory=list)


@dataclass
class OutputConfig:
    enable_file: bool = False
    file_dir: str = ""
    file_format: str = "csv"


@dataclass
class LogConfig:
    log_dir: str = ""
    log_level: str = "INFO"
    log_format: str = "[%(asctime)s] %(levelname)s  %(name)s — %(message)s"
    log_max_bytes: int = 1_048_576
    log_backup_count: int = 3


# ── 앱 전체 설정 ───────────────────────────────────────────────────────────────

@dataclass
class AppConfig:
    # 검색 설정
    keywords: list[str] = field(
        default_factory=lambda: ["중대재해", "안전보건", "산업안전", "안전관리"]
    )
    lookback_hours: int = 24

    # API 서비스 (1 서비스 = 1 Base URL + N 엔드포인트)
    api_services: list[ApiServiceConfig] = field(default_factory=_default_api_services)

    # 스케줄
    schedule_hour: int = 9
    schedule_minute: int = 0

    # 알림 채널
    enable_email: bool = True
    enable_os_notification: bool = True

    # 이메일 (비밀번호 제외)
    email: EmailConfig = field(default_factory=EmailConfig)

    # 출력
    output: OutputConfig = field(default_factory=OutputConfig)

    # 로그
    log: LogConfig = field(default_factory=LogConfig)

    # ── 직렬화 ──────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        d = asdict(self)
        # api_services는 asdict가 직접 처리하지 못하는 nested list → 수동 변환
        d["api_services"] = [s.to_dict() for s in self.api_services]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "AppConfig":
        email_raw    = d.pop("email",        {})
        output_raw   = d.pop("output",       {})
        log_raw      = d.pop("log",          {})
        services_raw = d.pop("api_services", None)

        # 구버전 notice_types 마이그레이션 지원
        notice_types_old = d.pop("notice_types", None)
        d.pop("notice_categories", None)
        d.pop("api_base_url",      None)

        cfg = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        cfg.email  = EmailConfig( **{k: v for k, v in email_raw.items()  if k in EmailConfig.__dataclass_fields__})
        cfg.output = OutputConfig(**{k: v for k, v in output_raw.items() if k in OutputConfig.__dataclass_fields__})
        cfg.log    = LogConfig(   **{k: v for k, v in log_raw.items()    if k in LogConfig.__dataclass_fields__})

        if services_raw:
            cfg.api_services = [ApiServiceConfig.from_dict(s) for s in services_raw]
        elif notice_types_old:
            # 구버전 notice_types → api_services 활성화 상태로 마이그레이션
            defaults = _default_api_services()
            for svc in defaults:
                svc.enabled = notice_types_old.get(svc.notice_type, True)
            cfg.api_services = defaults

        return cfg

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "AppConfig":
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return cls.from_dict(raw)
        except Exception:
            return cls()
