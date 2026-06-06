"""Tests for safe_render error boundary decorator."""

from __future__ import annotations

from shopstack.ui.screens._utils import safe_render


def test_safe_render_passes_through_on_success():
    @safe_render
    def ok_html():
        return "<div>OK</div>"

    assert ok_html() == "<div>OK</div>"


def test_safe_render_catches_exception():
    @safe_render
    def bad_html():
        raise RuntimeError("DB connection failed")

    result = bad_html()
    assert "Something went wrong" in result
    assert "DB connection failed" in result


def test_safe_render_catches_exception_with_args():
    @safe_render
    def bad_html(name: str):
        raise ValueError(f"Bad input: {name}")

    result = bad_html("test")
    assert "Something went wrong" in result
    assert "Bad input: test" in result


def test_safe_render_preserves_function_name():
    @safe_render
    def my_render_fn():
        return "<div>OK</div>"

    assert my_render_fn.__name__ == "my_render_fn"
