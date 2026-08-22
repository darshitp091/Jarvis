"""Tests for jarvis.core.text_normalize -- the pure text functions lifted out of
main.py's JARVIS class.

Two jobs here.

Most of the file is characterization. Every expected value was measured by
running the function, not worked out by reading it, so these tests describe what
JARVIS does today rather than what someone meant it to do. Several pin behaviour
that is arguably wrong; each of those says so, and says why it was pinned rather
than fixed. Changing one is then a decision that has to edit a test explaining
itself, which is the point.

The last test is structural. It checks that main.py's eight same-named methods
are still one-line delegations to this module. The move itself was checked by
`tools/ast_equivalence.py` against the pre-extraction commit; that runs at
extraction time, because CI checks out one commit deep and cannot see the
"before" side. What CI *can* check forever is that a second copy of this logic
does not quietly grow back inside main.py.

Until this module existed none of these functions could be tested at all: they
sat in main.py, which imports PyQt6, ollama and pyautogui at module level, so
importing it in the environment CI runs is impossible.
"""

import ast
import os

import pytest

from jarvis.core import text_normalize as tn

# -- detect_language -----------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("open chrome", "english"),
        ("hello there my friend", "english"),
        ("play the next song", "english"),
        ("", "english"),
        ("chrome kholo", "hinglish"),
        ("screenshot le lo", "english"),
        ("क्या हाल है", "hinglish"),
    ],
)
def test_detect_language(text, expected):
    assert tn.detect_language(text) == expected


@pytest.mark.parametrize("text", ["so what is this", "give me a banana"])
def test_a_single_english_word_in_the_keyword_set_flips_the_language(text):
    """Pinned, not fixed: the keyword set holds "so", "me" and "banana".

    One match out of any number of words is enough, so plain English sentences
    containing those come back as Hinglish. The consequence is a Hinglish reply
    to an English question -- wrong, but visible only as tone, which is why it
    survived. Fixing it means choosing a new threshold and re-tuning the set
    against real utterances; that is a behaviour change on the primary
    interface and wants its own commit, not a rider on an extraction.
    """
    assert tn.detect_language(text) == "hinglish"


# -- transliterate_devanagari_to_roman -----------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        # "क्रोम खोलो" -- word-map hit, then character-level.
        ("क्रोम खोलो", "chrome kholo"),
        ("गाना बजाओ", "gaana bajao"),
        ("मुझे एक काम करो", "mujhe ek kaam karo"),
        ("स्पॉटीफाई पे गाना", "spotify pe gaana"),
        ("नमस्ते", "namaste"),
        # Roman input is returned untouched -- the function is a no-op on it.
        ("open chrome", "open chrome"),
    ],
)
def test_transliterate_devanagari_to_roman(text, expected):
    assert tn.transliterate_devanagari_to_roman(text) == expected


def test_trailing_punctuation_is_dropped_from_a_devanagari_word():
    """Pinned, not fixed: "है?" loses its question mark.

    The function preserves punctuation only when `w.endswith(clean_w)`, which is
    false exactly when there is trailing punctuation -- so the branch meant to
    keep it can never fire. Downstream is the intent router, which does not read
    question marks, so nothing observable breaks today. It is a latent trap for
    whatever reads this text next.
    """
    assert tn.transliterate_devanagari_to_roman(
        "क्या हाल है?") == "kya hal hai"


# -- get_phonetic_candidates ---------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("opun chrome", {"open chrome"}),
        ("risakhal vine clean karo", {"recycle bin clean karo"}),
        ("dish clean up karo", {"disk cleanup karo"}),
        ("leptop band karo", {"laptop band karo"}),
        ("spotifai pe buja", {"spotify pe baja"}),
        ("temathareree fayas dilet karo", {"temporary files delete karo"}),
        # Nothing misheard: no candidates, so the caller keeps the original.
        ("open chrome", set()),
        # Whole-word and substring passes disagree, so both survive.
        ("opun play music", {"open play music", "open play some music"}),
    ],
)
def test_get_phonetic_candidates(text, expected):
    """Compared as sets on purpose.

    The function ends in `list(set(candidates))`, and str hashing is salted per
    process, so the order of a two-candidate result is not reproducible. A test
    asserting a list here would pass locally and fail on some CI runs.
    """
    assert set(tn.get_phonetic_candidates(text)) == expected


def test_get_phonetic_candidates_lowercases():
    assert tn.get_phonetic_candidates("OPUN Chrome") == ["open chrome"]


# -- clean_name_address --------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("hey jarvis open chrome", "open chrome"),
        ("jarvis bhai gaana bajao", "gaana bajao"),
        ("arre jarvis ji kya haal hai", "kya haal hai"),
        ("open chrome", "open chrome"),
        ("", ""),
    ],
)
def test_clean_name_address(text, expected):
    assert tn.clean_name_address(text) == expected


@pytest.mark.parametrize("text", ["jarvis", "sun jarvis"])
def test_an_utterance_that_is_only_the_address_is_returned_whole(text):
    """Stripping everything leaves nothing to act on, so the original comes back.

    That is deliberate in the source (`return cleaned if cleaned else text`) and
    it matters: a bare "jarvis" is a summons, and handing the dispatcher "" would
    turn it into an empty command instead.
    """
    assert tn.clean_name_address(text) == text


# -- split_chained_commands ----------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("open chrome and then play music", ["open chrome", "play music"]),
        ("notepad kholo phir gaana bajao", ["notepad kholo", "gaana bajao"]),
        (
            "screenshot lo uske baad whatsapp kholo aur phir bhej do",
            ["screenshot lo", "whatsapp kholo", "bhej do"],
        ),
        # No separator: one command, not a split.
        ("open chrome", ["open chrome"]),
    ],
)
def test_split_chained_commands(text, expected):
    assert tn.split_chained_commands(text) == expected


@pytest.mark.parametrize("text", ["", "then"])
def test_nothing_to_run_yields_no_commands(text):
    """A bare separator, or nothing at all, produces an empty list.

    Worth pinning because the caller iterates the result: an empty list is a
    silent no-op, whereas `[""]` would push an empty string through dispatch.
    """
    assert tn.split_chained_commands(text) == []


# -- parse_volume_reply --------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("50", 50),
        ("mute kar do", 0),
        ("zero", 0),
        ("bahut kam", 10),
        ("thoda kam kar do", 25),
        ("medium", 50),
        ("aadha", 50),
        ("full kar do", 100),
        ("tez kar do", 100),
        # Not understood -- the caller asks again rather than guessing.
        ("pata nahi", None),
        ("", None),
    ],
)
def test_parse_volume_reply(text, expected):
    assert tn.parse_volume_reply(text) == expected


@pytest.mark.parametrize("text,expected", [("volume 200 kar do", 100),
                                           ("volume 1000", 100)])
def test_out_of_range_numbers_are_clamped(text, expected):
    """"1000" matches at most three digits, so it reads as 100 and clamps to 100.

    Both roads lead to the same place here, which is why the digit cap has never
    caused trouble: any number a person says loudly is already over 100.
    """
    assert tn.parse_volume_reply(text) == expected


def test_a_number_wins_over_a_keyword():
    """The digit search runs before every keyword branch.

    So "mute" alongside a number is ignored -- deliberate, since the number is
    the more specific instruction.
    """
    assert tn.parse_volume_reply("mute nahi 30 kar do") == 30


# -- clean_song_name_reply -----------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("shape of you chalao", "shape of you"),
        ("youtube pe kesariya bajao", "kesariya"),
        ("arijit singh ka gaana sunao", "arijit singh"),
        ("believer", "believer"),
    ],
)
def test_clean_song_name_reply(text, expected):
    assert tn.clean_song_name_reply(text) == expected


@pytest.mark.parametrize("text", ["koi bhi chala do", "tum decide karo",
                                  "your choice sir"])
def test_leaving_the_choice_to_jarvis_becomes_a_concrete_query(text):
    """Handing the decision over has to produce something searchable.

    Returning "" or the literal "koi bhi" would send that to YouTube as a query.
    """
    assert tn.clean_song_name_reply(text) == "trending songs this week"


# -- clean_to_plain_text -------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("", ""),
        ("**bold** text", "bold text"),
        ("- item one\n- item two", "item one item two"),
        ("# Heading\n\n1. first\n2. second", "Heading first second"),
        ("line one\nline two\n\nline three", "line one line two line three"),
        # Stage directions an LLM adds for flavour would otherwise be spoken.
        ("(pauses) hello sir", "hello sir"),
        ("See <https://example.com> for more", "See for more"),
    ],
)
def test_clean_to_plain_text(text, expected):
    assert tn.clean_to_plain_text(text) == expected


def test_the_text_stops_at_an_interactive_question():
    """Anything after the question mark is dropped, so JARVIS waits for an answer
    instead of announcing what it is about to do and then doing it."""
    assert tn.clean_to_plain_text(
        "Sure. Shall we begin? I will also reformat the drive."
    ) == "Sure. Shall we begin?"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("[docs](https://example.com)", "[docs]"),
        ("Visit [docs](https://x.io) now", "Visit [docs] now"),
        ("![img](a.png) after the image", "![img] after the image"),
    ],
)
def test_markdown_links_keep_their_brackets(text, expected):
    """Pinned, not fixed -- and this one is a bug with a visible symptom.

    The function documents nine numbered steps. Step 1 strips every `(...)` as a
    stage direction, which eats a markdown link's URL before step 2 (images) and
    step 3 (links) ever look at it. Both of those regexes are therefore dead, and
    a link arrives as `[docs]`: brackets shown on screen, and read aloud as
    "docs" with no hint that it was a link.

    The fix is to move step 1 after step 3, which is a two-line reorder -- but it
    changes what the user sees and hears, and this extraction has to be provably
    behaviour-preserving. So the current output is recorded here first; the fix
    is then a commit that flips these three expectations and says why.
    """
    assert tn.clean_to_plain_text(text) == expected


def test_underscores_are_stripped_from_identifiers():
    """Step 4 removes `_` to kill markdown italics, and takes snake_case with it.

    Harmless for speech, wrong for the same text shown in the UI -- which it is,
    since one function serves both.
    """
    assert tn.clean_to_plain_text("snake_case identifier") == "snakecase identifier"


# -- main.py still only delegates ----------------------------------------

# main.py imports PyQt6, ollama and pyautogui at module level, so it cannot be
# imported here; it is read as source and parsed instead. tests/
# test_command_dispatch.py does the same for its own checks.
MAIN_PY = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "main.py")

# JARVIS method -> the function in this module it must delegate to.
DELEGATIONS = {
    "clean_to_plain_text": "clean_to_plain_text",
    "split_chained_commands": "split_chained_commands",
    "_detect_language": "detect_language",
    "transliterate_devanagari_to_roman": "transliterate_devanagari_to_roman",
    "_get_phonetic_candidates": "get_phonetic_candidates",
    "_clean_name_address": "clean_name_address",
    "_parse_volume_reply": "parse_volume_reply",
    "_clean_song_name_reply": "clean_song_name_reply",
}


def _jarvis_class():
    with open(MAIN_PY, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    return tree, next(n for n in tree.body
                      if isinstance(n, ast.ClassDef) and n.name == "JARVIS")


def test_main_py_imports_this_module_at_top_level():
    tree, _ = _jarvis_class()
    imported = {a.asname or a.name for n in tree.body
                if isinstance(n, ast.ImportFrom) and n.module == "jarvis.core"
                for a in n.names}
    assert "text_normalize" in imported


@pytest.mark.parametrize("method,function", sorted(DELEGATIONS.items()))
def test_jarvis_method_is_only_a_delegation(method, function):
    """The method body must be exactly `return text_normalize.<function>(<args>)`.

    Not a style rule. These eight bodies were 226 lines of main.py; the reason
    they are testable now is that the logic lives somewhere importable. A method
    that grows a second branch, a cache, or a `self.` lookup takes that back
    without anyone noticing, because the call sites do not change.
    """
    _, cls = _jarvis_class()
    fn = next((n for n in cls.body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and n.name == method), None)
    assert fn is not None, "JARVIS.%s is gone" % method
    assert len(fn.body) == 1, ("JARVIS.%s has %d statements, not a delegation"
                               % (method, len(fn.body)))

    stmt = fn.body[0]
    assert isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Call), \
        "JARVIS.%s does not return a call" % method
    call = stmt.value
    assert isinstance(call.func, ast.Attribute), \
        "JARVIS.%s calls %s, not text_normalize.%s" % (
            method, ast.unparse(call.func), function)
    assert isinstance(call.func.value, ast.Name)
    assert (call.func.value.id, call.func.attr) == ("text_normalize", function), \
        "JARVIS.%s delegates to %s" % (method, ast.unparse(call.func))

    # Every parameter after `self` is passed straight through, in order, with
    # nothing added: a delegation that drops or reshapes an argument is not one.
    params = [a.arg for a in fn.args.args[1:]]
    assert [getattr(a, "id", None) for a in call.args] == params
    assert not call.keywords

