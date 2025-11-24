import sys
from unittest.mock import MagicMock, patch

import pytest

from curateur.ui.keyboard_listener import KeyboardListener


@pytest.mark.unit
def test_keyboard_listener_start_no_tty():
    listener = KeyboardListener()
    with patch.object(sys.stdin, "isatty", return_value=False):
        assert listener.start() is False


@pytest.mark.unit
def test_handle_key_updates_flags_and_spotlight():
    ui = MagicMock()
    ui.prompt_active = False  # avoid prompt branch
    listener = KeyboardListener(console_ui=ui)

    # toggle pause
    listener._handle_key("p")
    assert listener.is_paused is True

    # spotlight next/prev via n/b
    listener._handle_key("n")
    listener._handle_key("b")
    ui.spotlight_next.assert_called_once()
    ui.spotlight_prev.assert_called_once()


@pytest.mark.unit
def test_skip_and_quit_requests_flagged_once():
    listener = KeyboardListener()

    listener._handle_key("s")
    assert listener.skip_requested is True
    # second press while pending should not flip pending again
    listener._handle_key("s")
    assert listener.skip_requested is True

    listener._handle_key("q")
    assert listener.quit_requested is True
