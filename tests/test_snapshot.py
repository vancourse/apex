"""`rails snapshot` (rails/leak.py snapshot_main): what it keeps, from how many stores.

Every value here is invented. The stores are fakes keyed by spec: each answers the three
queries of a leak.toml shaped like jarvis's (amount; descriptor min 8; booking id min 6,
needs a digit, outranks a descriptor).
"""

from __future__ import annotations

import io

import pytest

from rails import leak, store

LEAK_TOML = """
[snapshot]
store_env = "TEST_LEAK_STORE"
identity_sql = "WHO"
exclude_words = ["PAYMENTTHANKYOU"]

[[snapshot.query]]
kind = "amount"
sql = "AMOUNTS"

[[snapshot.query]]
kind = "descriptor"
min_len = 8
sql = "DESCRIPTORS"

[[snapshot.query]]
kind = "booking id"
min_len = 6
need_digit = true
rank = 1
sql = "IDS"
"""

STORES = {
    "docker://fleet-db/reader/fleet": {
        "AMOUNTS": ["4321.09"],
        "DESCRIPTORS": ["INVENTED GROCER", "12345678", "PAYMENT THANK YOU"],
        "IDS": ["90817263", "AB12CD34", "NODIGITS"],
        "WHO": ["reader (bypassrls=true)"],
    },
    "docker://local-db/postgres/working_copy": {
        "AMOUNTS": ["8765.43"],
        "DESCRIPTORS": ["ANOTHER INVENTED SHOP"],
        "IDS": ["55443322"],
        "WHO": ["postgres (bypassrls=true)"],
    },
    "postgresql://reader:hunter2secret@db.invalid:5432/empty_copy": {
        "AMOUNTS": [], "DESCRIPTORS": [], "IDS": [], "WHO": ["reader"],
    },
}


@pytest.fixture
def setup(repo, monkeypatch):
    (repo / "rails").mkdir()
    (repo / "rails" / "leak.toml").write_text(LEAK_TOML, encoding="utf-8")
    monkeypatch.setenv("TEST_LEAK_STORE", "docker://fleet-db/reader/fleet")

    def fake_fetcher(spec):
        if spec not in STORES:
            def broken(sql):
                raise RuntimeError("psql exited 2")
            return broken
        return lambda sql: list(STORES[spec][sql])

    monkeypatch.setattr(leak, "_fetcher", fake_fetcher)
    return repo, store.find_repo(repo)


def _run(top, rid, *argv):
    out = io.StringIO()
    code = leak.snapshot_main(top, rid, out=out, argv=list(argv))
    return code, out.getvalue()


def _found(rid, text):
    snap = leak.load_snapshot(rid)
    return {kind for _, _, kind, _ in leak.scan([("f.txt", 1, text)], snap)}


def test_an_all_digit_booking_id_is_kept_and_an_all_digit_descriptor_is_not(setup):
    top, rid = setup
    code, out = _run(top, rid)
    assert code == 0
    body = store.read_json(leak.snapshot_path(rid))
    assert body["counts"] == {"amount": 1, "descriptor": 1, "booking id": 2}
    assert _found(rid, "order 90817263 shipped") == {"booking id"}  # dropped by rails 1.0
    assert _found(rid, "ref AB12CD34") == {"booking id"}
    assert _found(rid, "code 12345678") == set()  # all digits: a descriptor never is one
    assert _found(rid, "PAYMENT THANK YOU") == set()  # bank vocabulary
    assert _found(rid, "NODIGITS here") == set()  # an id needs a digit
    assert _found(rid, "INVENTED GROCER #12") == {"descriptor"}


def test_several_stores_are_one_snapshot(setup):
    top, rid = setup
    code, out = _run(top, rid, "--store", "docker://local-db/postgres/working_copy")
    assert code == 0 and "from 2 store(s)" in out
    assert "fleet-db/fleet" in out and "local-db/working_copy" in out
    assert _found(rid, "paid 8,765.43") == {"amount"}  # only in the second store
    assert _found(rid, "paid 4321.09") == {"amount"}  # only in the first
    assert _found(rid, "id 55443322") == {"booking id"}
    assert "local-db/working_copy" in store.read_json(leak.snapshot_path(rid))["read_as"]


def test_remembered_stores_are_read_on_the_next_refresh_until_forgotten(setup):
    top, rid = setup
    assert _run(top, rid, "--store", "docker://local-db/postgres/working_copy", "--remember")[0] == 0
    code, out = _run(top, rid)
    assert code == 0 and "from 2 store(s)" in out
    assert _run(top, rid, "--forget")[0] == 0
    code, out = _run(top, rid)
    assert code == 0 and "from 1 store(s)" in out


def test_a_store_that_fails_or_answers_empty_writes_nothing_and_names_no_secret(setup):
    top, rid = setup
    code, out = _run(top, rid, "--store", "docker://nowhere/u/db")
    assert code == leak.EXIT_COULD_NOT_LOOK and "nowhere/db" in out
    assert leak.load_snapshot(rid) is None  # not even the store that answered
    code, out = _run(top, rid, "--store", "postgresql://reader:hunter2secret@db.invalid:5432/empty_copy")
    assert code == leak.EXIT_COULD_NOT_LOOK and "db.invalid:5432/empty_copy" in out
    assert "hunter2secret" not in out and leak.load_snapshot(rid) is None


def test_an_older_copy_without_a_newer_table_still_counts(setup, monkeypatch):
    """jarvis's local copies predate purser.booking_journeys: the other UNION part still reads."""
    top, rid = setup
    ids_sql = (
        "SELECT external_id FROM purser.purchase_documents WHERE external_id IS NOT NULL "
        "UNION SELECT external_id FROM purser.booking_journeys WHERE external_id IS NOT NULL"
    )
    toml = LEAK_TOML.replace('sql = "IDS"', f'sql = "{ids_sql}"')
    (top / "rails" / "leak.toml").write_text(toml, encoding="utf-8")
    fleet = dict(STORES["docker://fleet-db/reader/fleet"])

    def fake_fetcher(spec):
        def fetch(sql):
            if spec.endswith("old_copy") and "booking_journeys" in sql:
                raise leak.MissingRelation("purser.booking_journeys")
            if "purchase_documents" in sql:
                return ["77665544"] if spec.endswith("old_copy") else ["90817263"]
            if "booking_journeys" in sql:
                return ["AB12CD34"]
            return list(fleet[sql])
        return fetch

    monkeypatch.setattr(leak, "_fetcher", fake_fetcher)
    code, out = _run(top, rid, "--store", "docker://local-db/postgres/old_copy")
    assert code == 0, out
    assert "no purser.booking_journeys here" in out
    assert _found(rid, "order 77665544") == {"booking id"}  # the older copy's own id
    assert _found(rid, "ref AB12CD34") == {"booking id"}  # the fleet's newer table still read


def test_union_parts_splits_only_a_flat_union():
    assert leak.union_parts("SELECT a FROM t UNION SELECT b FROM u union all SELECT c FROM v") == [
        "SELECT a FROM t", "SELECT b FROM u", "SELECT c FROM v",
    ]
    nested = "SELECT a FROM (SELECT a FROM t UNION SELECT a FROM u) x"
    assert leak.union_parts(nested) == [nested]


def test_a_store_error_never_echoes_its_stderr(monkeypatch):
    """psql quotes the offending value in some errors; only a missing table is ever named."""
    import subprocess

    def fake_run(args, **kw):
        return subprocess.CompletedProcess(args, 1, "", fake_run.stderr)

    monkeypatch.setattr(leak.subprocess, "run", fake_run)
    fetch = leak._fetcher("docker://fleet-db/reader/fleet")
    fake_run.stderr = 'ERROR:  invalid input syntax for type numeric: "4321.09"'
    with pytest.raises(RuntimeError) as err:
        fetch("SELECT 1")
    assert not isinstance(err.value, leak.MissingRelation) and "4321.09" not in str(err.value)
    fake_run.stderr = 'ERROR:  relation "purser.booking_journeys" does not exist\nLINE 1: SELECT'
    with pytest.raises(leak.MissingRelation) as err:
        fetch("SELECT 1")
    assert err.value.name == "purser.booking_journeys"


def test_it_refuses_inside_an_agent(setup, monkeypatch):
    top, rid = setup
    monkeypatch.setenv("CLAUDECODE", "1")
    code, out = _run(top, rid)
    assert code == leak.EXIT_USAGE and "YOUR shell" in out and leak.load_snapshot(rid) is None


def test_no_store_at_all_says_how_to_name_one(setup, monkeypatch):
    top, rid = setup
    monkeypatch.delenv("TEST_LEAK_STORE")
    code, out = _run(top, rid)
    assert code == leak.EXIT_USAGE and "TEST_LEAK_STORE" in out and "--store" in out
