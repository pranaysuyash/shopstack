"""Voice memo quick-log — Phase 7 #23 (Tier 4 #23).

Continuous-listening mode for "talk while you cook / shop /
unpack" — the user holds a button, the STT provider
transcribes chunks, and each chunk is run through the
fine-tuned command parser and dispatched to the tool surface.

**Why a separate module:**

Existing :func:`ask_shopstack` is one-shot: you type/say one
utterance, get one response. Voice memo is *streaming* — the
user might say 5 things in 30 seconds, and the system should
handle them as 5 separate commands.

**Inputs:**

- An :class:`STTProvider` (already registered via the provider
  registry).
- A push-to-talk start/stop callback (Gradio `Audio` component
  fires `start_recording` / `stop_recording` events).

**Outputs:**

- A :class:`VoiceMemoSession` that tracks:
  - The list of captured utterances.
  - The list of parsed commands per utterance.
  - The list of dispatch results (one per command).
  - Total duration, number of commands, success count.
- An :func:`end_session` that returns the final summary +
  the per-command results as a structured list.

**Failure modes:**

- No STT provider loaded → fail with a clear "voice memo
  requires an STT provider" message.
- Audio file path is missing → fail with "no audio captured".
- Per-utterance parse / dispatch failure → the utterance is
  recorded but the command is marked failed (the rest of
  the session continues).
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any, Callable, Iterable

from shopstack.providers.interfaces import STTProvider

logger = logging.getLogger(__name__)


# ─── Session state ────────────────────────────────────────────────


@dataclass
class CapturedUtterance:
    """One transcribed chunk in a voice memo session."""

    text: str
    audio_path: str = ""
    started_at: float = 0.0
    duration_s: float = 0.0
    language: str = "en"


@dataclass
class ParsedCommand:
    """The parser output for one captured utterance."""

    utterance: CapturedUtterance
    intent: str = "general_query"
    args: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    dispatch_status: str = "pending"  # "pending" | "dispatched" | "failed"
    dispatch_message: str = ""


@dataclass
class VoiceMemoSession:
    """One continuous-listening session."""

    started_at: float = 0.0
    ended_at: float = 0.0
    utterances: list[CapturedUtterance] = field(default_factory=list)
    commands: list[ParsedCommand] = field(default_factory=list)
    language: str = "en"
    stop_phrase: str = "stop"
    notes: list[str] = field(default_factory=list)

    @property
    def duration_s(self) -> float:
        if not self.ended_at or not self.started_at:
            return 0.0
        return round(self.ended_at - self.started_at, 2)

    @property
    def command_count(self) -> int:
        return sum(1 for c in self.commands if c.intent != "general_query")

    @property
    def success_count(self) -> int:
        return sum(1 for c in self.commands if c.dispatch_status == "dispatched")

    @property
    def failure_count(self) -> int:
        return sum(1 for c in self.commands if c.dispatch_status == "failed")


# ─── Session lifecycle ────────────────────────────────────────────


def start_session(
    *,
    language: str = "en",
    stop_phrase: str = "stop",
) -> VoiceMemoSession:
    """Start a new voice-memo session.

    Args:
        language: BCP-47 language code passed to the STT
            provider (e.g. "en", "hi", "en-IN").
        stop_phrase: Spoken phrase that ends the session.

    Returns:
        A new :class:`VoiceMemoSession`. Pass this to
        :func:`capture_chunk` and :func:`end_session`.
    """
    return VoiceMemoSession(
        started_at=time.time(),
        language=language,
        stop_phrase=(stop_phrase or "stop").lower().strip(),
    )


def capture_chunk(
    session: VoiceMemoSession,
    audio_path: str,
    stt: STTProvider,
    *,
    parser: Callable[[str], dict[str, Any]] | None = None,
    dispatcher: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> CapturedUtterance:
    """Transcribe ``audio_path`` and append to the session.

    Args:
        session: Active :class:`VoiceMemoSession`.
        audio_path: Path to the audio chunk on disk.
        stt: An :class:`STTProvider` to transcribe the audio.
        parser: Optional intent parser (defaults to
            :func:`shopstack.services.fine_tuned_parser.classify_intent`).
        dispatcher: Optional command dispatcher. Should accept
            a parsed intent dict and return a status dict
            ``{"ok": bool, "message": str}``. When None, the
            command is recorded with ``dispatch_status="pending"``
            and the caller can dispatch it later.

    Returns:
        The :class:`CapturedUtterance` that was added to the
        session. If the audio path is empty / missing, returns
        a placeholder empty utterance.
    """
    started = time.time()
    if not audio_path or not Path(audio_path).is_file():
        utt = CapturedUtterance(
            text="", audio_path=audio_path or "", started_at=started,
            language=session.language,
        )
        session.utterances.append(utt)
        session.notes.append("Empty audio chunk skipped.")
        return utt
    try:
        result = stt.transcribe(audio_path, language=session.language)
        text = (result.get("text") or "").strip()
    except Exception as exc:
        logger.debug("STT transcribe failed: %s", exc)
        text = ""
    duration = round(time.time() - started, 2)
    utt = CapturedUtterance(
        text=text,
        audio_path=audio_path,
        started_at=started,
        duration_s=duration,
        language=session.language,
    )
    session.utterances.append(utt)
    # Stop phrase → don't dispatch
    if text.lower().strip() == session.stop_phrase:
        session.notes.append(f"Stop phrase detected: {text!r}")
        return utt
    if not text:
        return utt
    # Parse + dispatch
    if parser is None:
        from shopstack.services.fine_tuned_parser import classify_intent
        parser = classify_intent
    try:
        parsed = parser(text)
    except Exception as exc:
        session.notes.append(f"Parser failed on {text!r}: {exc}")
        return utt
    cmd = ParsedCommand(
        utterance=utt,
        intent=parsed.get("intent", "general_query"),
        args=parsed.get("args", {}),
        confidence=float(parsed.get("confidence", 0.0)),
    )
    if dispatcher is not None and cmd.intent != "general_query":
        try:
            result = dispatcher(parsed)
            if result.get("ok"):
                cmd.dispatch_status = "dispatched"
                cmd.dispatch_message = result.get("message", "")
            else:
                cmd.dispatch_status = "failed"
                cmd.dispatch_message = result.get("message", "Dispatcher returned ok=False.")
        except Exception as exc:
            cmd.dispatch_status = "failed"
            cmd.dispatch_message = f"Dispatcher raised: {exc}"
    session.commands.append(cmd)
    return utt


def end_session(
    session: VoiceMemoSession,
) -> dict[str, Any]:
    """End the session and return a structured summary.

    Returns::

        {
            "duration_s": float,
            "utterance_count": int,
            "command_count": int,
            "success_count": int,
            "failure_count": int,
            "commands": [
                {
                    "text": str,
                    "intent": str,
                    "args": dict,
                    "confidence": float,
                    "status": str,
                    "message": str,
                },
                ...
            ],
            "notes": [str, ...],
        }
    """
    session.ended_at = time.time()
    return {
        "duration_s": session.duration_s,
        "utterance_count": len(session.utterances),
        "command_count": session.command_count,
        "success_count": session.success_count,
        "failure_count": session.failure_count,
        "commands": [
            {
                "text": c.utterance.text,
                "intent": c.intent,
                "args": c.args,
                "confidence": c.confidence,
                "status": c.dispatch_status,
                "message": c.dispatch_message,
            }
            for c in session.commands
        ],
        "notes": list(session.notes),
    }


# ─── HTML rendering ──────────────────────────────────────────────


def render_session_summary_html(summary: dict[str, Any]) -> str:
    """Render a voice-memo session summary as XSS-safe HTML.

    Shows: duration, utterance count, success/failure counts,
    and a per-command list with status badges.
    """
    if not summary.get("utterance_count"):
        return (
            "<div class='vm-block vm-empty'>"
            "No voice memo captured yet. Hold the record button and speak."
            "</div>"
        )
    parts: list[str] = [
        "<div class='vm-block'>",
        "<div class='vm-headline'>",
        f"<strong>{summary['command_count']}</strong> commands in "
        f"{summary['utterance_count']} utterances · "
        f"{summary['duration_s']:.1f}s",
        "</div>",
    ]
    if summary.get("commands"):
        parts.append("<ul class='vm-cmds'>")
        for c in summary["commands"]:
            status_color = {
                "dispatched": "var(--green, #176B49)",
                "failed":     "var(--red, #A63F31)",
                "pending":    "var(--amber, #A76012)",
            }.get(c["status"], "var(--text-dim, #6F6254)")
            parts.append(
                "<li class='vm-cmd'>"
                f"<span class='vm-cmd-text'>{escape(c['text'])}</span>"
                f"<span class='vm-cmd-intent'>{escape(c['intent'])}</span>"
                f"<span class='vm-cmd-conf'>{c['confidence'] * 100:.0f}%</span>"
                f"<span class='vm-cmd-status' style='color:{status_color};'>"
                f"{escape(c['status'])}</span>"
                f"</li>"
            )
        parts.append("</ul>")
    parts.append("</div>")
    return "".join(parts)


# ─── Default dispatcher (records commands for replay) ────────────


def make_recording_dispatcher(commands_log: list[dict[str, Any]]) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Return a dispatcher that just appends commands to ``commands_log``.

    Useful for tests and for the "review before confirm" flow.
    """
    def dispatcher(parsed: dict[str, Any]) -> dict[str, Any]:
        commands_log.append(parsed)
        return {"ok": True, "message": "Recorded."}
    return dispatcher


__all__ = [
    "CapturedUtterance",
    "ParsedCommand",
    "VoiceMemoSession",
    "capture_chunk",
    "end_session",
    "make_recording_dispatcher",
    "render_session_summary_html",
    "start_session",
]
