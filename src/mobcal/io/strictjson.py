"""JSON read strictly, for the files that describe one calculation (the ion file, the method).

Python's ``json`` keeps the last of two equal keys in an object and accepts ``NaN``,
``Infinity`` and ``-Infinity``, none of which is JSON. ``loads`` refuses all three, so a file
that says a value twice, or a number that is not one, is refused by name instead of read as
one of its readings. The callers re-raise ``StrictJSONError`` as their own error, with the file
named.
"""

from __future__ import annotations

import json


class StrictJSONError(ValueError):
    """Text that is not JSON, or JSON with a key twice in one object or a non-finite constant."""


def _no_duplicates(pairs: list) -> dict:
    d = {}
    for k, v in pairs:
        if k in d:
            raise StrictJSONError(f"key {k!r} appears twice in one object")
        d[k] = v
    return d


def _no_constant(name: str):
    raise StrictJSONError(f"{name} is not a JSON number")


def loads(text: str) -> object:
    """``json.loads`` with duplicate keys and ``NaN``/``Infinity`` refused."""
    try:
        return json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_no_constant)
    except json.JSONDecodeError as e:
        raise StrictJSONError(f"not JSON: {e}") from None
