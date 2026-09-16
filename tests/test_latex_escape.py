import pytest

from careerx.renderers.latex_escape import LatexSafe, latex_escape, latex_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("R&D", r"R\&D"),
        ("100%", r"100\%"),
        ("a_b", r"a\_b"),
        ("#1", r"\#1"),
        ("$5", r"\$5"),
        ("{x}", r"\{x\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ],
)
def test_special_characters_are_escaped(raw: str, expected: str) -> None:
    assert latex_escape(raw) == expected


def test_backslash_is_escaped_before_other_characters() -> None:
    # A naive sequential replace would turn \& into \textbackslash{}\& and then
    # re-escape the inserted backslash.
    assert latex_escape(r"\&") == r"\textbackslash{}\&"


def test_injection_attempt_is_neutralised() -> None:
    escaped = latex_escape(r"\input{/etc/passwd}")

    assert r"\input" not in escaped
    assert escaped == r"\textbackslash{}input\{/etc/passwd\}"


def test_latex_safe_passes_through_untouched() -> None:
    assert latex_escape(LatexSafe(r"\faGithub")) == r"\faGithub"


def test_url_keeps_structure_but_escapes_percent_and_hash() -> None:
    assert latex_url("https://example.com/a_b?q=1") == "https://example.com/a_b?q=1"
    assert latex_url("https://example.com/100%") == r"https://example.com/100\%"


def test_url_strips_whitespace_used_to_break_out_of_the_argument() -> None:
    assert latex_url("https://example.com} \\evil{") == r"https://example.com}\\evil{"


def test_non_string_values_are_coerced() -> None:
    assert latex_escape(42) == "42"
