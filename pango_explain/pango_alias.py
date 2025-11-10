"""Utilities for working with Pango alias mappings.

This module provides helpers to load the alias mapping JSON file that ships
with the repository and to resolve an alias into its full Pango designation.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple, Union
from collections.abc import Mapping, MutableMapping
import json
import re
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


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


def _normalize_designation(value: str) -> str:
    """Return ``value`` as an upper-cased, canonical Pango designation string."""

    letters, suffix_parts = _split_pango_name(value)
    return letters + "".join(f".{part}" for part in suffix_parts)


def _find_alias_for_value(value: str, alias_map: Mapping[str, AliasValue]) -> Optional[str]:
    """Return the alias whose stored value matches ``value``."""

    try:
        normalized_value = _normalize_designation(value)
    except ValueError:
        return None

    for key, alias_value in alias_map.items():
        if isinstance(alias_value, str) and alias_value:
            try:
                candidate = _normalize_designation(alias_value)
            except ValueError:
                continue
            if candidate == normalized_value:
                return key

    try:
        letters, suffix_parts = _split_pango_name(normalized_value)
    except ValueError:
        return None

    if suffix_parts:
        return None

    root_key = _find_case_insensitive_key(letters, alias_map)
    if root_key is not None:
        return root_key

    if letters in {"A", "B"}:
        return letters

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


def get_ancestral_dict(
    value: str, alias_map: Mapping[str, AliasValue]
) -> "OrderedDict[str, Optional[str]]":
    """Return the ancestry chain for ``value`` as an ordered mapping.

    The mapping keys correspond to alias names and the associated value holds the
    immediate ancestor designation enriched with the three-number suffix that
    differentiates the two aliases.  The terminal ancestor (for example ``B`` or
    ``XBB``) has the value ``None``.

    Parameters
    ----------
    value:
        Alias or lineage to resolve.
    alias_map:
        Mapping containing the alias data.

    Returns
    -------
    OrderedDict[str, Optional[str]]
        Ordered mapping describing the ancestry of ``value``.

    Raises
    ------
    TypeError
        If ``alias_map`` is not a mapping instance.
    ValueError
        If ``value`` cannot be traced through the alias mapping.
    """

    if not isinstance(alias_map, Mapping):
        raise TypeError("alias_map must be a mapping")

    if not isinstance(value, str):
        raise TypeError("value must be a string")

    trimmed = value.strip()
    if not trimmed:
        raise ValueError("value must not be empty")

    try:
        original_letters, original_suffix = _split_pango_name(trimmed)
    except ValueError as exc:
        raise ValueError(f"'{value}' is not a valid Pango designation") from exc

    if original_suffix or original_letters in {"A", "B"} or original_letters.startswith("X"):
        unrolled = unroll_pango_name(trimmed, alias_map)
    else:
        alias_key = _find_case_insensitive_key(original_letters, alias_map)
        if alias_key is None:
            raise ValueError(f"Unknown alias '{value}'")
        alias_value = alias_map[alias_key]
        if not isinstance(alias_value, str) or not alias_value:
            raise ValueError(
                f"Alias '{alias_key}' does not resolve to a string Pango designation"
            )
        unrolled = _normalize_designation(alias_value)

    unrolled_letters, unrolled_suffix = _split_pango_name(unrolled)

    if len(original_suffix) > len(unrolled_suffix):
        raise ValueError("Unrolled designation shorter than original suffix")

    ancestor_suffix_parts = (
        unrolled_suffix[: len(unrolled_suffix) - len(original_suffix)]
        if original_suffix
        else unrolled_suffix
    )
    ancestor_value = unrolled_letters + "".join(
        f".{part}" for part in ancestor_suffix_parts
    )

    ancestry: "OrderedDict[str, Optional[str]]" = OrderedDict()
    current_value = ancestor_value

    while True:
        alias_name = _find_alias_for_value(current_value, alias_map)
        if alias_name is None:
            raise ValueError(f"No alias entry found for '{current_value}'")

        letters, suffix_parts = _split_pango_name(current_value)

        if len(suffix_parts) < 3:
            if alias_name not in ancestry:
                ancestry[alias_name] = None
            break

        parent_suffix_parts = suffix_parts[:-3]
        parent_value = letters + "".join(f".{part}" for part in parent_suffix_parts)
        parent_alias = _find_alias_for_value(parent_value, alias_map)
        if parent_alias is None:
            raise ValueError(f"No alias entry found for '{parent_value}'")

        tail = "".join(f".{part}" for part in suffix_parts[-3:])
        ancestry[alias_name] = parent_alias + tail
        current_value = parent_value

    return ancestry


def _format_ancestry_chain(ancestry: Mapping[str, Optional[str]]) -> str:
    """Return a comma-separated string describing ``ancestry`` without the root."""

    parts = [f"{alias} = {parent}" for alias, parent in ancestry.items() if parent]
    return " , ".join(parts)


def generate_alias_ancestry_report(
    alias_map: Mapping[str, AliasValue]
) -> List[Tuple[str, str]]:
    """Return alias-to-ancestry rows for every non-root alias."""

    if not isinstance(alias_map, Mapping):
        raise TypeError("alias_map must be a mapping")

    rows: List[Tuple[str, str]] = []
    for alias in sorted(alias_map.keys(), key=lambda item: item.upper()):
        value = alias_map[alias]
        if not (isinstance(value, str) and value):
            continue

        ancestry = get_ancestral_dict(alias, alias_map)
        formatted = _format_ancestry_chain(ancestry)
        if formatted:
            rows.append((alias, formatted))

    return rows


def _format_recombinant_components(components: Sequence[str]) -> str:
    """Return a comma-separated string describing recombinant components."""

    return " , ".join(components)


def generate_recombinant_report(
    alias_map: Mapping[str, AliasValue]
) -> List[Tuple[str, str]]:
    """Return recombinant alias rows comprised of the stored component lists."""

    if not isinstance(alias_map, Mapping):
        raise TypeError("alias_map must be a mapping")

    rows: List[Tuple[str, str]] = []
    for alias in sorted(alias_map.keys(), key=lambda item: item.upper()):
        value = alias_map[alias]
        if not (alias.upper().startswith("X") and isinstance(value, list) and value):
            continue

        if not all(isinstance(item, str) for item in value):
            raise ValueError(f"Recombinant entry for '{alias}' must contain only strings")

        formatted = _format_recombinant_components(value)
        rows.append((alias, formatted))

    return rows


def _column_letter(index: int) -> str:
    """Return the Excel column letter for ``index`` (0-based)."""

    if index < 0:
        raise ValueError("index must be non-negative")

    result = []
    current = index
    while True:
        current, remainder = divmod(current, 26)
        result.append(chr(ord("A") + remainder))
        if current == 0:
            break
        current -= 1
    return "".join(reversed(result))


def write_alias_ancestry_workbook(
    rows: Iterable[Tuple[str, str]],
    path: Union[str, Path],
    recombinant_rows: Optional[Iterable[Tuple[str, str]]] = None,
) -> Path:
    """Write alias and recombinant rows to ``path`` as a multi-sheet workbook."""

    if not isinstance(path, (str, Path)):
        raise TypeError("path must be a string or Path instance")

    def normalize_pairs(
        items: Iterable[Tuple[str, str]],
        item_name: str,
    ) -> List[Tuple[str, str]]:
        normalized: List[Tuple[str, str]] = []
        for entry in items:
            if not isinstance(entry, Sequence) or isinstance(entry, (str, bytes)):
                raise TypeError(f"{item_name} must be an iterable of string pairs")
            if len(entry) != 2:
                raise ValueError(f"{item_name} entries must contain exactly two elements")
            first, second = entry
            if not isinstance(first, str) or not isinstance(second, str):
                raise TypeError(f"{item_name} entries must contain string pairs")
            normalized.append((first, second))
        return normalized

    normalized_rows = normalize_pairs(rows, "rows")
    recombinant_rows = recombinant_rows or []
    normalized_recombinant_rows = normalize_pairs(recombinant_rows, "recombinant_rows")

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def make_cell(col_index: int, row_index: int, value: str) -> str:
        cell_ref = f"{_column_letter(col_index)}{row_index}"
        return (
            f'<c r="{cell_ref}" t="inlineStr">'
            f"<is><t>{escape(value)}</t></is>"
            f"</c>"
        )

    def make_row(row_index: int, values: Sequence[str]) -> str:
        cells = "".join(make_cell(idx, row_index, value) for idx, value in enumerate(values))
        return f"<row r=\"{row_index}\">{cells}</row>"

    def build_sheet(headers: Sequence[str], entries: Sequence[Tuple[str, str]]) -> str:
        sheet_rows = [make_row(1, headers)]
        for offset, entry in enumerate(entries, start=2):
            sheet_rows.append(make_row(offset, entry))

        max_row = len(sheet_rows)
        last_col = _column_letter(len(headers) - 1)
        dimension_ref = f"A1:{last_col}{max_row}" if max_row > 1 else f"A1:{last_col}1"

        return (
            "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
            "<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\""
            " xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">"
            f"<dimension ref=\"{dimension_ref}\"/>"
            "<sheetData>"
            + "".join(sheet_rows)
            + "</sheetData>"
            "</worksheet>"
        )

    alias_sheet_xml = build_sheet(("Alias", "Ancestry"), normalized_rows)
    recombinant_sheet_xml = build_sheet(
        ("Recombinant", "Comprising variants"), normalized_recombinant_rows
    )

    workbook_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\""
        " xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">"
        "<sheets>"
        "<sheet name=\"Alias ancestry\" sheetId=\"1\" r:id=\"rId1\"/>"
        "<sheet name=\"Recombinants\" sheetId=\"2\" r:id=\"rId2\"/>"
        "</sheets>"
        "</workbook>"
    )

    rels_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
        "<Relationship Id=\"rId1\""
        " Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\""
        " Target=\"worksheets/sheet1.xml\"/>"
        "<Relationship Id=\"rId2\""
        " Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\""
        " Target=\"worksheets/sheet2.xml\"/>"
        "</Relationships>"
    )

    package_rels_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">"
        "<Relationship Id=\"rId1\""
        " Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\""
        " Target=\"xl/workbook.xml\"/>"
        "</Relationships>"
    )

    content_types_xml = (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
        "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
        "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
        "<Override PartName=\"/xl/workbook.xml\""
        " ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/>"
        "<Override PartName=\"/xl/worksheets/sheet1.xml\""
        " ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>"
        "<Override PartName=\"/xl/worksheets/sheet2.xml\""
        " ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>"
        "</Types>"
    )

    with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml)
        archive.writestr("_rels/.rels", package_rels_xml)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", rels_xml)
        archive.writestr("xl/worksheets/sheet1.xml", alias_sheet_xml)
        archive.writestr("xl/worksheets/sheet2.xml", recombinant_sheet_xml)

    return output_path


def default_report_path() -> Path:
    """Return the default path used for alias ancestry reports."""

    today = date.today().isoformat()
    filename = f"Pango names {today}.xlsx"
    return Path(__file__).resolve().parent.parent / filename
