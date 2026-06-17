#!/usr/bin/env node
/* parity_runner.js — run the browser engine (engine.js) over a battery of cases and
   emit normalized JSON, so python/parity_test.py can assert byte-for-byte agreement
   with the authoritative Python engine. Reads a cases JSON file (path in argv[2]),
   writes the normalized results array to stdout. Pure Node, no deps.

   Normalization here MUST match python/parity_test.py exactly. */
"use strict";
const fs = require("fs");
const path = require("path");

const SubK = require("./engine.js");
const data = JSON.parse(fs.readFileSync(path.join(__dirname, "data.json"), "utf8"));
const g = SubK.buildGraph(data);

const r6 = x => Math.round((x + Number.EPSILON) * 1e6) / 1e6;
// Order-independent comparison for unordered buckets: normalize null -> "" and sort
// element-wise (NOT on a joined string — a separator can collide with cell content).
// Must match _sorted_rows in python/parity_test.py exactly.
const normRow = row => row.map(v => (v === null || v === undefined ? "" : String(v)));
const cmpRow = (x, y) => {
  const a = normRow(x), b = normRow(y), n = Math.max(a.length, b.length);
  for (let i = 0; i < n; i++) { const av = a[i] ?? "", bv = b[i] ?? ""; if (av < bv) return -1; if (av > bv) return 1; }
  return 0;
};
const sortRows = arr => arr.map(normRow).sort(cmpRow);

function run(c) {
  if (c.type === "retrieve") {
    const out = SubK.retrieve(g, c.question, c.as_of);
    return {
      type: "retrieve", question: c.question, as_of: c.as_of || null,
      results: out.results.map(([n, rel]) => [n.citation, n.tier, r6(rel)]),
      seeds: out.seeds.slice(),
      excluded: sortRows(out.excluded.map(e => [e[0], e[1], e[2]])),
      computed_hubs: out.computedHubs.map(n => n.citation),
      is_computation: out.isComputation,
    };
  }
  if (c.type === "compute") {
    const out = SubK.computeBasis(c.inputs);
    return {
      type: "compute", inputs: c.inputs,
      ending: r6(out.ending), gain: r6(out.gain),
      loss_allowed: r6(out.lossAllowed), loss_suspended: r6(out.lossSuspended),
    };
  }
  if (c.type === "currency") {
    const out = SubK.currencyReport(g, c.as_of);
    return {
      type: "currency", as_of: c.as_of,
      in_force: sortRows(out.inForce), not_yet: sortRows(out.notYet),
      expired: sortRows(out.expired), superseded: sortRows(out.superseded),
    };
  }
  if (c.type === "dag") {
    const out = SubK.dag(g, c.hub);
    return {
      type: "dag", hub: c.hub,
      rows: out.rows.map(rw => [rw.seq, rw.grp, rw.dir, rw.cite, rw.m]),
      overflow: out.overflow.slice(),
    };
  }
  if (c.type === "applicable") {
    return { type: "applicable", id: c.id, as_of: c.as_of,
             value: SubK.applicable(g, c.id, c.as_of) };
  }
  throw new Error("unknown case type: " + c.type);
}

const cases = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
process.stdout.write(JSON.stringify(cases.map(run)));
