# -*- coding: utf-8 -*-
"""
이메일 발송 및 OS 네이티브 알림 모듈.

UI·OS 스케줄러에 의존하지 않는 순수 로직.
OS 알림은 macOS(osascript)와 Windows(plyer) 분기 처리한다.
"""
from __future__ import annotations

import csv
import logging
import platform
import smtplib
import subprocess
from datetime import datetime
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 이메일
# ---------------------------------------------------------------------------

def _build_html(notices: list[dict], keywords: list[str]) -> str:
    rows = ""
    for i, n in enumerate(notices, 1):
        price = ""
        if n.get("추정가격"):
            try:
                price = f"{int(float(n['추정가격'])):,}원"
            except (ValueError, TypeError):
                price = n["추정가격"]

        link = (
            f'<a href="{n["공고URL"]}" style="color:#1a73e8;">상세보기</a>'
            if n.get("공고URL")
            else "—"
        )
        rows += f"""
        <tr>
          <td style="padding:8px;border-bottom:1px solid #eee;text-align:center;">{i}</td>
          <td style="padding:8px;border-bottom:1px solid #eee;">
            <strong>{n.get("공고명","")}</strong><br>
            <span style="color:#888;font-size:12px;">
              {n.get("공고유형","")} · {n.get("분야","")} · {n.get("공고기관","")}
            </span>
          </td>
          <td style="padding:8px;border-bottom:1px solid #eee;font-size:12px;">{n.get("공고일시","")}</td>
          <td style="padding:8px;border-bottom:1px solid #eee;font-size:12px;">{n.get("마감일시","")}</td>
          <td style="padding:8px;border-bottom:1px solid #eee;font-size:12px;text-align:right;">{price}</td>
          <td style="padding:8px;border-bottom:1px solid #eee;text-align:center;">{link}</td>
        </tr>"""

    return f"""
    <html><body style="font-family:'맑은 고딕',sans-serif;max-width:920px;margin:auto;">
      <h2 style="color:#222;border-bottom:2px solid #1a73e8;padding-bottom:8px;">
        조달청 입찰공고 알리미 — {datetime.now().strftime('%Y-%m-%d')}
      </h2>
      <p style="color:#555;">
        검색 키워드: <strong>{', '.join(keywords)}</strong><br>
        신규 공고: <strong>{len(notices)}건</strong>
      </p>
      <table style="width:100%;border-collapse:collapse;font-size:13px;">
        <thead>
          <tr style="background:#f5f5f5;">
            <th style="padding:8px;border-bottom:2px solid #ccc;">#</th>
            <th style="padding:8px;border-bottom:2px solid #ccc;text-align:left;">공고명 / 기관</th>
            <th style="padding:8px;border-bottom:2px solid #ccc;">공고일시</th>
            <th style="padding:8px;border-bottom:2px solid #ccc;">마감일시</th>
            <th style="padding:8px;border-bottom:2px solid #ccc;text-align:right;">추정가격</th>
            <th style="padding:8px;border-bottom:2px solid #ccc;">링크</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
      <p style="color:#999;font-size:11px;margin-top:20px;">
        본 메일은 자동 발송되었습니다.
        키워드 수정은 앱의 설정 탭에서 가능합니다.
      </p>
    </body></html>"""


def send_email(
    sender: str,
    app_password: str,
    recipients: list[str],
    notices: list[dict],
    keywords: list[str],
) -> None:
    """
    Gmail SMTP SSL(465포트)로 공고 이메일 발송.

    Raises:
        smtplib.SMTPException: 발송 실패 시
    """
    msg = MIMEMultipart("alternative")
    msg["From"] = formataddr((str(Header("조달청 알리미", "utf-8")), sender))
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = Header(
        f"[조달청 알리미] {datetime.now().strftime('%m/%d')} 신규 공고 {len(notices)}건",
        "utf-8",
    )
    msg.attach(MIMEText(_build_html(notices, keywords), "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, app_password)
        server.send_message(msg)

    logger.info("이메일 발송 완료 → %s (%d건)", recipients, len(notices))


# ---------------------------------------------------------------------------
# OS 네이티브 알림
# ---------------------------------------------------------------------------

def send_os_notification(title: str, message: str) -> None:
    """
    macOS 알림 센터 또는 Windows 토스트 알림 발송.

    실패해도 예외를 올리지 않고 경고만 기록한다.
    """
    system = platform.system()
    try:
        if system == "Darwin":
            # macOS — osascript (별도 의존성 불필요)
            script = (
                f'display notification "{_esc(message)}" '
                f'with title "{_esc(title)}"'
            )
            subprocess.run(
                ["osascript", "-e", script],
                check=True,
                timeout=5,
                capture_output=True,
            )
        elif system == "Windows":
            # Windows — plyer (선택적 의존성)
            try:
                from plyer import notification  # type: ignore
                notification.notify(
                    title=title,
                    message=message,
                    app_name="조달청 알리미",
                    timeout=10,
                )
            except ImportError:
                logger.debug("plyer 미설치 — Windows 알림 스킵")
        else:
            logger.debug("OS 알림 미지원 플랫폼: %s", system)
    except Exception as exc:
        logger.warning("OS 알림 실패: %s", exc)


def _esc(text: str) -> str:
    """osascript 문자열 이스케이프."""
    return text.replace('"', '\\"').replace("\\", "\\\\")


# ---------------------------------------------------------------------------
# 파일 출력
# ---------------------------------------------------------------------------

_CSV_FIELDS = ["공고번호", "공고명", "공고기관", "수요기관",
               "공고유형", "분야", "공고일시", "마감일시", "추정가격", "공고URL"]


def _save_csv(notices: list[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(notices)


def _save_html(notices: list[dict], keywords: list[str], path: Path) -> None:
    path.write_text(_build_html(notices, keywords), encoding="utf-8")


def save_to_file(
    notices: list[dict],
    keywords: list[str],
    output_cfg,          # OutputConfig (순환참조 방지를 위해 타입 미명시)
    data_dir: Path,
) -> str:
    """
    공고를 파일로 저장하고 저장된 경로 반환.

    Args:
        output_cfg: config.model.OutputConfig 인스턴스
        data_dir:   기본 저장 위치 (output_cfg.file_dir 미설정 시 사용)
    """
    out_dir = Path(output_cfg.file_dir) if output_cfg.file_dir else data_dir / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fmt = output_cfg.file_format

    if fmt == "html":
        path = out_dir / f"공고_{timestamp}.html"
        _save_html(notices, keywords, path)
    else:
        path = out_dir / f"공고_{timestamp}.csv"
        _save_csv(notices, path)

    logger.info("파일 저장 완료: %s", path)
    return str(path)
