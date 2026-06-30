"""M3 acceptance: Python extractor recovers what v1 regex dropped."""

from __future__ import annotations

import pytest

from source_map_v2 import extractors
from source_map_v2.model import IdFactory

pytestmark = pytest.mark.skipif(
    extractors.get_extractor("python") is None,
    reason="tree-sitter (python grammar) not installed",
)

FASTAPI_SRC = '''\
from fastapi import APIRouter
from pydantic import BaseModel
router = APIRouter()

class RecipeIn(BaseModel):
    title: str

class RecipeService:
    def get(self, id): ...

@router.get("/recipes")
async def list_recipes():
    return []

@router.post("/recipes")
async def create_recipe(payload: RecipeIn):
    return payload

def sync_helper():
    return 1
'''


def _extract(src, framework="fastapi"):
    ext = extractors.get_extractor("python")
    return ext.extract("app/api.py", src, IdFactory(), framework=framework)


def test_async_endpoints_recovered_with_method_and_path():
    units = _extract(FASTAPI_SRC)
    eps = {u.name: u for u in units if u.role == "endpoint"}
    assert "list_recipes" in eps and "create_recipe" in eps  # v1 dropped both
    assert eps["list_recipes"].endpoint == {"method": "GET", "path": "/recipes"}
    assert eps["create_recipe"].endpoint == {"method": "POST", "path": "/recipes"}
    assert eps["create_recipe"].kind == "fastapi_endpoint"


def test_pydantic_schema_typed_as_schema():
    units = _extract(FASTAPI_SRC)
    schemas = [u for u in units if u.role == "schema"]
    assert any(u.name == "RecipeIn" and u.kind == "pydantic_schema" for u in schemas)


def test_plain_class_and_function_kept():
    units = _extract(FASTAPI_SRC)
    assert any(u.name == "RecipeService" and u.role == "class" for u in units)
    assert any(u.name == "sync_helper" and u.role == "callable" for u in units)


def test_block_ranges_are_multiline():
    units = _extract(FASTAPI_SRC)
    svc = next(u for u in units if u.name == "RecipeService")
    assert svc.line_range[1] > svc.line_range[0]  # real span, not single line
