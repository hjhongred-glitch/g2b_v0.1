# -*- coding: utf-8 -*-
"""core/filter.py 단위 테스트."""
import pytest
from core.filter import keyword_match, filter_notices


# ── fixture ──────────────────────────────────────────────────────────────────

def _notice(공고번호="N001", 공고명="안전보건 컨설팅", 수요기관="서울시") -> dict:
    return {
        "공고번호": 공고번호,
        "공고명": 공고명,
        "수요기관": 수요기관,
        "공고URL": "http://example.com",
        "공고유형": "입찰공고",
        "분야": "용역",
        "공고일시": "",
        "마감일시": "",
        "추정가격": "",
        "공고기관": "",
    }


# ── keyword_match ─────────────────────────────────────────────────────────────

class TestKeywordMatch:
    def test_공고명_매칭(self):
        assert keyword_match(_notice(공고명="중대재해 예방 교육"), ["중대재해"]) is True

    def test_수요기관_매칭(self):
        assert keyword_match(_notice(수요기관="산업안전공단"), ["산업안전"]) is True

    def test_대소문자_무시(self):
        assert keyword_match(_notice(공고명="Safety 관리"), ["safety"]) is True

    def test_매칭_없음(self):
        assert keyword_match(_notice(공고명="도로 포장 공사"), ["안전보건"]) is False

    def test_빈_키워드_목록(self):
        assert keyword_match(_notice(), []) is False

    def test_여러_키워드_중_하나_매칭(self):
        assert keyword_match(_notice(공고명="산업안전 점검"), ["중대재해", "산업안전"]) is True


# ── filter_notices ────────────────────────────────────────────────────────────

class TestFilterNotices:
    def test_정상_필터(self):
        notices = [
            _notice("N001", "안전보건 컨설팅"),
            _notice("N002", "도로 포장 공사"),
            _notice("N003", "중대재해 예방"),
        ]
        result = filter_notices(notices, ["안전보건", "중대재해"], set())
        assert len(result) == 2
        ids = {n["공고번호"] for n in result}
        assert ids == {"N001", "N003"}

    def test_이미_발송된_항목_제외(self):
        notices = [_notice("N001"), _notice("N002")]
        result = filter_notices(notices, ["안전보건"], sent_ids={"N001"})
        assert all(n["공고번호"] != "N001" for n in result)

    def test_동일_공고번호_중복_제거(self):
        notices = [_notice("N001"), _notice("N001")]  # 동일 번호 2건
        result = filter_notices(notices, ["안전보건"], set())
        assert len(result) == 1

    def test_빈_키워드_시_결과_없음(self):
        result = filter_notices([_notice()], [], set())
        assert result == []

    def test_공고번호_없는_항목_무시(self):
        notices = [{"공고번호": "", "공고명": "안전보건", "수요기관": ""}]
        result = filter_notices(notices, ["안전보건"], set())
        assert result == []
