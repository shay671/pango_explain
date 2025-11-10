"""Utilities for working with Pango alias mappings.

This module provides helpers to load the alias mapping JSON file that ships
with the repository and to resolve an alias into its full Pango designation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Union
from collections.abc import Mapping, MutableMapping
import json


AliasValue = Union[str, List[str]]


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
