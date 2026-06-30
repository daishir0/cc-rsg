"""M5 acceptance: PHP / Java / C# extractors (tree-sitter)."""

from __future__ import annotations

import pytest

from source_map_v2 import extractors
from source_map_v2.model import IdFactory


def _ext(lang, src, path):
    e = extractors.get_extractor(lang)
    return e.extract(path, src, IdFactory()) if e else None


# ------------------------------- PHP -------------------------------
PHP = '''\
<?php
namespace App\\Http;
class UserController { public function index() {} }
interface Repo {}
trait Loggable {}
class User extends Model {}
Route::get('/users', [UserController::class, 'index']);
Route::post('/users', 'store');
'''


@pytest.mark.skipif(extractors.get_extractor("php") is None, reason="no php grammar")
def test_php_types_routes_models():
    units = _ext("php", PHP, "app/Http/UserController.php")
    by = {(u.kind, u.name) for u in units}
    assert ("php_class", "UserController") in by
    assert ("php_interface", "Repo") in by
    assert ("php_trait", "Loggable") in by
    assert ("eloquent_model", "User") in by         # extends Model -> model
    routes = [u for u in units if u.kind == "laravel_route"]
    methods = {u.endpoint["method"] for u in routes}
    assert {"GET", "POST"} <= methods
    assert any(u.endpoint["path"] == "/users" for u in routes)


# ------------------------------- Java ------------------------------
JAVA = '''\
package a;
@RestController
class UserController {
  @GetMapping("/users") public String list(){return null;}
  @PostMapping("/users") public String add(){return null;}
}
@Service class UserService {}
@Entity class User {}
interface Repo {}
enum Role { ADMIN, USER }
record Dto(int id) {}
'''


@pytest.mark.skipif(extractors.get_extractor("java") is None, reason="no java grammar")
def test_java_spring_and_types():
    units = _ext("java", JAVA, "src/UserController.java")
    by = {(u.kind, u.name) for u in units}
    assert ("spring_controller", "UserController") in by
    assert ("spring_service", "UserService") in by
    assert ("jpa_entity", "User") in by
    assert ("java_interface", "Repo") in by
    assert ("java_enum", "Role") in by
    assert ("java_record", "Dto") in by
    eps = [u for u in units if u.kind == "spring_endpoint"]
    methods = {u.endpoint["method"] for u in eps}
    assert {"GET", "POST"} <= methods
    assert any(u.endpoint["path"] == "/users" for u in eps)
    assert all(u.role == "endpoint" for u in eps)


# ------------------------------- C# --------------------------------
CSHARP = '''\
namespace A;
[ApiController]
public class UsersController {
  [HttpGet("/users")] public string List() => null;
  [HttpPost("/users")] public string Add() => null;
}
public interface IRepo {}
public record Dto(int Id);
public struct Point { public int X; }
'''


@pytest.mark.skipif(extractors.get_extractor("csharp") is None, reason="no csharp grammar")
def test_csharp_aspnet_and_types():
    units = _ext("csharp", CSHARP, "src/UsersController.cs")
    by = {(u.kind, u.name) for u in units}
    assert ("csharp_class", "UsersController") in by
    assert ("csharp_interface", "IRepo") in by
    assert ("csharp_record", "Dto") in by
    assert ("csharp_struct", "Point") in by
    eps = [u for u in units if u.kind == "aspnet_endpoint"]
    methods = {u.endpoint["method"] for u in eps}
    assert {"GET", "POST"} <= methods
    assert any(u.endpoint["path"] == "/users" for u in eps)
