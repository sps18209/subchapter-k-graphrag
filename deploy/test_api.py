"""
test_api.py — exercises every endpoint through FastAPI's TestClient.
Run: python test_api.py
"""

from __future__ import annotations

import os
from fastapi.testclient import TestClient

import app as appmod

PASS = 0


def check(name, cond):
    global PASS
    assert cond, f"FAIL: {name}"
    PASS += 1
    print(f"  ok  {name}")


with TestClient(appmod.app) as client:
    # health -------------------------------------------------------------------
    r = client.get("/health").json()["data"]
    check("health status ok", r["status"] == "ok")
    check("graph has nodes", r["nodes"] > 100)
    check("graph integrity clean", r["integrity_problems"] == 0)

    # ask ----------------------------------------------------------------------
    d = client.post("/ask", json={"question": "what feeds outside basis"}).json()["data"]
    check("ask returns results", len(d["results"]) > 0)
    check("ask flags verification_required", d["verification_required"] is True)
    check("ask carries disclaimer", "attorney review" in d["disclaimer"])
    check("ask detects computation", d["is_computation"] is True)
    check("ask surfaces computed-term DAG", len(d["computed_terms"]) > 0
          and len(d["computed_terms"][0]["dag"]) > 0)

    d = client.post("/ask", json={"question": "disguised sale with a liability",
                                   "as_of": "2016-06-01"}).json()["data"]
    check("ask echoes as_of", d["as_of"] == "2016-06-01")

    # compute: the two IRS LB&I worked examples --------------------------------
    joe = client.post("/compute", json={"beginning_basis": 245000,
                                         "cash_distributed": 465000}).json()["data"]
    check("compute Joe §731(a) gain = 220000", joe["sec731a_gain"] == 220000)
    check("compute Joe ending basis = 0", joe["ending_basis"] == 0)
    check("compute returns trace", len(joe["trace"]) >= 4)

    sally = client.post("/compute", json={"beginning_basis": 45000,
                                           "losses": 125000}).json()["data"]
    check("compute Sally §704(d) allowed = 45000", sally["sec704d_loss_allowed"] == 45000)
    check("compute Sally §704(d) suspended = 80000", sally["sec704d_loss_suspended"] == 80000)

    # verify: currency chain ---------------------------------------------------
    v2026 = client.get("/verify", params={"as_of": "2026-06-01"}).json()["data"]
    check("verify 2026 reports superseded authority",
          any("2024-14" in x["citation"] for x in v2026["superseded"]))
    v2016 = client.get("/verify", params={"as_of": "2016-06-01"}).json()["data"]
    check("verify 2016 flags not-yet-effective", len(v2016["not_yet_effective"]) > 0)

    # hubs + node --------------------------------------------------------------
    hubs = client.get("/hubs").json()["data"]
    check("hubs non-empty", len(hubs) > 0)
    computed = [h for h in hubs if h["computed"]]
    check("at least one computed hub", len(computed) > 0)

    hub_id = computed[0]["id"]
    hd = client.get(f"/hubs/{hub_id}").json()["data"]
    check("computed hub has a DAG", hd["dag"] is not None and len(hd["dag"]["steps"]) > 0)
    check("hub lists connected authority", len(hd["connected"]) > 0)

    nd = client.get(f"/node/{hub_id}").json()["data"]
    check("node returns edges", len(nd["edges"]) > 0)

    # validation + 404 ---------------------------------------------------------
    bad = client.post("/ask", json={"question": "x", "as_of": "not-a-date"})
    check("bad date -> 400", bad.status_code == 400)
    check("404 on unknown hub", client.get("/hubs/nope").status_code == 404)
    check("404 on unknown node", client.get("/node/nope").status_code == 404)
    check("422 on missing question", client.post("/ask", json={}).status_code == 422)

    # auth ---------------------------------------------------------------------
    os.environ["SUBK_API_KEYS"] = "firm:secret123"
    try:
        check("no key -> 401", client.get("/hubs").status_code == 401)
        check("x-api-key -> 200",
              client.get("/hubs", headers={"X-API-Key": "secret123"}).status_code == 200)
        check("bearer -> 200",
              client.get("/hubs", headers={"Authorization": "Bearer secret123"}).status_code == 200)
        check("wrong key -> 401",
              client.get("/hubs", headers={"X-API-Key": "nope"}).status_code == 401)
        check("health stays open (no auth)", client.get("/health").status_code == 200)
    finally:
        del os.environ["SUBK_API_KEYS"]

print(f"\nALL {PASS} API CHECKS PASS")
