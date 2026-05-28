# -*- coding: utf-8 -*-
"""core/api.py 단위 테스트 (requests Mock)."""
import pytest
from unittest.mock import MagicMock, patch
from core.api import normalize, fetch_endpoint, _parse_body


# ── normalize ────────────────────────────────────────────────────────────────

class TestNormalize:
    def _raw(self) -> dict:
        return {
            "bidNtceNo": "20250528",
            "bidNtceOrd": "1",
            "bidNtceNm": "안전보건 컨설팅",
            "ntceInsttNm": "조달청",
            "dminsttNm": "서울시",
            "bidNtceDt": "2025052809",
            "bidClseDt": "2025060509",
            "bidNtceDtlUrl": "http://example.com",
            "presmptPrce": "5000000",
        }

    def test_공고번호_조합(self):
        n = normalize(self._raw(), "입찰공고", "용역")
        assert n["공고번호"] == "20250528-1"

    def test_모든_필드_존재(self):
        n = normalize(self._raw(), "입찰공고", "용역")
        expected_keys = ["공고번호", "공고명", "공고기관", "수요기관",
                         "공고일시", "마감일시", "공고URL", "추정가격",
                         "공고유형", "분야"]
        for k in expected_keys:
            assert k in n

    def test_추정가격_fallback(self):
        raw = self._raw()
        raw.pop("presmptPrce")
        raw["asignBdgtAmt"] = "9000000"
        n = normalize(raw, "입찰공고", "물품")
        assert n["추정가격"] == "9000000"

    def test_None_값은_빈문자열로(self):
        raw = self._raw()
        raw["dminsttNm"] = None
        n = normalize(raw, "입찰공고", "용역")
        assert n["수요기관"] == ""


# ── _parse_body ───────────────────────────────────────────────────────────────

class TestParseBody:
    def test_단건_dict_items(self):
        data = {"response": {"body": {"totalCount": "1", "items": {"bidNtceNo": "X"}}}}
        total, items = _parse_body(data)
        assert total == 1
        assert isinstance(items, list)
        assert len(items) == 1

    def test_복수_list_items(self):
        data = {"response": {"body": {"totalCount": "2",
                                       "items": [{"bidNtceNo": "A"}, {"bidNtceNo": "B"}]}}}
        total, items = _parse_body(data)
        assert total == 2
        assert len(items) == 2

    def test_items_null(self):
        data = {"response": {"body": {"totalCount": "0", "items": None}}}
        total, items = _parse_body(data)
        assert total == 0
        assert items == []


# ── fetch_endpoint (Mock) ────────────────────────────────────────────────────

class TestFetchEndpoint:
    def _mock_response(self, total: int, items: list) -> MagicMock:
        m = MagicMock()
        m.json.return_value = {
            "response": {"body": {"totalCount": str(total), "items": items}}
        }
        m.raise_for_status = MagicMock()
        return m

    def test_단일_페이지_정상_조회(self):
        with patch("core.api._make_session") as mock_session_factory:
            session = MagicMock()
            session.get.return_value = self._mock_response(
                2, [{"bidNtceNo": "A", "bidNtceOrd": "0"}, {"bidNtceNo": "B", "bidNtceOrd": "0"}]
            )
            mock_session_factory.return_value = session

            from core.api import fetch_endpoint
            result = fetch_endpoint("key", "someEndpoint", "202505280000", "202505281200", session=session)
            assert len(result) == 2

    def test_API_예외_시_빈_목록_반환(self):
        with patch("core.api._make_session") as mock_session_factory:
            session = MagicMock()
            session.get.side_effect = Exception("network error")
            mock_session_factory.return_value = session

            result = fetch_endpoint("key", "ep", "from", "to", session=session)
            assert result == []
