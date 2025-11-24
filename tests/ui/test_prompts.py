import builtins
from unittest.mock import patch

import pytest

from curateur.ui import prompts


@pytest.mark.unit
def test_confirm_respects_default_and_input():
    with patch.object(builtins, "input", side_effect=["", "n"]):
        # default True when empty
        assert prompts.confirm("Proceed?", default=True) is True
        # explicit no
        assert prompts.confirm("Proceed?", default=False) is False


@pytest.mark.unit
def test_choose_validates_choices_and_default():
    with patch.object(builtins, "input", side_effect=["", "2"]):
        choice = prompts.PromptSystem().choose("Pick", ["a", "b"], default=0)
        assert choice == "a"

    with patch.object(builtins, "input", side_effect=["3", "1"]):
        choice = prompts.PromptSystem().choose("Pick", ["a", "b"], default=None)
        assert choice == "a"


@pytest.mark.unit
def test_input_text_uses_default_and_validator():
    with patch.object(builtins, "input", side_effect=["", "bad", "good"]):
        ps = prompts.PromptSystem()
        val = ps.input_text("Enter", default="default", validator=lambda x: x.startswith("g"))
        assert val == "good"


@pytest.mark.unit
def test_input_int_enforces_range_and_default():
    with patch.object(builtins, "input", side_effect=["", "0", "5"]):
        ps = prompts.PromptSystem()
        val = ps.input_int("Number", default=3, min_value=1, max_value=5)
        assert val == 3

        val2 = ps.input_int("Number", default=None, min_value=1, max_value=5)
        assert val2 == 5
