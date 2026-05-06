"""Generate provider-formatted JSON schemas from Python tool signatures.

Phase 1 emits Anthropic's ``{"name", "description", "input_schema"}``
flavor only. The internal ``ToolSpec`` is provider-blind so Phase 2 can
add ``to_openai()`` / ``to_gemini()`` over the same source of truth.

Schemas are derived from ``inspect.signature()`` + the function's
docstring. For the 21 tools we ship today the parameter types are all
plain ``str | int | bool | dict`` (with optional ``| None`` unions and
defaults), which round-trip cleanly through this naive translator.

Param descriptions are pulled from the ``Args:`` block of each
docstring (Google-style, matching the convention already used across
``mcp_server/tools/**``). Docstrings without an Args block fall back to
type-only schemas — the model still gets a useful description from the
function-level summary.
"""
from __future__ import annotations

import inspect
import re
import typing
from dataclasses import dataclass, field
from typing import Any, Callable

from core.llm.tool_dispatch import _REGISTRY


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict  # JSON-Schema "object" — properties + required


def _python_to_json_type(annotation: Any) -> dict:
    """Map a Python annotation to a JSON Schema fragment.

    Handles the small surface area we actually use: bare ``str``/``int``/
    ``bool``/``dict``/``list``, ``X | None`` unions (treated as the
    non-None side, ``required`` reflects the optional-ness elsewhere),
    and string forward-refs (e.g. ``"int | None"``).
    """
    # Handle string annotations (PEP 563-style, used in some modules).
    if isinstance(annotation, str):
        s = annotation.strip()
        s_no_none = re.sub(r"\s*\|\s*None\b|\bNone\s*\|\s*", "", s).strip()
        primitive = {
            "str": {"type": "string"},
            "int": {"type": "integer"},
            "float": {"type": "number"},
            "bool": {"type": "boolean"},
            "dict": {"type": "object"},
            "list": {"type": "array"},
        }
        if s_no_none in primitive:
            return primitive[s_no_none]
        # Common typing aliases written as strings.
        if "list" in s_no_none.lower():
            return {"type": "array"}
        if "dict" in s_no_none.lower():
            return {"type": "object"}
        return {}  # unknown — leave untyped, model sees just the name

    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)

    # X | None or Optional[X] — peel off NoneType.
    if origin is typing.Union or (origin is None and args):
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _python_to_json_type(non_none[0])

    if annotation in (str,):
        return {"type": "string"}
    if annotation in (int,):
        return {"type": "integer"}
    if annotation in (float,):
        return {"type": "number"}
    if annotation in (bool,):
        return {"type": "boolean"}
    if annotation in (dict,) or origin is dict:
        return {"type": "object"}
    if annotation in (list,) or origin is list:
        return {"type": "array"}

    return {}


_DOCSTRING_ARG_HEADER = re.compile(r"^\s*Args:\s*$", re.MULTILINE)
_DOCSTRING_NEXT_SECTION = re.compile(
    r"^\s*(Returns|Raises|Yields|Examples?|Notes?):\s*$", re.MULTILINE
)
_ARG_LINE = re.compile(r"^\s+(\w+)\s*(?:\([^)]*\))?\s*:\s*(.*)$")


def _parse_arg_descriptions(doc: str | None) -> tuple[str, dict[str, str]]:
    """Split docstring into (summary, {arg_name: description}).

    Matches Google-style ``Args:`` blocks. Continuation lines (extra
    indentation under the previous arg) are appended to that arg's
    description. Anything before ``Args:`` is the function summary.
    """
    if not doc:
        return "", {}

    text = inspect.cleandoc(doc)
    arg_match = _DOCSTRING_ARG_HEADER.search(text)
    if not arg_match:
        return text.strip(), {}

    summary = text[: arg_match.start()].strip()
    rest = text[arg_match.end():]
    next_section = _DOCSTRING_NEXT_SECTION.search(rest)
    args_block = rest[: next_section.start()] if next_section else rest

    descriptions: dict[str, str] = {}
    current: str | None = None
    for line in args_block.splitlines():
        if not line.strip():
            current = None
            continue
        m = _ARG_LINE.match(line)
        if m:
            current = m.group(1)
            descriptions[current] = m.group(2).strip()
        elif current is not None:
            descriptions[current] = (descriptions[current] + " " + line.strip()).strip()
    return summary, descriptions


def _build_spec(name: str, fn: Callable) -> ToolSpec:
    sig = inspect.signature(fn)
    summary, arg_descs = _parse_arg_descriptions(fn.__doc__)

    properties: dict[str, dict] = {}
    required: list[str] = []
    for pname, param in sig.parameters.items():
        if pname == "self":
            continue
        schema = _python_to_json_type(param.annotation) or {}
        desc = arg_descs.get(pname)
        if desc:
            schema = {**schema, "description": desc}
        properties[pname] = schema
        if param.default is inspect.Parameter.empty:
            required.append(pname)

    parameters: dict = {
        "type": "object",
        "properties": properties,
    }
    if required:
        parameters["required"] = required

    return ToolSpec(
        name=name,
        description=summary or fn.__doc__ or name,
        parameters=parameters,
    )


def all_tool_specs() -> list[ToolSpec]:
    """Build a `ToolSpec` per registered tool. Cached for the process."""
    global _CACHE
    if _CACHE is None:
        _CACHE = [_build_spec(name, fn) for name, fn in _REGISTRY.items()]
    return _CACHE


_CACHE: list[ToolSpec] | None = None


def to_anthropic(specs: list[ToolSpec] | None = None) -> list[dict]:
    """Format specs as Anthropic Messages-API tool definitions."""
    specs = specs if specs is not None else all_tool_specs()
    return [
        {
            "name": s.name,
            "description": s.description,
            "input_schema": s.parameters,
        }
        for s in specs
    ]
