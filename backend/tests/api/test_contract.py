"""AD-19: the committed contract the frontend client is generated from matches the live API.

CI also regenerates the client and fails on any diff (ci-pipeline); this catches drift locally.
"""

import json
from pathlib import Path

from ninja.responses import NinjaJSONEncoder

from config.api import api

COMMITTED_SCHEMA = Path(__file__).resolve().parents[3] / "frontend/lib/api/openapi.json"


def test_committed_openapi_schema_matches_the_live_api():
    assert COMMITTED_SCHEMA.exists(), f"{COMMITTED_SCHEMA} is missing: run `make client`"
    live = json.loads(json.dumps(api.get_openapi_schema(), cls=NinjaJSONEncoder))
    committed = json.loads(COMMITTED_SCHEMA.read_text())

    assert committed == live, "The API changed: run `make client` and commit lib/api/"
