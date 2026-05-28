# -*- coding: utf-8 -*-
"""
나라장터 OpenAPI 호출 모듈.

UI·OS에 전혀 의존하지 않는 순수 로직.
api_services 설정 목록(ApiServiceConfig)에 따라 다수의 서비스를 조회한다.
"""
from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

if TYPE_CHECKING:
    from config.model import ApiServiceConfig

logger = logging.getLogger(__name__)

BASE_URL = "http://apis.data.go.kr/1230000/BidPublicInfoService05"


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _make_session(max_retries: int = 3) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=max_retries,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _parse_body(data: dict) -> tuple[int, list[dict]]:
    body = data["response"]["body"]
    total = int(body.get("totalCount") or 0)
    items = body.get("items") or []
    if isinstance(items, dict):
        items = [items]
    return total, items


# ---------------------------------------------------------------------------
# 공개 인터페이스
# ---------------------------------------------------------------------------

def fetch_endpoint(
    api_key: str,
    endpoint: str,
    from_dt: str,
    to_dt: str,
    base_url: str = BASE_URL,
    session: requests.Session | None = None,
    extra_params: dict | None = None,
) -> list[dict[str, Any]]:
    """단일 엔드포인트에서 조회 기간 내 공고 전체를 페이징하여 반환."""
    if session is None:
        session = _make_session()

    url = f"{base_url.rstrip('/')}/{endpoint}"
    all_items: list[dict] = []
    page = 1

    while True:
        params: dict[str, Any] = {
            "serviceKey": api_key,
            "pageNo":     page,
            "numOfRows":  100,
            "inqryDiv":   1,
            "inqryBgnDt": from_dt,
            "inqryEndDt": to_dt,
            "type":       "json",
        }
        if extra_params:
            params.update(extra_params)
        try:
            resp = session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("API 호출 실패 [%s p%d]: %s", endpoint, page, exc)
            break

        try:
            total, items = _parse_body(data)
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("응답 파싱 실패 [%s p%d]: %s", endpoint, page, exc)
            break

        all_items.extend(items)
        logger.info(
            "  %s p%d: %d건 수신 (누계 %d / 전체 %d)",
            endpoint, page, len(items), len(all_items), total,
        )

        if not items or page * 100 >= total:
            break
        page += 1

    return all_items


def normalize(item: dict, notice_type: str, category: str) -> dict:
    return {
        "공고번호": f"{item.get('bidNtceNo', '')}-{item.get('bidNtceOrd', '')}",
        "공고명":   item.get("bidNtceNm",    "") or "",
        "공고기관": item.get("ntceInsttNm",  "") or "",
        "수요기관": item.get("dminsttNm",    "") or "",
        "공고일시": item.get("bidNtceDt",    "") or "",
        "마감일시": item.get("bidClseDt",    "") or "",
        "공고URL":  item.get("bidNtceDtlUrl","") or "",
        "추정가격": item.get("presmptPrce",  "") or item.get("asignBdgtAmt", "") or "",
        "공고유형": notice_type,
        "분야":     category,
    }


def fetch_all(
    api_key: str,
    api_services: list[ApiServiceConfig],
    from_dt: str,
    to_dt: str,
) -> tuple[list[dict], int]:
    """
    활성화된 모든 API 서비스의 엔드포인트를 조회하고 정규화된 목록을 반환.

    Returns:
        (notices, failed_endpoint_count)
    """
    session = _make_session()
    all_notices: list[dict] = []
    failed = 0

    for svc in api_services:
        if not svc.enabled:
            continue
        logger.info("[%s] 서비스 조회 시작 — %s", svc.name, svc.base_url)
        for ep in svc.endpoints:
            if not ep.enabled:
                logger.debug("  └ %s: 비활성화 — 건너뜀", ep.endpoint)
                continue
            items = fetch_endpoint(api_key, ep.endpoint, from_dt, to_dt, svc.base_url, session, ep.extra_params or None)
            if not items:
                failed += 1
            logger.info("  └ %s (%s): %d건", ep.endpoint, ep.category, len(items))
            for item in items:
                all_notices.append(normalize(item, svc.notice_type, ep.category))

    return all_notices, failed


def test_connection(
    api_key: str,
    service: ApiServiceConfig | None = None,
    base_url: str = BASE_URL,
) -> tuple[bool, str]:
    """
    API 연결 상태 테스트.

    service가 주어지면 해당 서비스의 첫 번째 활성 엔드포인트로 테스트,
    없으면 base_url + 용역 입찰공고 엔드포인트로 테스트.

    Returns:
        (success, message)
    """
    from datetime import datetime, timedelta

    if not api_key:
        return False, "API 키가 설정되지 않았습니다."

    # 테스트할 엔드포인트 결정
    if service is not None:
        test_base = service.base_url.rstrip("/")
        ep_list = [ep.endpoint for ep in service.endpoints if ep.enabled]
        if not ep_list:
            return False, "활성화된 엔드포인트가 없습니다."
        test_ep = ep_list[0]
    else:
        test_base = base_url.rstrip("/")
        test_ep = "getBidPblancListInfoServcPPSSrch"

    now = datetime.now()
    from_dt = (now - timedelta(hours=1)).strftime("%Y%m%d%H%M")
    to_dt   = now.strftime("%Y%m%d%H%M")

    session = _make_session(max_retries=0)
    url = f"{test_base}/{test_ep}"
    params = {
        "serviceKey": api_key,
        "pageNo":     1,
        "numOfRows":  1,
        "inqryDiv":   1,
        "inqryBgnDt": from_dt,
        "inqryEndDt": to_dt,
        "type":       "json",
    }

    # 알려진 나라장터 XML 오류 코드 → 메시지 매핑
    _XML_ERRORS = {
        "SERVICE_KEY_IS_NOT_REGISTERED_ERROR": "API 키 미등록 — 공공데이터포털에서 서비스 신청 확인",
        "DEADLINE_HAS_EXPIRED_ERROR":          "API 키 사용 기간 만료",
        "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR": "일일 호출 횟수 초과",
        "APPLICATION_ERROR":                   "응용 프로그램 오류 — 파라미터 확인",
        "DB_ERROR":                            "DB 오류 — 잠시 후 재시도",
        "NODATA_ERROR":                        None,   # 정상 (데이터 없음)
        "SERVICE_ACCESS_DENIED_ERROR":         "서비스 접근 거부 — IP 또는 키 권한 확인",
    }

    try:
        resp = session.get(url, params=params, timeout=10)
        raw  = resp.text
        logger.debug("test_connection HTTP %d  %s", resp.status_code, raw[:300])

        # ── XML 오류 응답 처리 (HTTP 200/500 모두 해당) ──────────────────────
        if raw.lstrip().startswith("<"):
            for code, user_msg in _XML_ERRORS.items():
                if code in raw:
                    if user_msg is None:
                        return True, "연결 성공 — 조회 결과 없음 (키·엔드포인트 정상)"
                    return False, user_msg
            # 알 수 없는 XML — 첫 200자 표시
            snippet = raw.replace("\n", " ")[:200]
            return False, f"서버 오류 (XML): {snippet}"

        # ── HTTP 오류 처리 ──────────────────────────────────────────────────
        if not resp.ok:
            return False, f"HTTP {resp.status_code} 오류 — {raw[:120]}"

        # ── JSON 파싱 ──────────────────────────────────────────────────────
        data = resp.json()
        total, _ = _parse_body(data)
        return True, f"연결 성공 — 조회 가능 공고 {total}건"

    except requests.exceptions.Timeout:
        return False, "응답 시간 초과 — 네트워크 또는 서버 상태 확인"
    except requests.exceptions.ConnectionError as exc:
        return False, f"연결 실패 — 서버 주소 확인 ({exc})"
    except Exception as exc:
        msg = str(exc)
        if "401" in msg or "AUTH" in msg.upper():
            return False, "인증 실패 — Decoding 키를 확인하세요"
        return False, msg[:120]
