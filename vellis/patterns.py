"""Whole-string RE2 property patterns.

Realizes ``RTG::'String Pattern'`` and ``VellisRequirements::stringPatternValidation``.

The model selects Google RE2 syntax with Unicode semantics and whole-string
``FullMatch`` behavior, and says explicitly that this selection does not select a
runtime engine. This realization selects RE2 itself.

That choice is worth naming, because the obvious alternative is wrong in a way that is
hard to see. The standard library engine is close to RE2 but not identical: it reads
``\\d``, ``\\w``, ``\\s``, and ``\\b`` as Unicode-wide where RE2 defines them over ASCII,
it lets ``$`` match before a trailing newline, it reads ``{,n}`` as a repetition where
RE2 reads literal text, and it has no ``\\p{...}`` at all. An expression validated
against that engine would quietly mean something different from the expression the model
says the owner stored, and the owner would lose script classes, word boundaries, negated
POSIX classes, and scoped inline flags outright. Using RE2 removes that whole class of
divergence, and it rejects lookaround, backreferences, and malformed expressions on its
own terms rather than on ours.

The engine encodes to UTF-8, so none of its failure modes reaches a caller as itself.
Compiling converts them into :class:`PatternError`; matching answers a yes-or-no
question, so text the engine cannot encode simply matches nothing. Either way a caller
assessing a graph gets a finding or an answer, never an exception from a library it did
not call.

Error logging is turned off because an invalid expression is an ordinary validation
finding the owner should see once, in a report, rather than a line on standard error.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

import re2

__all__ = ["CompiledPattern", "PatternError", "compile_pattern"]


def _quiet_options() -> Any:
    options = re2.Options()
    options.log_errors = False
    return options


_OPTIONS: Final[Any] = _quiet_options()


class PatternError(ValueError):
    """Raised when RE2 rejects an expression as malformed or unsupported."""


@dataclass(frozen=True, slots=True)
class CompiledPattern:
    """An RE2-accepted expression compiled for whole-string matching."""

    expression: str
    _compiled: Any

    def matches(self, value: str) -> bool:
        """Return whether the whole value matches, per RE2 ``FullMatch``.

        Text the engine cannot encode matches nothing; it is never an exception thrown
        at a caller who asked a yes-or-no question about a stored value.
        """
        if not isinstance(value, str):  # pyright: ignore[reportUnnecessaryIsInstance]
            return False
        try:
            return self._compiled.fullmatch(value) is not None
        except UnicodeEncodeError:
            return False


def compile_pattern(expression: str) -> CompiledPattern:
    """Compile an RE2 expression, raising :class:`PatternError` when RE2 rejects it."""
    if not isinstance(expression, str):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise PatternError("a pattern expression must be text")
    try:
        compiled = re2.compile(expression, _OPTIONS)
    except re2.error as error:
        raise PatternError(f"RE2 rejected the expression: {_reason(error)}") from error
    except UnicodeEncodeError as error:
        raise PatternError(f"the expression is not encodable text: {error}") from error
    return CompiledPattern(expression=expression, _compiled=compiled)


def _reason(error: Exception) -> str:
    """Return RE2's own diagnosis as readable text."""
    detail = error.args[0] if error.args else error
    if isinstance(detail, bytes):
        return detail.decode("utf-8", "replace")
    return str(detail)
