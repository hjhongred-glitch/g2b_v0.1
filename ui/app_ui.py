# -*- coding: utf-8 -*-
"""
Flet 기반 메인 UI.
화면 표시만 담당하고 비즈니스 로직을 직접 구현하지 않는다.
"""
from __future__ import annotations

import logging
import subprocess
import sys
import threading
from pathlib import Path

import flet as ft

from config import store as cfg_store
from config.model import (
    AppConfig, ApiServiceConfig, EndpointConfig,
    DEFAULT_API_BASE_URL, LOG_FORMAT_PRESETS, LOG_LEVELS, OUTPUT_FORMATS,
)
from scheduler.job import AlertScheduler, JobResult, run_job

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 색상 팔레트
# ─────────────────────────────────────────────────────────────────────────────
# 엔드포인트 기본 요청 파라미터 (사용자가 편집 가능)
_DEFAULT_EP_PARAMS: list[tuple[str, str]] = [
    ("numOfRows", "100"),
    ("inqryDiv",  "1"),
    ("type",      "json"),
]

C_PRIMARY   = "#1a73e8"
C_SUCCESS   = "#34a853"
C_ERROR     = "#ea4335"
C_WARN      = "#fbbc04"
C_BG        = "#f8f9fa"
C_CARD      = "#ffffff"
C_BORDER    = "#e0e0e0"
C_TEXT_MAIN = "#202124"
C_TEXT_SUB  = "#5f6368"


# ─────────────────────────────────────────────────────────────────────────────
# 공통 위젯 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _card(content: ft.Control, padding: int = 18) -> ft.Container:
    return ft.Container(
        content=content,
        bgcolor=C_CARD,
        border=ft.Border.all(1, C_BORDER),
        border_radius=12,
        padding=padding,
        margin=ft.Margin.only(bottom=10),
    )


def _label(text: str, size: int = 13, color: str = C_TEXT_SUB, weight=None) -> ft.Text:
    return ft.Text(text, size=size, color=color, weight=weight)


def _section_title(text: str) -> ft.Text:
    return ft.Text(text, size=14, weight=ft.FontWeight.W_600, color=C_TEXT_MAIN)


def _hint(text: str) -> ft.Text:
    return ft.Text(text, size=11, color=C_TEXT_SUB, italic=True)


def _text_field(label: str, **kwargs) -> ft.TextField:
    """전체 너비 기본 TextField."""
    return ft.TextField(label=label, border_radius=8, **kwargs)


def _number_field(label: str, value: str, width: int = 88) -> ft.TextField:
    return ft.TextField(
        label=label, value=value, width=width,
        border_radius=8, keyboard_type=ft.KeyboardType.NUMBER,
        text_align=ft.TextAlign.CENTER,
    )


def _scroll_view(controls: list) -> ft.ListView:
    return ft.ListView(controls=controls, spacing=0, expand=True)


# ─────────────────────────────────────────────────────────────────────────────
# 대시보드 탭
# ─────────────────────────────────────────────────────────────────────────────

class DashboardView:
    def __init__(self, scheduler: AlertScheduler, on_run: callable) -> None:
        self._scheduler = scheduler
        self._on_run    = on_run

        self._status_text      = ft.Text("준비", size=14, color=C_TEXT_SUB)
        self._next_run_text    = ft.Text("—",   size=14, color=C_TEXT_MAIN)
        self._last_run_text    = ft.Text("—",   size=13, color=C_TEXT_SUB)
        self._last_result_text = ft.Text("—",   size=13, color=C_TEXT_SUB)
        self._last_file_text   = ft.Text("—",   size=12, color=C_TEXT_SUB, selectable=True)
        self._run_btn = ft.ElevatedButton(
            "▶  지금 실행하기",
            on_click=self._handle_run,
            bgcolor=C_PRIMARY, color="white", height=44,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
            expand=True,
        )
        self._progress = ft.ProgressBar(visible=False, color=C_PRIMARY)

    def build(self) -> ft.Control:
        self._refresh_schedule_info()
        return _scroll_view([
            _card(ft.Column([
                _section_title("📊 실행 현황"),
                ft.Divider(height=10, color=C_BORDER),
                ft.Row([_label("스케줄러 상태", size=13), self._status_text],      spacing=12),
                ft.Row([_label("다음 실행",     size=13), self._next_run_text],    spacing=12),
                ft.Row([_label("마지막 실행",   size=13), self._last_run_text],    spacing=12),
                ft.Row([_label("마지막 결과",   size=13), self._last_result_text], spacing=12),
                ft.Row([_label("저장 파일",     size=13), self._last_file_text],   spacing=12),
            ], spacing=8)),
            self._progress,
            self._run_btn,
        ])

    def _handle_run(self, _e) -> None:
        self._set_running(True)
        threading.Thread(target=self._do_run, daemon=True).start()

    def _do_run(self) -> None:
        result = run_job()
        self._on_run(result)
        self.update_result(result)

    def _set_running(self, running: bool) -> None:
        self._run_btn.disabled = running
        self._progress.visible = running
        if running:
            self._status_text.value = "실행 중..."
            self._status_text.color = C_WARN
        else:
            self._refresh_schedule_info()
        try:
            self._run_btn.page.update()
        except Exception:
            pass

    def update_result(self, result: JobResult) -> None:
        self._last_run_text.value    = result.ran_at.strftime("%Y-%m-%d %H:%M:%S")
        self._last_result_text.value = result.summary()
        self._last_result_text.color = C_ERROR if result.error else C_SUCCESS
        self._last_file_text.value   = result.saved_file or "—"
        self._set_running(False)

    def _refresh_schedule_info(self) -> None:
        if self._scheduler.is_running:
            self._status_text.value = "실행 중"
            self._status_text.color = C_SUCCESS
            nrt = self._scheduler.next_run_time
            self._next_run_text.value = nrt.strftime("%Y-%m-%d %H:%M") if nrt else "—"
        else:
            self._status_text.value = "중지됨"
            self._status_text.color = C_ERROR


# ─────────────────────────────────────────────────────────────────────────────
# 설정 탭 (서브탭 4개)
# ─────────────────────────────────────────────────────────────────────────────

class SettingsView:
    def __init__(self, scheduler: AlertScheduler) -> None:
        self._scheduler = scheduler
        self._cfg: AppConfig = cfg_store.load_config()

        # ── 서브탭 0: API / 검색 ──────────────────────────────────────────────
        self._api_key_field = _text_field(
            "API 키 (Decoding)",
            password=True, can_reveal_password=True,
            value=cfg_store.get_api_key(),
            hint_text="공공데이터포털 Decoding 키",
        )
        self._keyword_input = _text_field(
            "키워드 추가", hint_text="입력 후 Enter 또는 + 버튼",
            expand=True, on_submit=self._add_keyword,
        )
        self._keywords_col = ft.Column(spacing=6)
        self._rebuild_keyword_chips()

        # ── 서브탭 1: 알림 / 출력 ─────────────────────────────────────────────
        self._cb_email = ft.Checkbox(label="이메일로 발송", value=self._cfg.enable_email)
        self._sender_field = _text_field(
            "발신자 Gmail 주소", value=self._cfg.email.sender,
            hint_text="example@gmail.com",
        )
        self._gmail_pw_field = _text_field(
            "Gmail 앱 비밀번호 (16자리)",
            password=True, can_reveal_password=True,
            value=cfg_store.get_gmail_password(),
            hint_text="Gmail → 구글 계정 → 보안 → 2단계 인증 → 앱 비밀번호",
        )
        self._recipients_field = _text_field(
            "수신자 이메일 (쉼표로 구분)",
            value=", ".join(self._cfg.email.recipients),
            hint_text="a@gmail.com, b@gmail.com",
        )

        self._cb_file = ft.Checkbox(label="파일로 저장", value=self._cfg.output.enable_file)
        self._file_dir_field = _text_field(
            "파일 저장 경로",
            value=self._cfg.output.file_dir,
            hint_text=f"비워두면: {cfg_store.DATA_DIR / 'reports'}",
        )
        self._file_format_dd = ft.Dropdown(
            label="파일 형식",
            value=self._cfg.output.file_format,
            options=[ft.DropdownOption(key=f, text=f.upper()) for f in OUTPUT_FORMATS],
            border_radius=8,
            width=140,
        )

        # ── 서브탭 2: 스케줄 / 알림 ───────────────────────────────────────────
        self._hour_field     = _number_field("시 (0~23)", str(self._cfg.schedule_hour))
        self._minute_field   = _number_field("분 (0~59)", str(self._cfg.schedule_minute))
        self._lookback_field = _number_field("시간", str(self._cfg.lookback_hours), width=88)
        self._cb_os = ft.Checkbox(
            label="OS 알림 (macOS 알림센터 / Windows 토스트)",
            value=self._cfg.enable_os_notification,
        )

        # ── 서브탭 3: 로그 설정 ───────────────────────────────────────────────
        self._log_dir_field = _text_field(
            "로그 저장 경로",
            value=self._cfg.log.log_dir,
            hint_text=f"비워두면: {cfg_store.DATA_DIR / 'app.log'}",
        )
        self._log_level_dd = ft.Dropdown(
            label="로그 레벨", value=self._cfg.log.log_level,
            options=[ft.DropdownOption(key=lv, text=lv) for lv in LOG_LEVELS],
            border_radius=8,
        )
        current_fmt = self._cfg.log.log_format
        preset_key = next(
            (k for k, v in LOG_FORMAT_PRESETS.items() if v == current_fmt and k != "직접입력"),
            "직접입력",
        )
        self._log_format_dd = ft.Dropdown(
            label="로그 포맷 프리셋", value=preset_key,
            options=[ft.DropdownOption(key=k, text=k) for k in LOG_FORMAT_PRESETS],
            border_radius=8,
            on_select=self._on_format_preset_change,
        )
        self._log_format_field = _text_field(
            "포맷 문자열", value=current_fmt,
            hint_text="%(asctime)s  %(levelname)s  %(name)s  %(lineno)d  %(message)s",
            multiline=True, min_lines=2, max_lines=3,
            read_only=(preset_key != "직접입력"),
        )
        self._log_max_bytes_field    = _number_field("최대 크기 (bytes)", str(self._cfg.log.log_max_bytes), width=160)
        self._log_backup_count_field = _number_field("백업 수", str(self._cfg.log.log_backup_count), width=88)

        # ── 서브탭 4: API 서비스 관리 ────────────────────────────────────────────
        self._service_widgets: list[dict] = []
        self._endpoint_list_view = ft.ListView(expand=True, spacing=0)
        self._rebuild_service_cards()

        # FilePicker (build_app에서 set_pickers로 주입)
        self._log_picker: ft.FilePicker | None    = None
        self._output_picker: ft.FilePicker | None = None

        # 공통 저장 메시지
        self._save_msg = ft.Text("", size=13, color=C_SUCCESS)

    def set_pickers(
        self,
        log_picker: ft.FilePicker,
        output_picker: ft.FilePicker,
    ) -> None:
        self._log_picker    = log_picker
        self._output_picker = output_picker

    # ── 키워드 관리 ──────────────────────────────────────────────────────────

    def _rebuild_keyword_chips(self) -> None:
        self._keywords_col.controls = [
            ft.Chip(
                label=ft.Text(kw),
                bgcolor="#e8f0fe",
                delete_icon_color=C_ERROR,
                on_delete=lambda e, k=kw: self._remove_keyword(k),
            )
            for kw in self._cfg.keywords
        ]

    def _add_keyword(self, _e=None) -> None:
        kw = self._keyword_input.value.strip()
        if kw and kw not in self._cfg.keywords:
            self._cfg.keywords.append(kw)
            self._keyword_input.value = ""
            self._rebuild_keyword_chips()
            try:
                self._keywords_col.page.update()
            except Exception:
                pass

    def _remove_keyword(self, kw: str) -> None:
        if kw in self._cfg.keywords:
            self._cfg.keywords.remove(kw)
            self._rebuild_keyword_chips()
            try:
                self._keywords_col.page.update()
            except Exception:
                pass

    # ── 로그 포맷 프리셋 연동 ────────────────────────────────────────────────

    def _on_format_preset_change(self, _e=None) -> None:
        key = self._log_format_dd.value
        if key == "직접입력":
            self._log_format_field.read_only = False
        else:
            self._log_format_field.value    = LOG_FORMAT_PRESETS.get(key, "")
            self._log_format_field.read_only = True
        try:
            self._log_format_field.page.update()
        except Exception:
            pass

    # ── 폴더 선택 (FilePicker) ───────────────────────────────────────────────

    async def _pick_log_dir(self, _e=None) -> None:
        if self._log_picker is None:
            return
        initial = self._log_dir_field.value.strip() or str(cfg_store.DATA_DIR)
        result = await self._log_picker.get_directory_path(
            dialog_title="로그 저장 폴더 선택",
            initial_directory=initial,
        )
        if result:
            self._log_dir_field.value = result
            try:
                self._log_dir_field.page.update()
            except Exception:
                pass

    async def _pick_output_dir(self, _e=None) -> None:
        if self._output_picker is None:
            return
        initial = self._file_dir_field.value.strip() or str(cfg_store.DATA_DIR / "reports")
        result = await self._output_picker.get_directory_path(
            dialog_title="파일 출력 폴더 선택",
            initial_directory=initial,
        )
        if result:
            self._file_dir_field.value = result
            try:
                self._file_dir_field.page.update()
            except Exception:
                pass

    # ── 저장된 출력 폴더 열기 ────────────────────────────────────────────────

    def _open_output_folder(self, _e=None) -> None:
        folder = self._file_dir_field.value.strip() or str(cfg_store.DATA_DIR / "reports")
        Path(folder).mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", folder])
            elif sys.platform == "win32":
                subprocess.run(["explorer", folder])
        except Exception:
            pass

    # ── 저장 ─────────────────────────────────────────────────────────────────

    def _save(self, _e) -> None:
        # API 키
        cfg_store.set_api_key(self._api_key_field.value.strip())

        # API 서비스 (엔드포인트 탭 위젯 → cfg 반영)
        self._read_services_to_config()

        # 이메일
        self._cfg.enable_email            = self._cb_email.value
        self._cfg.email.sender            = self._sender_field.value.strip()
        self._cfg.email.recipients        = [
            r.strip() for r in self._recipients_field.value.split(",") if r.strip()
        ]
        cfg_store.set_gmail_password(self._gmail_pw_field.value.strip())

        # 파일 출력
        self._cfg.output.enable_file  = self._cb_file.value
        self._cfg.output.file_dir     = self._file_dir_field.value.strip()
        self._cfg.output.file_format  = self._file_format_dd.value or "csv"

        # 스케줄
        try:
            hour     = max(0,  min(23, int(self._hour_field.value     or 9)))
            minute   = max(0,  min(59, int(self._minute_field.value   or 0)))
            lookback = max(1,          int(self._lookback_field.value or 24))
        except ValueError:
            self._show_msg("시간/분/조회범위는 숫자로 입력해주세요.", error=True)
            return
        self._cfg.schedule_hour               = hour
        self._cfg.schedule_minute             = minute
        self._cfg.lookback_hours              = lookback
        self._cfg.enable_os_notification      = self._cb_os.value

        # 로그
        self._cfg.log.log_dir          = self._log_dir_field.value.strip()
        self._cfg.log.log_level        = self._log_level_dd.value or "INFO"
        self._cfg.log.log_format       = self._log_format_field.value.strip() or LOG_FORMAT_PRESETS["기본"]
        try:
            self._cfg.log.log_max_bytes    = max(65536, int(self._log_max_bytes_field.value    or 1048576))
            self._cfg.log.log_backup_count = max(0,     int(self._log_backup_count_field.value or 3))
        except ValueError:
            pass

        cfg_store.save_config(self._cfg)
        self._scheduler.reschedule(hour, minute)
        self._show_msg(f"✓ 저장 완료  (매일 {hour:02d}:{minute:02d} 실행)")

    def _show_msg(self, text: str, error: bool = False) -> None:
        self._save_msg.value = text
        self._save_msg.color = C_ERROR if error else C_SUCCESS
        try:
            self._save_msg.page.update()
        except Exception:
            pass

    # ── API 서비스 관리 ──────────────────────────────────────────────────────

    def _rebuild_service_cards(self) -> None:
        """_cfg.api_services 목록으로 서비스 카드 전체 재생성."""
        self._service_widgets = []
        controls: list[ft.Control] = []
        for idx, svc in enumerate(self._cfg.api_services):
            card, w = self._make_service_card(idx, svc)
            self._service_widgets.append(w)
            controls.append(card)
        controls.append(
            ft.Container(
                content=ft.TextButton(
                    "+ API 서비스 추가",
                    icon=ft.Icons.ADD,
                    on_click=self._add_service,
                    style=ft.ButtonStyle(color=C_PRIMARY),
                ),
                margin=ft.Margin.only(top=4),
            )
        )
        self._endpoint_list_view.controls.clear()
        self._endpoint_list_view.controls.extend(controls)
        try:
            self._endpoint_list_view.page.update()
        except Exception:
            pass

    def _read_services_to_config(self) -> None:
        """위젯 값을 읽어 self._cfg.api_services 갱신."""
        services = []
        for w in self._service_widgets:
            endpoints = []
            for ep_w in w["ep_list"]:
                ep_params = {
                    p["key_f"].value.strip(): p["value_f"].value.strip()
                    for p in ep_w["param_rows"]
                    if p["key_f"].value.strip()
                }
                endpoints.append(EndpointConfig(
                    endpoint=ep_w["endpoint_f"].value.strip(),
                    category=ep_w["category_f"].value.strip(),
                    enabled=ep_w["enabled_cb"].value,
                    extra_params=ep_params,
                ))
            services.append(ApiServiceConfig(
                name=w["name_f"].value.strip(),
                base_url=w["base_url_f"].value.strip() or DEFAULT_API_BASE_URL,
                notice_type=w["notice_type_f"].value.strip(),
                enabled=w["enabled_sw"].value,
                endpoints=endpoints,
            ))
        self._cfg.api_services = services

    def _add_service(self, _e=None) -> None:
        self._read_services_to_config()
        self._cfg.api_services.append(ApiServiceConfig(
            name="새 서비스",
            base_url=DEFAULT_API_BASE_URL,
            notice_type="입찰공고",
            enabled=True,
            endpoints=[EndpointConfig("getBidPblancListInfoServcPPSSrch", "용역")],
        ))
        self._rebuild_service_cards()

    def _make_service_card(self, svc_idx: int, svc: ApiServiceConfig) -> tuple[ft.Control, dict]:
        """서비스 카드 위젯과 위젯 참조 dict 반환."""
        enabled_sw = ft.Switch(value=svc.enabled, active_color=C_PRIMARY)
        # Column 단독 사용이므로 label= 사용 무방 (서비스명은 단독 행)
        name_f = ft.TextField(label="서비스명", value=svc.name, border_radius=6)
        # Row 안 TextField — hint_text= 사용 (floating label 겹침 방지)
        notice_type_f = ft.TextField(
            hint_text="공고유형 (예: 입찰공고)",
            value=svc.notice_type, border_radius=6, width=160,
        )
        base_url_f = ft.TextField(
            hint_text=f"Base URL (기본: {DEFAULT_API_BASE_URL})",
            value=svc.base_url, border_radius=6,
        )
        ep_list: list[dict] = []
        ep_col = ft.Column(spacing=4)

        def _rebuild_ep_col() -> None:
            ep_col.controls = [_make_ep_row(ep_w) for ep_w in ep_list]
            try:
                ep_col.page.update()
            except Exception:
                pass

        def _make_ep_row(ep_w: dict) -> ft.Container:
            params_col = ep_w["params_col"]

            def _rebuild_params() -> None:
                params_col.controls = [_make_param_row(p) for p in ep_w["param_rows"]]
                try:
                    params_col.page.update()
                except Exception:
                    pass

            def _make_param_row(p: dict) -> ft.Row:
                def _del_p(_e, _p=p):
                    if _p in ep_w["param_rows"]:
                        ep_w["param_rows"].remove(_p)
                        _rebuild_params()
                return ft.Row([
                    ft.Container(content=p["key_f"],   width=150),
                    ft.Text("=", size=13, color=C_TEXT_SUB),
                    ft.Container(content=p["value_f"], expand=True),
                    ft.IconButton(
                        icon=ft.Icons.REMOVE_CIRCLE_OUTLINE, icon_color=C_ERROR,
                        icon_size=15, tooltip="파라미터 삭제", on_click=_del_p,
                    ),
                ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER)

            def _add_param(_e=None) -> None:
                ep_w["param_rows"].append({
                    "key_f":   ft.TextField(hint_text="키",  border_radius=6, dense=True),
                    "value_f": ft.TextField(hint_text="값", border_radius=6, dense=True),
                })
                _rebuild_params()

            def _del_ep(_e, _w=ep_w):
                if _w in ep_list:
                    ep_list.remove(_w)
                    _rebuild_ep_col()

            def _test_ep(_e) -> None:
                from core import api as api_mod
                # Flet 0.85.2: ControlEvent.page (control 속성 없음)
                page = _e.page
                if page is None:
                    logger.warning("_test_ep: page is None")
                    return
                api_key = self._api_key_field.value.strip() or cfg_store.get_api_key()
                ep_name = ep_w["endpoint_f"].value.strip()
                if not ep_name:
                    logger.warning("_test_ep: ep_name is empty")
                    return

                result_txt = ft.Text("연결 테스트 중...", size=13, color=C_TEXT_SUB)

                dlg = ft.AlertDialog(
                    title=ft.Text("연결 테스트", weight=ft.FontWeight.W_600),
                    content=ft.Column([
                        ft.Text(ep_name, size=11, color=C_TEXT_SUB, selectable=True),
                        ft.Divider(height=8),
                        result_txt,
                    ], tight=True, spacing=4),
                    actions=[
                        # Flet 0.85.2: page.pop_dialog() 로 닫기
                        ft.TextButton("닫기", on_click=lambda _: page.pop_dialog()),
                    ],
                    actions_alignment=ft.MainAxisAlignment.END,
                )
                # Flet 0.85.2: page.show_dialog() 로 표시
                page.show_dialog(dlg)

                def _run():
                    try:
                        ep_params = {
                            p["key_f"].value.strip(): p["value_f"].value.strip()
                            for p in ep_w["param_rows"]
                            if p["key_f"].value.strip()
                        }
                        tmp_svc = ApiServiceConfig(
                            name="테스트",
                            base_url=base_url_f.value.strip() or DEFAULT_API_BASE_URL,
                            notice_type="",
                            enabled=True,
                            endpoints=[EndpointConfig(
                                endpoint=ep_name,
                                category=ep_w["category_f"].value.strip(),
                                enabled=True,
                                extra_params=ep_params,
                            )],
                        )
                        ok, msg = api_mod.test_connection(api_key, tmp_svc)
                        result_txt.value = msg
                        result_txt.color = C_SUCCESS if ok else C_ERROR
                        page.update()
                    except Exception as exc:
                        logger.exception("연결 테스트 실행 오류")
                        result_txt.value = f"오류: {exc}"
                        result_txt.color = C_ERROR
                        try:
                            page.update()
                        except Exception:
                            pass

                threading.Thread(target=_run, daemon=True).start()

            # 초기 파라미터 행 렌더링
            params_col.controls = [_make_param_row(p) for p in ep_w["param_rows"]]

            return ft.Container(
                content=ft.Column([
                    # 함수명 + 분야 + 테스트 + 삭제
                    ft.Row([
                        ep_w["enabled_cb"],
                        ft.Container(content=ep_w["endpoint_f"], expand=True),
                        ep_w["category_f"],
                        ft.IconButton(
                            icon=ft.Icons.NETWORK_CHECK, icon_color=C_PRIMARY,
                            icon_size=18, tooltip="연결 테스트", on_click=_test_ep,
                        ),
                        ft.IconButton(
                            icon=ft.Icons.REMOVE_CIRCLE_OUTLINE, icon_color=C_ERROR,
                            icon_size=18, tooltip="엔드포인트 삭제", on_click=_del_ep,
                        ),
                    ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    # 파라미터 섹션
                    ft.Container(
                        content=ft.Column([
                            ft.Text(
                                "🔒 자동 파라미터: serviceKey · pageNo · inqryBgnDt · inqryEndDt",
                                size=11, color=C_TEXT_SUB, italic=True,
                            ),
                            ft.Row([
                                _label("📋 요청 파라미터", size=11,
                                       weight=ft.FontWeight.W_500, color=C_TEXT_MAIN),
                                ft.Container(expand=True),
                                ft.TextButton(
                                    "+ 추가", icon=ft.Icons.ADD, on_click=_add_param,
                                    style=ft.ButtonStyle(color=C_PRIMARY),
                                ),
                            ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                            params_col,
                        ], spacing=4),
                        bgcolor="#f8f9fa",
                        border_radius=6,
                        padding=ft.Padding.symmetric(horizontal=8, vertical=6),
                        margin=ft.Margin.only(top=4),
                    ),
                ], spacing=6),
                bgcolor="#eef2ff",
                border_radius=8,
                padding=10,
                margin=ft.Margin.only(bottom=8),
            )

        def _new_ep_widget(
            endpoint: str = "", category: str = "",
            enabled: bool = True, extra_params: dict | None = None,
        ) -> dict:
            params_list = list(extra_params.items()) if extra_params else list(_DEFAULT_EP_PARAMS)

            def _make_kv(k: str = "", v: str = "") -> dict:
                # Row 안 TextField — label= 대신 hint_text= 사용 (floating label 겹침 방지)
                return {
                    "key_f":   ft.TextField(hint_text="키",  value=k, border_radius=6, dense=True),
                    "value_f": ft.TextField(hint_text="값", value=v, border_radius=6, dense=True),
                }

            return {
                "enabled_cb": ft.Checkbox(value=enabled, tooltip="활성화"),
                # Row 안 TextField — hint_text= 사용
                "endpoint_f": ft.TextField(
                    hint_text="엔드포인트 함수명 (예: getBidPblancListInfo...)",
                    value=endpoint, border_radius=6,
                ),
                "category_f": ft.TextField(
                    hint_text="분야",
                    value=category, border_radius=6, width=90,
                ),
                "param_rows": [_make_kv(k, v) for k, v in params_list],
                "params_col": ft.Column(spacing=2),
            }

        def _add_ep(_e=None) -> None:
            ep_list.append(_new_ep_widget())
            _rebuild_ep_col()

        for ep in svc.endpoints:
            ep_list.append(_new_ep_widget(ep.endpoint, ep.category, ep.enabled, ep.extra_params))
        ep_col.controls = [_make_ep_row(ep_w) for ep_w in ep_list]

        def _delete_svc(_e=None, _svc=svc) -> None:
            if _svc in self._cfg.api_services:
                self._cfg.api_services.remove(_svc)
                self._rebuild_service_cards()

        w = {
            "enabled_sw": enabled_sw,
            "name_f": name_f,
            "base_url_f": base_url_f,
            "notice_type_f": notice_type_f,
            "ep_list": ep_list,
        }

        card = _card(ft.Column([
            # ── 헤더: 서비스 번호 + 활성 스위치 + 삭제 ──────────────────────
            ft.Row([
                _section_title(f"서비스 {svc_idx + 1}"),
                ft.Container(expand=True),
                _label("활성화", size=12),
                enabled_sw,
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE, icon_color=C_ERROR,
                    tooltip="서비스 삭제", on_click=_delete_svc,
                    icon_size=18,
                ),
            ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(height=4, color=C_BORDER),
            # ── 서비스명 ──────────────────────────────────────────────────────
            name_f,
            # ── 공고유형 + Base URL ───────────────────────────────────────────
            ft.Row([
                ft.Container(content=notice_type_f, width=160),
                ft.Container(content=base_url_f, expand=True),
            ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            # ── 엔드포인트 목록 ───────────────────────────────────────────────
            ft.Divider(height=8, color=C_BORDER),
            ft.Row([
                _label("엔드포인트 목록", size=12, weight=ft.FontWeight.W_500),
                ft.Container(expand=True),
                ft.TextButton(
                    "+ 엔드포인트 추가", icon=ft.Icons.ADD, on_click=_add_ep,
                    style=ft.ButtonStyle(color=C_PRIMARY),
                ),
            ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ep_col,
        ], spacing=8), padding=14)

        return card, w

    # ── 서브탭 빌드 ──────────────────────────────────────────────────────────

    def _build_api_tab(self) -> ft.Control:
        return _scroll_view([
            _card(ft.Column([
                _section_title("🔑 API 키"),
                self._api_key_field,
            ], spacing=12)),
            _card(ft.Column([
                _section_title("🔍 키워드"),
                _hint("공고명 또는 수요기관명에 포함된 키워드로 필터링합니다."),
                ft.Row([
                    self._keyword_input,
                    ft.IconButton(icon=ft.Icons.ADD_CIRCLE, icon_color=C_PRIMARY, on_click=self._add_keyword),
                ], spacing=8),
                ft.Container(content=self._keywords_col, padding=ft.Padding.only(top=4)),
            ], spacing=10)),
        ])

    def _build_notification_tab(self) -> ft.Control:
        return _scroll_view([
            _card(ft.Column([
                ft.Row([_section_title("📧 이메일 알림"), self._cb_email], spacing=12,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                self._sender_field,
                self._gmail_pw_field,
                self._recipients_field,
                _hint("Gmail → 구글 계정 관리 → 보안 → 2단계 인증 → 앱 비밀번호"),
            ], spacing=12)),
            _card(ft.Column([
                ft.Row([_section_title("📁 파일 출력"), self._cb_file], spacing=12,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([
                    ft.Container(content=self._file_dir_field, expand=True),
                    ft.IconButton(
                        icon=ft.Icons.FOLDER_OPEN,
                        icon_color=C_PRIMARY,
                        tooltip="폴더 선택",
                        on_click=self._pick_output_dir,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.OPEN_IN_NEW,
                        icon_color=C_TEXT_SUB,
                        tooltip="저장 폴더 열기",
                        on_click=self._open_output_folder,
                    ),
                ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Row([_label("파일 형식:"), self._file_format_dd], spacing=12,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
                _hint("CSV: Excel에서 바로 열기 가능 / HTML: 이메일과 동일한 표 형식"),
            ], spacing=12)),
        ])

    def _build_schedule_tab(self) -> ft.Control:
        return _scroll_view([
            _card(ft.Column([
                _section_title("⏰ 매일 자동 실행 시각"),
                _hint("앱이 실행 중인 동안 매일 지정 시각에 자동으로 공고를 조회합니다."),
                ft.Row([
                    self._hour_field,
                    _label("시", size=14),
                    self._minute_field,
                    _label("분", size=14),
                ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ], spacing=12)),
            _card(ft.Column([
                _section_title("🔎 조회 범위"),
                _hint("실행 시각 기준으로 지정 시간 전까지의 공고를 조회합니다."),
                ft.Row([
                    self._lookback_field,
                    _label("시간 전부터 현재까지", size=14),
                ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ], spacing=12)),
            _card(ft.Column([
                _section_title("🔔 OS 알림"),
                self._cb_os,
            ], spacing=12)),
        ])

    def _build_log_tab(self) -> ft.Control:
        return _scroll_view([
            _card(ft.Column([
                _section_title("📁 로그 파일 경로"),
                ft.Row([
                    ft.Container(content=self._log_dir_field, expand=True),
                    ft.IconButton(
                        icon=ft.Icons.FOLDER_OPEN,
                        icon_color=C_PRIMARY,
                        tooltip="폴더 선택",
                        on_click=self._pick_log_dir,
                    ),
                ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                _hint(f"기본: {cfg_store.DATA_DIR / 'app.log'}  (파일은 크기 초과 시 자동 롤오버)"),
            ], spacing=10)),
            _card(ft.Column([
                _section_title("🎚️ 레벨 및 포맷"),
                self._log_level_dd,
                self._log_format_dd,
                self._log_format_field,
                _hint("사용 가능: %(asctime)s  %(levelname)s  %(name)s  %(lineno)d  %(message)s"),
            ], spacing=12)),
            _card(ft.Column([
                _section_title("🔄 파일 로테이션"),
                ft.Row([
                    self._log_max_bytes_field,
                    _label("bytes  백업"),
                    self._log_backup_count_field,
                    _label("개"),
                ], spacing=10, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ], spacing=12)),
        ])

    def _build_api_endpoints_tab(self) -> ft.Control:
        return ft.Column([
            _card(ft.Column([
                _section_title("🔗 API 서비스 관리"),
                _hint("각 서비스의 Base URL, 공고유형, 엔드포인트를 설정합니다. 저장 버튼으로 반영됩니다."),
            ], spacing=6)),
            ft.Container(content=self._endpoint_list_view, expand=True),
        ], spacing=0, expand=True)

    # ── 전체 설정 탭 빌드 ────────────────────────────────────────────────────

    def build(self) -> ft.Control:
        return ft.Column(
            controls=[
                ft.Tabs(
                    length=5,
                    selected_index=0,
                    animation_duration=150,
                    content=ft.Column(
                        expand=True,
                        controls=[
                            ft.TabBar(
                                scrollable=True,
                                tabs=[
                                    ft.Tab(label="API / 검색"),
                                    ft.Tab(label="알림 / 출력"),
                                    ft.Tab(label="스케줄"),
                                    ft.Tab(label="로그 설정"),
                                    ft.Tab(label="엔드포인트"),
                                ],
                            ),
                            ft.TabBarView(
                                expand=True,
                                controls=[
                                    ft.Container(self._build_api_tab(),             padding=ft.Padding.only(top=10), expand=True),
                                    ft.Container(self._build_notification_tab(),    padding=ft.Padding.only(top=10), expand=True),
                                    ft.Container(self._build_schedule_tab(),        padding=ft.Padding.only(top=10), expand=True),
                                    ft.Container(self._build_log_tab(),             padding=ft.Padding.only(top=10), expand=True),
                                    ft.Container(self._build_api_endpoints_tab(),   padding=ft.Padding.only(top=10), expand=True),
                                ],
                            ),
                        ],
                    ),
                    expand=True,
                ),
                ft.Divider(height=1, color=C_BORDER),
                ft.Container(
                    content=ft.Row(
                        [
                            ft.ElevatedButton(
                                "💾  설정 저장",
                                on_click=self._save,
                                bgcolor=C_PRIMARY, color="white", height=42,
                                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
                            ),
                            self._save_msg,
                        ],
                        spacing=16,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    padding=ft.Padding.symmetric(vertical=10),
                ),
            ],
            expand=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 로그 탭
# ─────────────────────────────────────────────────────────────────────────────

class LogView:
    def __init__(self) -> None:
        self._log_list = ft.ListView(expand=True, spacing=2, auto_scroll=True)
        self._file_picker: ft.FilePicker | None = None

        cfg = cfg_store.load_config()
        self._current_path: Path = cfg_store.get_log_file(cfg.log)
        self._path_text = ft.Text(
            str(self._current_path),
            size=11, color=C_TEXT_SUB, expand=True,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
        self._load_logs()

    def set_file_picker(self, picker: ft.FilePicker) -> None:
        self._file_picker = picker

    # 로그 레벨별 색상 (어두운 배경 기준)
    _LOG_COLORS = {
        "ERROR": C_ERROR,          # 빨강
        "오류":  C_ERROR,
        "WARN":  "#fbbc04",        # 노랑
        "주의":  "#fbbc04",
        "DEBUG": "#888888",        # 회색
        "INFO":  "#d4d4d4",        # 밝은 회색 (기본)
    }
    _MAX_LINES = 200

    def _line_color(self, line: str) -> str:
        for key, color in self._LOG_COLORS.items():
            if key in line:
                return color
        return "#d4d4d4"

    def _load_logs(self, path: Path | None = None) -> None:
        if path is not None:
            self._current_path = path
        self._path_text.value = str(self._current_path)
        self._log_list.controls.clear()

        if not self._current_path.exists():
            self._log_list.controls.append(
                ft.Text("로그 파일이 없습니다.", color="#888888", size=13)
            )
            return

        try:
            lines = self._current_path.read_text(encoding="utf-8").splitlines()
            tail = lines[-self._MAX_LINES:]
            self._log_list.controls.extend(
                ft.Text(
                    line, size=12,
                    color=self._line_color(line),
                    selectable=True,
                    font_family="monospace",
                )
                for line in tail
            )
        except Exception as exc:
            self._log_list.controls.append(
                ft.Text(f"로그 읽기 실패: {exc}", color=C_ERROR, size=13)
            )

    async def _pick_log_file(self, _e=None) -> None:
        if self._file_picker is None:
            return
        files = await self._file_picker.pick_files(
            dialog_title="로그 파일 선택",
            initial_directory=str(self._current_path.parent),
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["log", "txt"],
        )
        if files and files[0].path:
            self._load_logs(Path(files[0].path))
            try:
                self._log_list.page.update()
            except Exception:
                pass

    def _refresh(self, _e) -> None:
        self._load_logs()
        try:
            self._log_list.page.update()
        except Exception:
            pass

    def _open_folder(self, _e) -> None:
        folder = str(self._current_path.parent)
        try:
            if sys.platform == "darwin":
                subprocess.run(["open", folder])
            elif sys.platform == "win32":
                subprocess.run(["explorer", folder])
        except Exception:
            pass

    def build(self) -> ft.Control:
        return ft.Column([
            ft.Row([
                ft.IconButton(
                    icon=ft.Icons.FOLDER_OPEN,
                    icon_color=C_PRIMARY,
                    tooltip="로그 파일 선택",
                    on_click=self._pick_log_file,
                ),
                ft.IconButton(
                    icon=ft.Icons.REFRESH,
                    icon_color=C_TEXT_SUB,
                    tooltip="새로고침",
                    on_click=self._refresh,
                ),
                ft.IconButton(
                    icon=ft.Icons.OPEN_IN_NEW,
                    icon_color=C_TEXT_SUB,
                    tooltip="폴더 열기",
                    on_click=self._open_folder,
                ),
                self._path_text,
            ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(height=6, color=C_BORDER),
            ft.Container(content=self._log_list, bgcolor="#1e1e1e", border_radius=8, padding=12, expand=True),
        ], spacing=8, expand=True)


# ─────────────────────────────────────────────────────────────────────────────
# 앱 진입점
# ─────────────────────────────────────────────────────────────────────────────

def build_app(scheduler: AlertScheduler):

    def main(page: ft.Page) -> None:
        page.title          = "조달청 입찰공고 알리미"
        page.window.width   = 780
        page.window.height  = 700
        page.window.min_width  = 640
        page.window.min_height = 560
        page.bgcolor = C_BG
        page.padding = 0
        page.fonts   = {"monospace": "Courier New"}
        page.window.prevent_close = True

        def on_window_event(e: ft.WindowEvent) -> None:
            if e.type == ft.WindowEventType.CLOSE:
                page.window.visible = False
                page.update()

        page.window.on_event = on_window_event

        log_view  = LogView()
        dash_view = DashboardView(
            scheduler=scheduler,
            on_run=lambda result: log_view._load_logs(),
        )

        def on_scheduled(result: JobResult) -> None:
            dash_view.update_result(result)
            log_view._load_logs()
            try:
                page.update()
            except Exception:
                pass

        scheduler.set_on_complete(on_scheduled)
        settings_view = SettingsView(scheduler=scheduler)

        # FilePicker — Service로 자동 등록 (page.overlay 불필요)
        log_picker      = ft.FilePicker()
        output_picker   = ft.FilePicker()
        log_file_picker = ft.FilePicker()
        settings_view.set_pickers(log_picker, output_picker)
        log_view.set_file_picker(log_file_picker)

        main_tabs = ft.Tabs(
            length=3,
            selected_index=0,
            animation_duration=200,
            content=ft.Column(
                expand=True,
                controls=[
                    ft.TabBar(
                        scrollable=False,
                        tabs=[
                            ft.Tab(label="대시보드", icon=ft.Icons.DASHBOARD),
                            ft.Tab(label="설정",     icon=ft.Icons.SETTINGS),
                            ft.Tab(label="로그",     icon=ft.Icons.ARTICLE),
                        ],
                    ),
                    ft.TabBarView(
                        expand=True,
                        controls=[
                            ft.Container(dash_view.build(),     padding=20, expand=True),
                            ft.Container(settings_view.build(), padding=16, expand=True),
                            ft.Container(log_view.build(),      padding=20, expand=True),
                        ],
                    ),
                ],
            ),
            expand=True,
        )

        header = ft.Container(
            content=ft.Row(
                [
                    ft.Text("🔔", size=20),
                    ft.Text("조달청 입찰공고 알리미", size=17, weight=ft.FontWeight.W_600, color=C_TEXT_MAIN),
                    ft.Text("v1.0", size=11, color=C_TEXT_SUB),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=C_CARD,
            border=ft.Border.only(bottom=ft.BorderSide(1, C_BORDER)),
            padding=ft.Padding.symmetric(horizontal=20, vertical=12),
        )

        page.add(ft.Column([header, main_tabs], spacing=0, expand=True))

    return main
