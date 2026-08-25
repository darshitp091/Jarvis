"""What ``.env`` does and does not do to the process environment.

The reason this file is worth its length: every provider key from now on is
resolved "settings.yaml, else environment", so a bug here is a bug in how
JARVIS finds *every* secret. The two properties that carry real weight are that
a real exported variable outranks the file (otherwise a checked-out ``.env``
silently overrides the shell) and that a missing or broken file is a no-op
(otherwise a fresh clone cannot boot).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from jarvis.core.env_loader import load_dotenv  # noqa: E402


_TOUCHED = ("BYNARA_API_KEY", "SPARE_KEY", "QUOTED", "EXPORTED", "EMPTY_VALUE")


@pytest.fixture
def env(monkeypatch):
    """A clean slate for the variables these tests set, before and after.

    The cleanup on the way out is not decoration. `load_dotenv` is the thing
    under test, and it writes to `os.environ` itself -- monkeypatch never sees
    those writes, and `delenv(raising=False)` on a name that was absent records
    nothing to undo, so a key this file invents would otherwise outlive it and
    be read as an ambient key by every test file that runs afterwards.
    """
    for name in _TOUCHED:
        monkeypatch.delenv(name, raising=False)
    yield monkeypatch
    for name in _TOUCHED:
        os.environ.pop(name, None)


@pytest.fixture
def dotenv(tmp_path):
    """Write a .env and hand back its path."""
    def write(text):
        path = tmp_path / ".env"
        path.write_text(text, encoding="utf-8")
        return str(path)
    return write


# --- the basic contract -----------------------------------------------------

def test_a_variable_in_the_file_reaches_the_environment(env, dotenv):
    assert load_dotenv(dotenv("BYNARA_API_KEY=sk-abc123\n")) == 1
    assert os.environ["BYNARA_API_KEY"] == "sk-abc123"


def test_the_count_returned_is_the_number_actually_set(env, dotenv):
    assert load_dotenv(dotenv("BYNARA_API_KEY=one\nSPARE_KEY=two\n")) == 2


def test_a_value_containing_equals_signs_keeps_them(env, dotenv):
    load_dotenv(dotenv("BYNARA_API_KEY=sk-a=b=c\n"))
    assert os.environ["BYNARA_API_KEY"] == "sk-a=b=c"


def test_surrounding_whitespace_is_stripped_from_both_halves(env, dotenv):
    load_dotenv(dotenv("  BYNARA_API_KEY  =  sk-spaced  \n"))
    assert os.environ["BYNARA_API_KEY"] == "sk-spaced"


@pytest.mark.parametrize("quote", ['"', "'"])
def test_a_quoted_value_loses_its_quotes(env, dotenv, quote):
    load_dotenv(dotenv("QUOTED=%ssk-quoted%s\n" % (quote, quote)))
    assert os.environ["QUOTED"] == "sk-quoted"


def test_a_mismatched_quote_is_left_alone(env, dotenv):
    load_dotenv(dotenv("QUOTED=\"sk-half\n"))
    assert os.environ["QUOTED"] == '"sk-half'


def test_an_export_prefix_is_accepted(env, dotenv):
    load_dotenv(dotenv("export EXPORTED=sk-exported\n"))
    assert os.environ["EXPORTED"] == "sk-exported"


def test_an_empty_value_is_still_a_definition(env, dotenv):
    assert load_dotenv(dotenv("EMPTY_VALUE=\n")) == 1
    assert os.environ["EMPTY_VALUE"] == ""


# --- precedence: the real environment wins ----------------------------------

def test_an_already_exported_variable_is_not_overwritten(env, dotenv):
    env.setenv("BYNARA_API_KEY", "sk-from-the-shell")
    assert load_dotenv(dotenv("BYNARA_API_KEY=sk-from-the-file\n")) == 0
    assert os.environ["BYNARA_API_KEY"] == "sk-from-the-shell"


def test_an_exported_empty_string_still_wins(env, dotenv):
    """Empty is a decision, not an absence -- `KEY= jarvis` disables a provider."""
    env.setenv("BYNARA_API_KEY", "")
    load_dotenv(dotenv("BYNARA_API_KEY=sk-from-the-file\n"))
    assert os.environ["BYNARA_API_KEY"] == ""


def test_the_first_definition_in_the_file_wins_over_a_later_one(env, dotenv):
    load_dotenv(dotenv("BYNARA_API_KEY=first\nBYNARA_API_KEY=second\n"))
    assert os.environ["BYNARA_API_KEY"] == "first"


# --- absence and damage are never fatal -------------------------------------

def test_a_missing_file_is_a_silent_no_op(env, tmp_path):
    assert load_dotenv(str(tmp_path / "nothing-here")) == 0


def test_the_default_path_is_dot_env():
    """The signature's default is what main.py relies on; pin it."""
    import inspect
    from jarvis.core import env_loader
    assert inspect.signature(env_loader.load_dotenv).parameters["path"].default == ".env"


def test_a_directory_where_the_file_should_be_does_not_raise(env, tmp_path):
    assert load_dotenv(str(tmp_path)) == 0


def test_comments_and_blank_lines_are_skipped(env, dotenv):
    assert load_dotenv(dotenv("# a comment\n\n   \nBYNARA_API_KEY=sk-real\n# trailing\n")) == 1
    assert os.environ["BYNARA_API_KEY"] == "sk-real"


def test_a_line_with_no_equals_sign_is_ignored_not_fatal(env, dotenv):
    assert load_dotenv(dotenv("THIS IS NOT AN ASSIGNMENT\nBYNARA_API_KEY=sk-survived\n")) == 1
    assert os.environ["BYNARA_API_KEY"] == "sk-survived"


def test_a_nameless_assignment_is_ignored(env, dotenv):
    assert load_dotenv(dotenv("=orphaned\n")) == 0


def test_a_hash_inside_a_value_is_kept(env, dotenv):
    """Only a leading # is a comment. Keys legitimately contain '#'."""
    load_dotenv(dotenv("BYNARA_API_KEY=sk-with#hash\n"))
    assert os.environ["BYNARA_API_KEY"] == "sk-with#hash"
