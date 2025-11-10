import json
from pathlib import Path

import pytest

from pango_explain.gui import unroll_aliance
from collections import OrderedDict

from pango_explain.pango_alias import (
    generate_alias_ancestry_report,
    get_ancestral_dict,
    load_alias_map,
    lookup_alias,
    unroll_pango_name,
)


@pytest.fixture(scope="session")
def alias_map() -> dict:
    path = Path(__file__).resolve().parents[1] / "alias_key.json"
    return load_alias_map(path)


def test_lookup_alias_with_single_string(alias_map):
    assert lookup_alias("BA", alias_map) == "B.1.1.529"


def test_lookup_alias_with_list(alias_map):
    assert lookup_alias("XCD", alias_map) == ["XBB.1*", "BQ.1.1.25*"]


def test_lookup_alias_with_empty_value(alias_map):
    assert lookup_alias("B", alias_map) == ""


def test_lookup_alias_not_present(alias_map):
    assert lookup_alias("ZQP", alias_map) is None


def test_alias_map_contains_only_expected_value_types():
    path = Path(__file__).resolve().parents[1] / "alias_key.json"
    raw = json.loads(path.read_text(encoding="utf-8"))

    for value in raw.values():
        assert (
            isinstance(value, str)
            or (isinstance(value, list) and all(isinstance(item, str) for item in value))
        )


def test_unroll_aliance_with_provided_mapping(alias_map):
    assert unroll_aliance("BA", alias_map=alias_map) == "B.1.1.529"


def test_unroll_aliance_with_path(tmp_path):
    path = tmp_path / "aliases.json"
    path.write_text(json.dumps({"alias": ["value1", "value2"]}), encoding="utf-8")

    assert unroll_aliance("alias", alias_map_path=path) == ["value1", "value2"]


@pytest.mark.parametrize(
    "designation,expected",
    [
        ("JN.1", "B.1.1.529.2.86.1.1"),
        ("jn.1", "B.1.1.529.2.86.1.1"),
        ("XBB.1.5", "XBB.1.5"),
        ("XBC", "XBC"),
        ("XFG", "XFG"),
        ("A", "A"),
    ],
)
def test_unroll_pango_name_valid(designation, expected, alias_map):
    assert unroll_pango_name(designation, alias_map) == expected


@pytest.mark.parametrize(
    "designation",
    [
        "XZZ",
        "B.1.1.4.2",
        "FK.1.4.F",
        "BA",
    ],
)
def test_unroll_pango_name_invalid(designation, alias_map):
    with pytest.raises(ValueError):
        unroll_pango_name(designation, alias_map)


@pytest.mark.parametrize(
    "designation,expected",
    [
        ("XFG.1.3", OrderedDict([("XFG", None)])),
        (
            "BA.5.1",
            OrderedDict(
                [
                    ("BA", "B.1.1.529"),
                    ("B", None),
                ]
            ),
        ),
        (
            "QU.5.2",
            OrderedDict(
                [
                    ("QU", "NY.3.1.2"),
                    ("NY", "LP.8.1.1"),
                    ("LP", "KP.1.1.3"),
                    ("KP", "JN.1.11.1"),
                    ("JN", "BA.2.86.1"),
                    ("BA", "B.1.1.529"),
                    ("B", None),
                ]
            ),
        ),
        (
            "KH.1.2.4",
            OrderedDict(
                [
                    ("KH", "JE.1.1.1"),
                    ("JE", "GJ.1.2.1"),
                    ("GJ", "XBB.2.3.3"),
                    ("XBB", None),
                ]
            ),
        ),
        (
            "QU",
            OrderedDict(
                [
                    ("QU", "NY.3.1.2"),
                    ("NY", "LP.8.1.1"),
                    ("LP", "KP.1.1.3"),
                    ("KP", "JN.1.11.1"),
                    ("JN", "BA.2.86.1"),
                    ("BA", "B.1.1.529"),
                    ("B", None),
                ]
            ),
        ),
        (
            "KH",
            OrderedDict(
                [
                    ("KH", "JE.1.1.1"),
                    ("JE", "GJ.1.2.1"),
                    ("GJ", "XBB.2.3.3"),
                    ("XBB", None),
                ]
            ),
        ),
    ],
)
def test_get_ancestral_dict(designation, expected, alias_map):
    assert get_ancestral_dict(designation, alias_map) == expected


@pytest.mark.parametrize(
    "designation",
    [
        "BA.14.S",
        "XOQKFA.13",
    ],
)
def test_get_ancestral_dict_invalid(designation, alias_map):
    with pytest.raises(ValueError):
        get_ancestral_dict(designation, alias_map)


def test_generate_alias_ancestry_report_contains_known_examples(alias_map):
    report = generate_alias_ancestry_report(alias_map)

    def block_for(alias: str) -> str:
        for chunk in report.split("\n\n"):
            lines = chunk.splitlines()
            if not lines:
                continue
            if lines[0].startswith(f"{alias}"):
                return chunk
        raise AssertionError(f"No block found for {alias}")

    qu_block = block_for("QU")
    assert qu_block.splitlines() == [
        "QU = NY.3.1.2",
        "NY = LP.8.1.1",
        "LP = KP.1.1.3",
        "KP = JN.1.11.1",
        "JN = BA.2.86.1",
        "BA = B.1.1.529",
        "B",
    ]

    kh_block = block_for("KH")
    assert kh_block.splitlines() == [
        "KH = JE.1.1.1",
        "JE = GJ.1.2.1",
        "GJ = XBB.2.3.3",
        "XBB",
    ]
