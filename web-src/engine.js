/* engine.js — browser port of the Subchapter K GraphRAG engine.
   Mirrors retrieve.py / calculator.py / graph.py. ISO date strings compare
   lexicographically, which is equivalent to the Python date comparisons. */
(function (root) {
  "use strict";

  function tokenize(s) { return (s.toLowerCase().match(/[a-z0-9]+/g)) || []; }
  function round2(x) { return Math.round((x + Number.EPSILON) * 100) / 100; }

  function buildGraph(data) {
    const nodes = data.nodes, edges = data.edges;
    const byId = {}; nodes.forEach(n => byId[n.id] = n);
    const adj = {}; nodes.forEach(n => adj[n.id] = []);
    edges.forEach(e => { if (adj[e.s]) adj[e.s].push(e); if (adj[e.d]) adj[e.d].push(e); });

    // BM25 over node text
    const ids = nodes.map(n => n.id);
    const docs = {}, tok = {}, dl = {}; let total = 0;
    nodes.forEach(n => {
      docs[n.id] = [n.citation, n.label, n.syn || "", (n.tags || []).join(" "),
                    n.id.replace(/_/g, " ")].join(" ");
    });
    ids.forEach(i => { const t = tokenize(docs[i]); tok[i] = t; dl[i] = t.length; total += t.length; });
    const avgdl = total / Math.max(1, ids.length);
    const df = {}; ids.forEach(i => { new Set(tok[i]).forEach(t => df[t] = (df[t] || 0) + 1); });
    const N = ids.length;
    const idf = t => { const n = df[t] || 0; return Math.log(1 + (N - n + 0.5) / (n + 0.5)); };
    function score(query, i) {
      const tf = {}; tok[i].forEach(t => tf[t] = (tf[t] || 0) + 1);
      let s = 0; const k1 = 1.5, b = 0.75;
      tokenize(query).forEach(t => { if (tf[t]) s += idf(t) * (tf[t] * (k1 + 1)) / (tf[t] + k1 * (1 - b + b * dl[i] / avgdl)); });
      return s;
    }
    function topk(query, k) {
      const sc = ids.map(i => [score(query, i), i]).filter(x => x[0] > 0)
        .sort((a, b) => (b[0] - a[0]) || (a[1] > b[1] ? -1 : 1));
      return sc.slice(0, k);
    }
    return { nodes, edges, byId, adj, bm25: { score, topk } };
  }

  function supersededBy(g, id) {
    const e = g.adj[id].find(e => e.d === id && e.t === "supersedes");
    return e ? [e.s, g.byId[e.s].vf] : null;
  }

  function applicable(g, id, asOf) {
    if (!asOf) return true;
    const n = g.byId[id];
    if (n.vf && asOf < n.vf) return false;
    if (n.vt && asOf > n.vt) return false;
    const sup = supersededBy(g, id);
    if (sup && sup[1] && asOf >= sup[1]) return false;
    return true;
  }

  function isComputation(q) {
    return q.toLowerCase().includes("basis") &&
      /\b(comput|calculat|figure|how much|what.+basis|ending basis|gain|suspend)/i.test(q);
  }

  function retrieve(g, question, asOf, topN, seedK) {
    topN = topN || 16; seedK = seedK || 8;
    const seeds = g.bm25.topk(question, seedK).map(x => x[1]);

    const visited = new Set(seeds); let frontier = seeds.slice();
    for (let h = 0; h < 2; h++) {
      const nxt = [];
      frontier.forEach(id => g.adj[id].forEach(e => {
        const o = e.s === id ? e.d : e.s;
        if (!visited.has(o)) { visited.add(o); nxt.push(o); }
      }));
      frontier = nxt;
    }
    Array.from(visited).forEach(id => {
      const n = g.byId[id];
      if (n && n.ntype === "term" && n.sub === "computed")
        g.adj[id].forEach(e => visited.add(e.s === id ? e.d : e.s));
    });

    const prot = new Set();
    seeds.forEach(sid => {
      const sn = g.byId[sid];
      if (sn && sn.ntype === "term" && sn.sub === "computed")
        g.adj[sid].forEach(e => {
          if (e.d === sid && ["computes", "adjusts", "uses"].includes(e.t)) prot.add(e.s);
          if (e.s === sid && e.t === "overflow") prot.add(e.d);
        });
    });
    const relOf = id => g.bm25.score(question, id) + (prot.has(id) ? 5 : 0);

    const cand = [], excluded = [];
    visited.forEach(id => {
      if (applicable(g, id, asOf)) cand.push(id);
      else { const n = g.byId[id]; excluded.push([n.citation, n.vf, n.vt]); }
    });
    const candSet = new Set(cand);

    const seen = new Set(), mustOrder = [];
    seeds.concat(Array.from(prot).sort()).forEach(id => { if (!seen.has(id)) { seen.add(id); mustOrder.push(id); } });
    const must = mustOrder.filter(id => candSet.has(id));
    const mustSet = new Set(must);
    // node id is the final tiebreak so truncation is deterministic and identical to the
    // Python engine (retrieve.py), independent of Set/dict iteration order.
    const byIdAsc = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
    const others = cand.filter(id => !mustSet.has(id))
      .sort((a, b) => (g.byId[a].tier - g.byId[b].tier) || (relOf(b) - relOf(a)) || byIdAsc(a, b));
    const keep = must.slice();
    for (const id of others) { if (keep.length >= topN) break; keep.push(id); }

    const results = keep.map(id => [g.byId[id], relOf(id)])
      .sort((x, y) => (x[0].tier - y[0].tier) || (y[1] - x[1]) || byIdAsc(x[0].id, y[0].id));
    const computedHubs = results.filter(r => r[0].ntype === "term" && r[0].sub === "computed").map(r => r[0]);
    return { question, asOf, results, seeds, excluded, computedHubs, isComputation: isComputation(question) };
  }

  // Ordered inbound computation edges for a computed-term hub + member ids.
  function dag(g, hubId) {
    const rows = [], members = new Set();
    g.adj[hubId].forEach(e => {
      if (e.d === hubId && ["computes", "adjusts", "uses"].includes(e.t)) {
        members.add(e.s);
        rows.push({ seq: e.seq == null ? 99 : e.seq, grp: e.grp || "-", dir: e.dir || "-",
                    cite: g.byId[e.s].citation, m: e.m });
      }
      if (e.s === hubId && e.t === "overflow") members.add(e.d);
    });
    // Sort the full row (seq, grp, dir, cite, mechanism) to match retrieve._dag's tuple
    // sort in Python, so seq-tied constraint rows order identically in both engines.
    const c = (x, y) => (x < y ? -1 : x > y ? 1 : 0);
    rows.sort((a, b) => (a.seq - b.seq) || c(a.grp, b.grp) || c(a.dir, b.dir) || c(a.cite, b.cite) || c(a.m, b.m));
    const overflow = g.adj[hubId].filter(e => e.s === hubId && e.t === "overflow")
      .map(e => g.byId[e.d].citation + " (" + e.m + ")");
    return { rows, overflow, members };
  }

  function computeBasis(input) {
    const d = Object.assign({
      beginning_basis: 0, cash_contributed: 0, property_contributed_basis: 0, liability_increase: 0,
      income_taxable: 0, income_tax_exempt: 0, depletion_excess: 0, cash_distributed: 0,
      property_distributed_basis: 0, liability_decrease: 0, nondeductible: 0, oil_gas_depletion: 0, losses: 0
    }, input);
    const trace = [["A. Beginning basis", d.beginning_basis, d.beginning_basis]];
    const inc = d.cash_contributed + d.property_contributed_basis + d.liability_increase +
                d.income_taxable + d.income_tax_exempt + d.depletion_excess;
    let b = d.beginning_basis + inc;
    trace.push(["B. + increases  [\u00A7722, \u00A7752(a), \u00A7705(a)(1)]", inc, b]);
    const dist = d.cash_distributed + d.property_distributed_basis + d.liability_decrease;
    const gain = Math.max(0, dist - b); b = Math.max(0, b - dist);
    trace.push(["C. \u2212 distributions  [\u00A7733, \u00A7752(b)] (floor 0)", -dist, b]);
    const red = d.nondeductible + d.oil_gas_depletion; b = Math.max(0, b - red);
    trace.push(["D. \u2212 nondeductible / depletion  [\u00A7705(a)(2)(B),(a)(3)] (floor 0)", -red, b]);
    const lossAllowed = Math.min(d.losses, b), lossSusp = d.losses - lossAllowed; b = b - lossAllowed;
    trace.push(["E. \u2212 loss allowed  [\u00A7704(d) limit]", -lossAllowed, b]);
    return {
      ending: round2(b), gain: round2(gain), lossAllowed: round2(lossAllowed),
      lossSuspended: round2(lossSusp), trace,
      authorities: ["IRC 722", "IRC 742", "IRC 752", "IRC 705", "IRC 733", "IRC 704(d)", "IRC 731(a)"]
    };
  }

  function currencyReport(g, asOf) {
    const inForce = [], notYet = [], expired = [], superseded = [], seen = new Set();
    g.nodes.forEach(n => {
      if (!(n.vf || n.vt)) return;
      seen.add(n.id);
      const sup = supersededBy(g, n.id);
      if (n.vf && asOf < n.vf) notYet.push([n.citation, "effective " + n.vf]);
      else if (n.vt && asOf > n.vt) expired.push([n.citation, "removed " + n.vt]);
      else if (sup && sup[1] && asOf >= sup[1]) superseded.push([n.citation, "superseded by " + g.byId[sup[0]].citation]);
      else inForce.push([n.citation, "in force"]);
    });
    new Set(g.edges.filter(e => e.t === "supersedes").map(e => e.d)).forEach(id => {
      if (seen.has(id)) return;
      const sup = supersededBy(g, id), c = g.byId[id].citation;
      if (sup && sup[1] && asOf >= sup[1]) superseded.push([c, "superseded by " + g.byId[sup[0]].citation]);
      else inForce.push([c, "in force"]);
    });
    return { asOf, inForce, notYet, expired, superseded };
  }

  const API = { buildGraph, retrieve, dag, computeBasis, currencyReport, applicable, supersededBy, tokenize };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  root.SubK = API;
})(typeof window !== "undefined" ? window : globalThis);
