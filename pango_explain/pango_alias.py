"""Utilities for working with Pango alias mappings.

This module provides helpers to load the alias mapping JSON file that ships
with the repository and to resolve an alias into its full Pango designation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from collections.abc import Mapping, MutableMapping
import json
import re


AliasValue = Union[str, List[str]]

_PANGO_PATTERN = re.compile(r"^([A-Za-z]+)((?:\.\d+)*)$")


def _split_pango_name(value: str) -> Tuple[str, List[str]]:
    """Return the letter prefix and numeric suffix parts of ``value``.

    Parameters
    ----------
    value:
        Candidate Pango designation.

    Returns
    -------
    Tuple[str, List[str]]
        A tuple containing the upper-cased letter component and a list of the
        numeric suffix components (without leading dots).

    Raises
    ------
    ValueError
        If ``value`` does not conform to the expected ``LETTERS[.NUMBER]*``
        structure.
    """

    match = _PANGO_PATTERN.fullmatch(value)
    if not match:
        raise ValueError("Value must contain letters followed by optional dot-number groups")

    letter_part = match.group(1).upper()
    suffix_raw = match.group(2)
    if not suffix_raw:
        return letter_part, []

    suffix_parts = [part for part in suffix_raw.lstrip(".").split(".") if part]
    return letter_part, suffix_parts


def _find_case_insensitive_key(key: str, alias_map: Mapping[str, AliasValue]) -> Optional[str]:
    """Return the original key from ``alias_map`` matching ``key`` case-insensitively."""

    key_upper = key.upper()
    for existing_key in alias_map.keys():
        if existing_key.upper() == key_upper:
            return existing_key
    return None


def load_alias_map(path: Union[str, Path]) -> Dict[str, AliasValue]:
    """Load the alias mapping from ``path``.

    Parameters
    ----------
    path:
        A path to the JSON file that stores the alias mapping. The file is
        expected to contain a JSON object whose keys are alias strings and
        whose values are either strings, lists of strings, or empty strings.

    Returns
    -------
    Dict[str, AliasValue]
        The parsed alias mapping.

    Raises
    ------
    ValueError
        If one of the values in the JSON file is not an empty string, a
        string, or a list of strings.
    """

    alias_path = Path(path)
    data = json.loads(alias_path.read_text(encoding="utf-8"))

    if not isinstance(data, Mapping):
        raise ValueError("Alias mapping JSON must describe an object/dict")

    validated: Dict[str, AliasValue] = {}
    for key, value in data.items():
        if isinstance(value, str):
            # Strings, including empty strings, are valid as-is.
            validated[key] = value
        elif isinstance(value, list) and all(isinstance(item, str) for item in value):
            validated[key] = value
        else:
            raise ValueError(
                "Alias mapping values must be strings, empty strings, or lists of strings"
            )

    return validated


def lookup_alias(alias: str, alias_map: MutableMapping[str, AliasValue]) -> Optional[AliasValue]:
    """Look up ``alias`` in ``alias_map``.

    Parameters
    ----------
    alias:
        The alias string to resolve.
    alias_map:
        A mapping produced by :func:`load_alias_map`.

    Returns
    -------
    Optional[AliasValue]
        The corresponding mapping value, which may be a string, list of
        strings, or an empty string. Returns ``None`` if the alias is not
        present in the mapping.
    """

    try:
        return alias_map[alias]
    except KeyError:
        return None


def unroll_pango_name(value: str, alias_map: Mapping[str, AliasValue]) -> str:
    """Return the fully unrolled Pango designation for ``value``.

    The function implements a restricted validation tailored for Pango names
    used in the alias mapping bundled with this project.  ``value`` must begin
    with a sequence of letters optionally followed by up to three ``.number``
    groups.  Roots ``A`` and ``B`` as well as aliases whose letter component
    starts with ``X`` (provided they exist in the alias mapping) are considered
    already unrolled, aside from the validation that they include at most three
    suffix groups.

    Non-root aliases are resolved through ``alias_map`` and the resulting value
    must itself describe a Pango designation whose suffix component count is a
    multiple of three.  The stored suffix is then extended with the suffix from
    ``value`` to produce the final unrolled lineage.

    Parameters
    ----------
    value:
        The candidate Pango designation to unroll.
    alias_map:
        Mapping containing the alias data.

    Returns
    -------
    str
        The unrolled Pango designation.

    Raises
    ------
    ValueError
        If ``value`` does not describe a valid or known Pango alias.
    """

    if not isinstance(value, str):
        raise TypeError("value must be a string")

    trimmed = value.strip()
    if not trimmed:
        raise ValueError("value must not be empty")

    try:
        letter_component, suffix_parts = _split_pango_name(trimmed)
    except ValueError as exc:
        raise ValueError(f"'{value}' is not a valid Pango designation") from exc

    if len(suffix_parts) > 3:
        raise ValueError("Pango designations may include at most three suffix groups")

    suffix_text = "".join(f".{part}" for part in suffix_parts)

    # Roots: A and B are always allowed, X-prefixed aliases must exist in the
    # mapping to be considered a root designation.
    if letter_component in {"A", "B"}:
        return letter_component + suffix_text

    alias_key = _find_case_insensitive_key(letter_component, alias_map)

    if letter_component.startswith("X"):
        if alias_key is None:
            raise ValueError(f"Unknown Pango designation '{value}'")
        return letter_component + suffix_text

    if not suffix_parts:
        raise ValueError("Non-root Pango designations must include at least one suffix group")

    if alias_key is None:
        raise ValueError(f"Unknown Pango designation '{value}'")

    alias_value = alias_map[alias_key]
    if not isinstance(alias_value, str) or not alias_value:
        raise ValueError(
            f"Alias '{alias_key}' does not resolve to a string Pango designation"
        )

    try:
        resolved_letters, resolved_suffix_parts = _split_pango_name(alias_value)
    except ValueError as exc:
        raise ValueError(
            f"Alias '{alias_key}' resolves to unsupported value '{alias_value}'"
        ) from exc

    if resolved_suffix_parts and len(resolved_suffix_parts) % 3 != 0:
        raise ValueError(
            f"Alias '{alias_key}' resolves to '{alias_value}', whose suffix length is not a multiple of three"
        )

    combined_suffix = resolved_suffix_parts + suffix_parts
    return resolved_letters + "".join(f".{part}" for part in combined_suffix)
