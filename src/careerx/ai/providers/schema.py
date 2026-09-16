"""Pydantic -> strict JSON Schema conversion for OpenAI structured outputs.

OpenAI's ``json_schema`` response format only accepts a restricted dialect:
every property must be listed in ``required``, objects must set
``additionalProperties: false``, and keywords like ``default`` or ``format``
are rejected. Pydantic emits none of that by default, so we normalise here.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

_UNSUPPORTED_KEYWORDS = frozenset(
    {
        "default",
        "examples",
        "format",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minimum",
        "maximum",
        "minLength",
        "maxLength",
        "pattern",
        "minItems",
        "maxItems",
        "uniqueItems",
    }
)


def to_strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Return a strict-mode JSON Schema for ``model``."""
    schema = model.model_json_schema(ref_template="#/$defs/{model}")
    return _normalise(schema)


def _normalise(node: Any) -> Any:
    if isinstance(node, list):
        return [_normalise(item) for item in node]

    if not isinstance(node, dict):
        return node

    result: dict[str, Any] = {}

    for key, value in node.items():
        if key in _UNSUPPORTED_KEYWORDS:
            continue
        if key == "$defs":
            result[key] = {name: _normalise(definition) for name, definition in value.items()}
        else:
            result[key] = _normalise(value)

    if result.get("type") == "object" or "properties" in result:
        properties = result.get("properties", {})
        result["properties"] = properties
        result["type"] = "object"
        result["additionalProperties"] = False
        result["required"] = list(properties)

    return result
