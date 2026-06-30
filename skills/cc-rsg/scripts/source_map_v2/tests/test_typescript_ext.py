"""M2 acceptance: TypeScript extractor fixes v1's keyword-as-name + drops."""

from __future__ import annotations

import pytest

from source_map_v2 import extractors
from source_map_v2.model import IdFactory

pytestmark = pytest.mark.skipif(
    extractors.get_extractor("typescript") is None,
    reason="tree-sitter (typescript grammar) not installed",
)

TS_SRC = '''\
export interface Recipe { id: string; title: string; }
export type RecipeId = string;
export enum Status { Draft, Published }
export class RecipeService {
  getRecipe(id: string) { return null; }
  async createRecipe(d: Recipe) { return d; }
}
export const listRecipes = () => [];
function internalHelper() { return 1; }
const arrowHelper = () => 2;
'''

EXPRESS_SRC = '''\
import express from "express";
const app = express();
app.get("/health", (req, res) => res.send("ok"));
app.post("/users", (req, res) => res.json({}));
'''


def _extract(src, path="x/types.ts"):
    ext = extractors.get_extractor("typescript")
    return ext.extract(path, src, IdFactory())


def test_interface_type_enum_get_real_names():
    units = {u.name: u for u in _extract(TS_SRC)}
    for nm in ("Recipe", "RecipeId", "Status"):
        assert nm in units and units[nm].role == "schema"  # v1 named these "interface"/"type"/"enum"


def test_class_has_real_block_range():
    units = {u.name: u for u in _extract(TS_SRC)}
    svc = units["RecipeService"]
    assert svc.role == "class" and svc.line_range[1] > svc.line_range[0]  # v1 was single-line


def test_non_exported_declarations_recovered():
    names = {u.name for u in _extract(TS_SRC)}
    assert "internalHelper" in names   # v1 dropped non-exports
    assert "arrowHelper" in names


def test_express_routes_typed_as_endpoints():
    units = _extract(EXPRESS_SRC, path="x/server.ts")
    eps = [u for u in units if u.role == "endpoint"]
    got = {(u.endpoint["method"], u.endpoint["path"]) for u in eps}
    assert ("GET", "/health") in got and ("POST", "/users") in got
