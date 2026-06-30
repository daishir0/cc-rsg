"""M6 acceptance: Go (tree-sitter) + SQL / COBOL (regex)."""

from __future__ import annotations

import pytest

from source_map_v2 import extractors
from source_map_v2.model import IdFactory


def _ext(lang, src, path):
    e = extractors.get_extractor(lang)
    return e.extract(path, src, IdFactory()) if e else None


# -------------------------------- Go --------------------------------
GO = '''\
package main
import "net/http"
type User struct { ID int }
type Repo interface { Get() }
func main() { http.HandleFunc("/users", h); r.GET("/ping", p) }
func (s *Svc) Save() {}
func h() {}
'''


@pytest.mark.skipif(extractors.get_extractor("go") is None, reason="no go grammar")
def test_go_types_funcs_endpoints():
    units = _ext("go", GO, "main.go")
    by = {(u.kind, u.name) for u in units}
    assert ("go_struct", "User") in by
    assert ("go_interface", "Repo") in by
    assert ("go_func", "main") in by
    assert ("go_method", "Save") in by
    eps = [u for u in units if u.role == "endpoint"]
    paths = {u.endpoint["path"] for u in eps}
    assert "/users" in paths and "/ping" in paths


# -------------------------------- SQL -------------------------------
SQL = '''\
CREATE TABLE users (id INT PRIMARY KEY, name TEXT);
CREATE OR REPLACE VIEW active_users AS SELECT * FROM users;
CREATE INDEX idx_users_name ON users(name);
CREATE OR REPLACE FUNCTION bump() RETURNS void AS $$ $$ LANGUAGE sql;
CREATE TRIGGER trg_audit AFTER INSERT ON users EXECUTE PROCEDURE bump();
'''


def test_sql_ddl_objects():
    units = _ext("sql", SQL, "schema.sql")
    by = {(u.kind, u.name) for u in units}
    assert ("sql_table", "users") in by
    assert ("sql_view", "active_users") in by
    assert ("sql_index", "idx_users_name") in by
    assert ("sql_routine", "bump") in by
    assert ("sql_trigger", "trg_audit") in by
    assert all(u.role == "datastore" for u in units)


# ------------------------------- COBOL ------------------------------
COBOL = '''\
       IDENTIFICATION DIVISION.
       PROGRAM-ID. PAYROLL.
       DATA DIVISION.
       FILE SECTION.
       FD  EMP-FILE.
       PROCEDURE DIVISION.
       MAIN-LOGIC SECTION.
       CALCULATE-PAY.
           CALL "TAXSUB" USING WS-PAY.
       SELECT EMP-FILE ASSIGN TO "EMP.DAT".
'''


def test_cobol_units():
    units = _ext("cobol", COBOL, "payroll.cob")
    by = {(u.kind, u.name) for u in units}
    assert ("cobol_program", "PAYROLL") in by
    assert any(u.kind == "cobol_section" for u in units)
    assert ("cobol_call", "TAXSUB") in by
    assert any(u.kind == "cobol_data" for u in units)       # FD / SELECT
    assert any(u.kind == "cobol_paragraph" and u.name == "CALCULATE-PAY" for u in units)
