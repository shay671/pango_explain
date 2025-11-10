import json
from pathlib import Path

import pytest

from pango_explain.gui import unroll_aliance
from pango_explain.pango_alias import load_alias_map, lookup_alias


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
