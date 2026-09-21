"""Unit tests for conversion abort and retry behavior."""

import os
import threading
import pytest

from janeconverter import cli

from janeconverter.cli import process_conversion, process_playlist_conversion
from janeconverter.converter import convert_media

def test_process_conversion_aborts_immediately():
    abort_event = threading.Event()
    abort_event.set()

    with pytest.raises(KeyboardInterrupt) as excinfo:
        process_conversion(
            source="https://example.com/test",
            abort_event=abort_event,
            check_updates=False
        )
    assert "aborted" in str(excinfo.value).lower()

def test_process_playlist_conversion_aborts_immediately():
    abort_event = threading.Event()
    abort_event.set()

    with pytest.raises(KeyboardInterrupt) as excinfo:
        process_playlist_conversion(
            playlist_title="Test Playlist",
            selected_entries=[{"index": 1, "title": "Track 1", "url": "https://example.com/1"}],
            abort_event=abort_event,
            check_updates=False
        )
    assert "aborted" in str(excinfo.value).lower()

def test_playlist_retry_operation_retries_with_bounded_attempts(monkeypatch):
    attempts = []

    def flaky_operation():
        attempts.append(len(attempts) + 1)
        if len(attempts) < 3:
            raise RuntimeError("temporary provider failure")
        return "ok"

    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)
    result = cli._retry_operation(flaky_operation, "Test track", max_retries=2)

    assert result == "ok"
    assert attempts == [1, 2, 3]

def test_convert_media_aborts_immediately(tmp_path):
    abort_event = threading.Event()
    abort_event.set()

    dummy_input = os.path.join(str(tmp_path), "input.wav")
    with open(dummy_input, "w") as f:
        f.write("dummy content")

    with pytest.raises(KeyboardInterrupt) as excinfo:
        convert_media(
            input_path=dummy_input,
            output_dir=str(tmp_path),
            output_filename="output",
            target_format="mp3",
            abort_event=abort_event
        )
    assert "aborted" in str(excinfo.value).lower()
