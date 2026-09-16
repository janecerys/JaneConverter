"""
Unit tests for UI structure, abort functionality, and Console rebranding
"""

import os
import sys
import threading
import pytest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import run_converter

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

def test_playlist_retry_operation_retries_with_bounded_attempts(monkeypatch):
    attempts = []

    def flaky_operation():
        attempts.append(len(attempts) + 1)
        if len(attempts) < 3:
            raise RuntimeError("temporary provider failure")
        return "ok"

    monkeypatch.setattr(run_converter.time, "sleep", lambda _seconds: None)
    result = run_converter._retry_operation(flaky_operation, "Test track", max_retries=2)

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

    # Verify universal GPU switch and hardware detection
    assert "self.gpu_switch" in content
    assert "Hardware Acceleration" in content
    hw_info = gui.get_system_hardware_info()
    assert "has_gpu" in hw_info
    assert "encoder_name" in hw_info
    assert "short_gpu" in hw_info

def test_unix_launcher_honors_python_preference_and_stages_stale_native_binary():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    with open(os.path.join(root, "run_converter.sh"), encoding="utf-8") as launcher_file:
        launcher = launcher_file.read()
    with open(os.path.join(root, "install.sh"), encoding="utf-8") as installer_file:
        installer = installer_file.read()
    assert "FRONTEND_PREFERENCE" in launcher
    assert 'FRONTEND_PREFERENCE\" != \"python\"' in launcher
    assert "JaneConverterNative.stale" in installer