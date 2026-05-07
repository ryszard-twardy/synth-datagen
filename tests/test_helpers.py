"""Unit tests for ``tests/helpers.py``.

Mostly covers the ANSI-strip helper used to make CliRunner-based help-text
assertions environment-agnostic (CI emits ANSI; local Windows does not).
"""

from __future__ import annotations

from tests.helpers import strip_ansi


def test_strip_ansi_no_op_on_plain_text() -> None:
    assert strip_ansi("--profile-config") == "--profile-config"
    assert strip_ansi("") == ""


def test_strip_ansi_removes_simple_color_sequence() -> None:
    coloured = "\x1b[1;36m--profile-config\x1b[0m"
    assert strip_ansi(coloured) == "--profile-config"


def test_strip_ansi_removes_split_color_sequences() -> None:
    """The exact CI failure shape: each character group wrapped separately."""
    coloured = "\x1b[1;36m-\x1b[0m\x1b[1;36m-profile\x1b[0m\x1b[1;36m-config\x1b[0m"
    assert strip_ansi(coloured) == "--profile-config"


def test_strip_ansi_handles_resets_and_attrs() -> None:
    coloured = "\x1b[0m\x1b[31mERROR\x1b[39m: bad\x1b[m"
    assert strip_ansi(coloured) == "ERROR: bad"


def test_strip_ansi_preserves_non_sgr_text() -> None:
    """Helper is intentionally narrow — only SGR (``CSI ... m``) sequences."""
    # A bell and a literal escape that isn't an SGR sequence pass through.
    assert strip_ansi("hello\x07world") == "hello\x07world"
