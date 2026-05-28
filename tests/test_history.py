# -*- coding: utf-8 -*-
"""core/history.py 단위 테스트."""
import csv
import pytest
from pathlib import Path
from core.history import load_sent_ids, append_sent


@pytest.fixture
def tmp_csv(tmp_path) -> Path:
    return tmp_path / "sent_history.csv"


class TestLoadSentIds:
    def test_파일_없으면_빈_집합(self, tmp_csv):
        assert load_sent_ids(tmp_csv) == set()

    def test_정상_로드(self, tmp_csv):
        tmp_csv.write_text(
            "공고번호,공고명,발송일시\nN001,테스트,2025-01-01\nN002,테스트2,2025-01-02\n",
            encoding="utf-8",
        )
        ids = load_sent_ids(tmp_csv)
        assert ids == {"N001", "N002"}

    def test_헤더만_있는_파일(self, tmp_csv):
        tmp_csv.write_text("공고번호,공고명,발송일시\n", encoding="utf-8")
        assert load_sent_ids(tmp_csv) == set()

    def test_빈_행_무시(self, tmp_csv):
        tmp_csv.write_text("공고번호,공고명,발송일시\nN001,테스트,2025-01-01\n\n", encoding="utf-8")
        assert load_sent_ids(tmp_csv) == {"N001"}


class TestAppendSent:
    def _make_notice(self, bid_no: str) -> dict:
        return {"공고번호": bid_no, "공고명": f"테스트 {bid_no}"}

    def test_신규_파일_생성(self, tmp_csv):
        append_sent(tmp_csv, [self._make_notice("N001")])
        assert tmp_csv.exists()
        rows = list(csv.reader(tmp_csv.open(encoding="utf-8")))
        assert rows[0] == ["공고번호", "공고명", "발송일시"]  # 헤더
        assert rows[1][0] == "N001"

    def test_기존_파일에_추가(self, tmp_csv):
        append_sent(tmp_csv, [self._make_notice("N001")])
        append_sent(tmp_csv, [self._make_notice("N002")])
        rows = list(csv.reader(tmp_csv.open(encoding="utf-8")))
        assert len(rows) == 3  # 헤더 + 2건
        # 헤더가 한 번만 기록됐는지 확인
        headers = [r for r in rows if r[0] == "공고번호"]
        assert len(headers) == 1

    def test_빈_목록_호출_시_파일_변화_없음(self, tmp_csv):
        append_sent(tmp_csv, [])
        assert not tmp_csv.exists()

    def test_load_후_추가된_항목_반영(self, tmp_csv):
        append_sent(tmp_csv, [self._make_notice("N001")])
        ids = load_sent_ids(tmp_csv)
        assert "N001" in ids
