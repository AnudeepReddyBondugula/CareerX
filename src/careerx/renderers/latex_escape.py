"""LaTeX escaping for user-supplied values.

Resume data is arbitrary user input. Interpolated raw, a ``&`` or ``%`` breaks
compilation, and a string like ``\\input{/etc/passwd}`` is a file-read
primitive. Every value rendered into a template is therefore escaped by
default, and anything that must pass through unescaped has to say so
explicitly by being marked :class:`LatexSafe`.
"""

from __future__ import annotations

_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

# Characters that must stay escaped inside \href / \url arguments. hyperref
# reads the rest of a URL verbatim, so over-escaping would corrupt the link.
_URL_ESCAPES = {
    "%": r"\%",
    "#": r"\#",
    "\\": r"\\",
}


class LatexSafe(str):
    """A string that is already valid LaTeX and must not be escaped again."""

    __slots__ = ()


def latex_escape(value: object) -> str:
    """Escape ``value`` for inclusion in a LaTeX document body."""
    if isinstance(value, LatexSafe):
        return str(value)

    text = str(value)
    return "".join(_ESCAPES.get(character, character) for character in text)


def latex_url(value: object) -> LatexSafe:
    """Escape ``value`` for use as a \\href target."""
    if isinstance(value, LatexSafe):
        return value

    text = str(value).strip()
    # Strip control characters and whitespace, which cannot appear in a URL and
    # are the usual vehicle for breaking out of the argument.
    text = "".join(character for character in text if character.isprintable() and not character.isspace())

    return LatexSafe("".join(_URL_ESCAPES.get(character, character) for character in text))
