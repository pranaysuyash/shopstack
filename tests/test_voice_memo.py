"""Tests for shopstack.services.voice_memo (Phase 7 #23)."""
from __future__ import annotations

import json
import tempfile
import wave
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from shopstack.services.voice_memo import (
    CapturedUtterance,
    ParsedCommand,
    VoiceMemoSession,
    capture_chunk,
    end_session,
    make_recording_dispatcher,
    render_session_summary_html,
    start_session,
)


# ── Mocks ──────────────────────────────────────────────────────


class FakeSTT:
    """Records transcribe() calls and returns canned text."""

    def __init__(self, responses: list[str] | None = None):
        self.responses = list(responses or [])
        self.calls: list[tuple[str, str]] = []

    def transcribe(self, audio_path: str, language: str = "en") -> dict:
        self.calls.append((audio_path, language))
        text = self.responses.pop(0) if self.responses else ""
        return {"text": text, "language": language}


def _write_wav(path: str, duration_s: float = 0.1) -> None:
    """Create a tiny WAV file (1 sample, 8kHz)."""
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(8000)
        wf.writeframes(b"\x00\x00")


# ── start_session ──────────────────────────────────────────────


def test_start_session_returns_empty_session():
    s = start_session()
    assert isinstance(s, VoiceMemoSession)
    assert s.utterances == []
    assert s.commands == []
    assert s.started_at > 0


def test_start_session_with_custom_stop_phrase():
    s = start_session(stop_phrase="the end")
    assert s.stop_phrase == "the end"


def test_start_session_lowercases_stop_phrase():
    s = start_session(stop_phrase="STOP")
    assert s.stop_phrase == "stop"


# ─- capture_chunk ──────────────────────────────────────────


def test_capture_chunk_empty_audio_path():
    s = start_session()
    stt = FakeSTT(["hello"])
    utt = capture_chunk(s, "", stt)
    assert utt.text == ""
    # STT was NOT called
    assert stt.calls == []


def test_capture_chunk_nonexistent_audio_path(tmp_path):
    s = start_session()
    stt = FakeSTT(["hello"])
    utt = capture_chunk(s, str(tmp_path / "nope.wav"), stt)
    assert utt.text == ""
    assert stt.calls == []


def test_capture_chunk_transcribes_audio(tmp_path):
    s = start_session()
    audio = str(tmp_path / "test.wav")
    _write_wav(audio)
    stt = FakeSTT(["add tomato"])
    utt = capture_chunk(s, audio, stt)
    assert utt.text == "add tomato"
    assert len(s.utterances) == 1
    assert stt.calls == [(audio, "en")]


def test_capture_chunk_honors_stop_phrase(tmp_path):
    s = start_session(stop_phrase="stop")
    audio = str(tmp_path / "test.wav")
    _write_wav(audio)
    stt = FakeSTT(["stop"])
    capture_chunk(s, audio, stt)
    # No command should be added (stop phrase)
    assert s.commands == []


def test_capture_chunk_no_text_no_command(tmp_path):
    s = start_session()
    audio = str(tmp_path / "test.wav")
    _write_wav(audio)
    stt = FakeSTT([""])
    capture_chunk(s, audio, stt)
    assert s.commands == []


def test_capture_chunk_parses_and_dispatches(tmp_path):
    s = start_session()
    audio = str(tmp_path / "test.wav")
    _write_wav(audio)
    stt = FakeSTT(["add tomato"])
    dispatched = []
    dispatcher = make_recording_dispatcher(dispatched)
    capture_chunk(s, audio, stt, dispatcher=dispatcher)
    # Default parser is fine-tuned classifier
    assert len(s.commands) == 1
    assert s.commands[0].intent == "add_inventory_item"
    assert s.commands[0].dispatch_status == "dispatched"
    assert len(dispatched) == 1


def test_capture_chunk_dispatcher_failure_marked(tmp_path):
    s = start_session()
    audio = str(tmp_path / "test.wav")
    _write_wav(audio)
    stt = FakeSTT(["add tomato"])

    def failing_dispatcher(parsed):
        return {"ok": False, "message": "No can do."}

    capture_chunk(s, audio, stt, dispatcher=failing_dispatcher)
    assert s.commands[0].dispatch_status == "failed"
    assert "No can do" in s.commands[0].dispatch_message


def test_capture_chunk_dispatcher_raises_marked(tmp_path):
    s = start_session()
    audio = str(tmp_path / "test.wav")
    _write_wav(audio)
    stt = FakeSTT(["add tomato"])

    def raising_dispatcher(parsed):
        raise RuntimeError("kaboom")

    capture_chunk(s, audio, stt, dispatcher=raising_dispatcher)
    assert s.commands[0].dispatch_status == "failed"
    assert "kaboom" in s.commands[0].dispatch_message


def test_capture_chunk_no_dispatcher_pending(tmp_path):
    s = start_session()
    audio = str(tmp_path / "test.wav")
    _write_wav(audio)
    stt = FakeSTT(["add tomato"])
    capture_chunk(s, audio, stt)  # no dispatcher
    assert s.commands[0].dispatch_status == "pending"


def test_capture_chunk_general_query_skips_dispatch(tmp_path):
    s = start_session()
    audio = str(tmp_path / "test.wav")
    _write_wav(audio)
    stt = FakeSTT(["hello there"])
    dispatched = []
    capture_chunk(s, audio, stt, dispatcher=make_recording_dispatcher(dispatched))
    # No command is added for general_query
    assert s.commands == []
    assert dispatched == []


def test_capture_chunk_multiple_in_sequence(tmp_path):
    s = start_session()
    stt = FakeSTT(["add milk", "add bread", "consume eggs"])
    for i in range(3):
        audio = str(tmp_path / f"test_{i}.wav")
        _write_wav(audio)
        capture_chunk(s, audio, stt)
    assert len(s.utterances) == 3
    assert len(s.commands) == 3
    intents = [c.intent for c in s.commands]
    assert "add_inventory_item" in intents
    assert "consume_item" in intents


# ── end_session ──────────────────────────────────────────────


def test_end_session_returns_summary():
    s = start_session()
    summary = end_session(s)
    assert summary["duration_s"] >= 0
    assert summary["utterance_count"] == 0
    assert summary["command_count"] == 0
    assert summary["commands"] == []


def test_end_session_includes_commands():
    s = start_session()
    stt = FakeSTT(["add milk"])
    audio = "/tmp/test.wav"
    # We don't need a real file for end_session test
    s.utterances.append(CapturedUtterance(text="add milk", audio_path=audio))
    s.commands.append(ParsedCommand(
        utterance=s.utterances[0], intent="add_inventory_item",
        args={"canonical_name": "milk"}, confidence=0.8,
        dispatch_status="dispatched", dispatch_message="ok",
    ))
    summary = end_session(s)
    assert summary["command_count"] == 1
    assert summary["success_count"] == 1
    assert summary["failure_count"] == 0
    assert summary["commands"][0]["intent"] == "add_inventory_item"


def test_end_session_counts_success_failure():
    s = start_session()
    s.commands.append(ParsedCommand(
        utterance=CapturedUtterance(text="a"), intent="x",
        dispatch_status="dispatched",
    ))
    s.commands.append(ParsedCommand(
        utterance=CapturedUtterance(text="b"), intent="y",
        dispatch_status="failed",
    ))
    summary = end_session(s)
    assert summary["success_count"] == 1
    assert summary["failure_count"] == 1


def test_voice_memo_session_duration_property():
    s = VoiceMemoSession(started_at=10.0, ended_at=12.5)
    assert s.duration_s == 2.5


def test_voice_memo_session_command_count_skips_general_query():
    s = VoiceMemoSession(
        commands=[
            ParsedCommand(utterance=CapturedUtterance(text="a"), intent="add"),
            ParsedCommand(utterance=CapturedUtterance(text="b"), intent="general_query"),
        ]
    )
    assert s.command_count == 1


# ── make_recording_dispatcher ──────────────────────────────────


def test_make_recording_dispatcher_records():
    log = []
    d = make_recording_dispatcher(log)
    out = d({"intent": "add_inventory_item", "args": {"x": 1}})
    assert out["ok"] is True
    assert log == [{"intent": "add_inventory_item", "args": {"x": 1}}]


def test_make_recording_dispatcher_appends():
    log = []
    d = make_recording_dispatcher(log)
    d({"intent": "a"})
    d({"intent": "b"})
    assert log == [{"intent": "a"}, {"intent": "b"}]


# ── HTML rendering ──────────────────────────────────────────


def test_render_session_summary_html_empty():
    html = render_session_summary_html({"utterance_count": 0})
    assert "No voice memo" in html or "vm-empty" in html


def test_render_session_summary_html_with_commands():
    summary = {
        "duration_s": 5.0,
        "utterance_count": 3,
        "command_count": 2,
        "success_count": 2,
        "failure_count": 0,
        "commands": [
            {"text": "add milk", "intent": "add_inventory_item",
             "args": {"canonical_name": "milk"}, "confidence": 0.8,
             "status": "dispatched", "message": "ok"},
            {"text": "consume bread", "intent": "consume_item",
             "args": {}, "confidence": 0.7,
             "status": "failed", "message": "no can do"},
        ],
        "notes": [],
    }
    html = render_session_summary_html(summary)
    assert "vm-block" in html
    assert "add milk" in html
    assert "consume bread" in html
    assert "dispatched" in html
    assert "failed" in html


def test_render_session_summary_html_escapes_xss():
    summary = {
        "duration_s": 1.0, "utterance_count": 1, "command_count": 1,
        "success_count": 0, "failure_count": 1,
        "commands": [
            {"text": "<script>alert(1)</script>", "intent": "x",
             "args": {}, "confidence": 0.5, "status": "failed", "message": ""},
        ],
        "notes": [],
    }
    html = render_session_summary_html(summary)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_render_session_summary_html_color_coding():
    summary = {
        "duration_s": 1.0, "utterance_count": 3, "command_count": 3,
        "success_count": 1, "failure_count": 1,
        "commands": [
            {"text": "a", "intent": "x", "args": {}, "confidence": 0.5,
             "status": "dispatched", "message": ""},
            {"text": "b", "intent": "x", "args": {}, "confidence": 0.5,
             "status": "failed", "message": ""},
            {"text": "c", "intent": "x", "args": {}, "confidence": 0.5,
             "status": "pending", "message": ""},
        ],
        "notes": [],
    }
    html = render_session_summary_html(summary)
    # 3 different colors for 3 statuses
    assert "176B49" in html  # green for dispatched
    assert "A63F31" in html  # red for failed
    assert "A76012" in html  # amber for pending
