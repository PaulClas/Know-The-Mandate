import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from kym import config, scenarios, schemas

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("sid", [c["id"] for c in scenarios.CATALOG])
def test_every_demonstration_scenario_passes_against_the_real_engine(client, sid):
    r = scenarios.run(sid)
    assert r["passed"], [s for s in r["steps"] if not s["ok"]]


def test_scenarios_repeat_cleanly_on_the_same_database(client):
    for sid in ("B", "J", "H"):
        assert scenarios.run(sid)["passed"]


def test_alembic_migration_matches_models():
    from sqlalchemy import create_engine, inspect

    from kym import db

    tmp = tempfile.mkdtemp()
    env = {**os.environ, "KYM_DATA_DIR": tmp}
    env.pop("KYM_DATABASE_URL", None)
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT / "apps" / "api", env={**env, "PYTHONPATH": str(ROOT / "apps" / "api")}, check=True, capture_output=True)
    insp = inspect(create_engine(f"sqlite:///{tmp}/kym.db"))
    tables = set(insp.get_table_names()) - {"alembic_version"}
    assert tables == set(db.Base.metadata.tables)
    for name, table in db.Base.metadata.tables.items():  # columns too: a model change without a migration must fail here
        assert {c["name"] for c in insp.get_columns(name)} == set(table.columns.keys()), name


def test_committed_json_schema_is_current():
    committed = json.loads((config.PACKAGES / "mandate-schema" / "mandate.schema.json").read_text())
    assert committed == json.loads(json.dumps(schemas.mandate_json_schema(), sort_keys=True))


def test_json_schema_accepts_valid_and_rejects_invalid_mandate():
    import jsonschema
    from helpers import make_mandate

    schema = schemas.mandate_json_schema()
    jsonschema.validate(make_mandate(), schema)
    bad = make_mandate()
    bad["permissions"][1]["constraints"]["maximum_amount_minor"] = 12.5
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
