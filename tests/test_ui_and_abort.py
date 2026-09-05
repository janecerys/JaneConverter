"""
Unit tests for UI structure, abort functionality, and Console rebranding
"""

import os
import sys
import threading
import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from run_converter import process_conversion, process_playlist_conversion
from engine.converter import convert_media
import gui

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

def test_gui_elements_and_wording():
    with open(os.path.join(os.path.dirname(__file__), "..", "gui.py"), "r", encoding="utf-8") as f:
        content = f.read()

    # Verify play_btn and front clear_logs_btn were removed
    assert "self.play_btn" not in content
    assert "Play Result" not in content
    assert "self.clear_logs_btn" not in content

    # Verify abort button exists
    assert "self.abort_btn" in content
    assert "🛑 Abort" in content

    # Verify diagnostic console was renamed to Console
    assert "💻 Console" in content
    assert "Diagnostic Log" not in content
    assert "Diagnostic Output Stream" not in content
    assert "Diagnostic Console" not in content

    # Verify abort methods exist on JaneConverterApp
    assert hasattr(gui.JaneConverterApp, "_abort_conversion")
    assert hasattr(gui.JaneConverterApp, "_on_conversion_aborted")
    assert hasattr(gui.JaneConverterApp, "_clear_logs")

    # Verify Check for Updates button and methods exist
    assert "self.update_btn" in content
    assert "🔄 Check for Updates" in content
    assert hasattr(gui.JaneConverterApp, "_on_check_updates_clicked")
    assert hasattr(gui.JaneConverterApp, "_on_update_completed")
