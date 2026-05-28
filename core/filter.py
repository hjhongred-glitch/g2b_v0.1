# -*- coding: utf-8 -*-
"""키워드 필터링 및 중복 제거 모듈."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def keyword_match(notice: dict, keywords: list[str]) -> bool:
    """
    공고명 또는 수요기관명에 키워드가 하나라도 포함되면 True.

    대소문자 구분 없이 비교한다.
    """
    target = (
        (notice.get("공고명") or "") + " " + (notice.get("수요기관") or "")
    ).lower()
    return any(kw.lower() in target for kw in keywords)


def filter_notices(
    notices: list[dict],
    keywords: list[str],
    sent_ids: set[str],
) -> list[dict]:
    """
    공고 목록에서 키워드 매칭 + 미발송 공고만 추출.

    동일 호출 내 중복(공고번호 기준)도 제거한다.
    """
    if not keywords:
        logger.warning("키워드가 비어있어 필터링을 건너뜁니다.")
        return []

    seen: set[str] = set()
    result: list[dict] = []

    for notice in notices:
        bid_no = notice.get("공고번호", "")
        if not bid_no:
            continue
        if bid_no in sent_ids:
            continue
        if bid_no in seen:
            continue
        if not keyword_match(notice, keywords):
            continue
        seen.add(bid_no)
        result.append(notice)

    logger.info(
        "필터 결과: 전체 %d건 → 키워드매칭+신규 %d건",
        len(notices),
        len(result),
    )
    return result
