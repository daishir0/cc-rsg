"""M0 acceptance tests: constitution + schema 0.2.0 + three-layer skeleton.

Run from the scripts/ directory:
    python -m pytest source_map_v2/tests/test_m0.py -q
"""

from __future__ import annotations

import json

import pytest

from source_map_v2 import SCHEMA_VERSION, build_source_map
from source_map_v2 import extractors, taxonomy
from source_map_v2.model import IdFactory, SourceMap, SourceUnit


# --------------------------------------------------------------------------
# Constitution (taxonomy)
# --------------------------------------------------------------------------

def test_every_role_maps_to_a_universal_table():
    for role in taxonomy.ROLES:
        assert taxonomy.table_for_role(role) in taxonomy.UNIVERSAL_TABLES


def test_register_kind_binds_role_and_tier():
    taxonomy.register_kind("test_widget", "schema", "micro")
    assert taxonomy.role_for_kind("test_widget") == "schema"
    assert taxonomy.tier_for_kind("test_widget") == "micro"


def test_register_kind_rejects_unknown_role_and_tier():
    with pytest.raises(taxonomy.TaxonomyError):
        taxonomy.register_kind("bad_role_kind", "not_a_role")
    with pytest.raises(taxonomy.TaxonomyError):
        taxonomy.register_kind("bad_tier_kind", "class", "nano")


def test_register_kind_refuses_conflicting_rebind():
    taxonomy.register_kind("stable_kind", "class")
    taxonomy.register_kind("stable_kind", "class")  # idempotent ok
    with pytest.raises(taxonomy.TaxonomyError):
        taxonomy.register_kind("stable_kind", "endpoint")


# --------------------------------------------------------------------------
# Schema 0.2.0 (model)
# --------------------------------------------------------------------------

def test_unit_to_dict_carries_table_and_endpoint():
    u = SourceUnit(
        id="SRC-0001", path="a/api.py", line_range=(10, 20), language="python",
        role="endpoint", kind="fastapi_endpoint", name="create", tier="middle",
        framework="fastapi", endpoint={"method": "POST", "path": "/x"},
    )
    u.validate()
    d = u.to_dict()
    assert d["table"] == taxonomy.TABLE_ACTIONS
    assert d["endpoint"] == {"method": "POST", "path": "/x"}
    assert d["framework"] == "fastapi"
    assert d["line_range"] == [10, 20]


def test_endpoint_metadata_only_on_endpoint_role():
    bad = SourceUnit(
        id="SRC-0002", path="a.py", line_range=(1, 2), language="python",
        role="class", kind="py_class", name="X", endpoint={"method": "GET", "path": "/"},
    )
    with pytest.raises(taxonomy.TaxonomyError):
        bad.validate()


def test_sourcemap_stats_and_schema_version():
    sm = SourceMap(target_root="demo")
    sm.units = [
        SourceUnit("SRC-0001", "a.py", (1, 2), "python", "class", "py_class", "A"),
        SourceUnit("SRC-0002", "a.py", (3, 9), "python", "endpoint", "py_endpoint", "f",
                   endpoint={"method": "GET", "path": "/"}),
        SourceUnit("SRC-0003", "b.ts", (1, 1), "typescript", "schema", "ts_interface", "T"),
    ]
    sm.files_scanned = 2
    payload = sm.to_dict()
    assert payload["schema_version"] == SCHEMA_VERSION == "0.2.0"
    stats = payload["stats"]
    assert stats["units_total"] == 3
    assert stats["by_role"] == {"class": 1, "endpoint": 1, "schema": 1}
    assert stats["by_language"] == {"python": 2, "typescript": 1}
    # round-trips through JSON
    assert json.loads(json.dumps(payload))["stats"]["units_total"] == 3


# --------------------------------------------------------------------------
# Three-layer skeleton (pipeline)
# --------------------------------------------------------------------------

def _make_project(tmp_path):
    root = tmp_path / "proj"
    (root / "app").mkdir(parents=True)
    (root / "app" / "main.py").write_text("def hello():\n    return 1\n", encoding="utf-8")
    (root / "app" / "ui.ts").write_text("export const x = 1\n", encoding="utf-8")
    (root / "legacy.php").write_text("<?php class C {}\n", encoding="utf-8")
    (root / "README.txt").write_text("not source\n", encoding="utf-8")
    (root / "requirements.txt").write_text("fastapi==0.110\n", encoding="utf-8")
    (root / "package.json").write_text(json.dumps({"dependencies": {"next": "14"}}), encoding="utf-8")
    return root


def test_layer1_framework_detection_with_evidence(tmp_path):
    root = _make_project(tmp_path)
    payload = build_source_map(root).to_dict()
    fws = {h["framework"] for h in payload["detected_frameworks"]}
    assert "fastapi" in fws and "nextjs" in fws
    assert all(h["evidence"] for h in payload["detected_frameworks"])


def test_unsupported_language_falls_back_with_loud_warning(tmp_path):
    """A recognised language with no extractor (php) must warn, not vanish (P4)."""
    root = _make_project(tmp_path)  # contains legacy.php + README.txt
    payload = build_source_map(root).to_dict()
    assert any("'php'" in w for w in payload["warnings"])
    php_units = [u for u in payload["units"] if u["language"] == "php"]
    assert php_units and php_units[0]["kind"] == "php_file"   # file-level fallback
    assert payload["stats"]["files_excluded"] >= 1            # README.txt excluded


def test_supported_languages_are_not_warned(tmp_path):
    """python/typescript are autoloaded; they must be extracted, not warned."""
    root = _make_project(tmp_path)
    payload = build_source_map(root).to_dict()
    assert not any("'python'" in w for w in payload["warnings"])
    assert not any("'typescript'" in w for w in payload["warnings"])
    # main.py's `def hello()` was really extracted as a callable
    assert any(u["language"] == "python" and u["role"] == "callable" and u["name"] == "hello"
               for u in payload["units"])


def test_registered_extractor_is_dispatched_with_framework(tmp_path):
    """Prove layer-2 dispatch + framework hand-off via a dummy extractor on php."""
    taxonomy.register_kind("dummy_endpoint", "endpoint", "middle")

    class DummyPhp(extractors.Extractor):
        language = "php"

        def extract(self, path, source, id_factory, framework=None, context=None):
            return [SourceUnit(
                id=id_factory(), path=path, line_range=(1, 1), language="php",
                role="endpoint", kind="dummy_endpoint", name="dummy",
                framework=framework, endpoint={"method": "GET", "path": "/dummy"},
            )]

    saved = extractors.get_extractor("php")
    extractors.register(DummyPhp())
    try:
        root = _make_project(tmp_path)
        payload = build_source_map(root).to_dict()
        php_units = [u for u in payload["units"] if u["language"] == "php"]
        assert any(u["role"] == "endpoint" and u["kind"] == "dummy_endpoint" for u in php_units)
        assert not any("'php'" in w for w in payload["warnings"])  # php now handled
    finally:
        if saved is None:
            extractors._REGISTRY.pop("php", None)
        else:
            extractors._REGISTRY["php"] = saved
