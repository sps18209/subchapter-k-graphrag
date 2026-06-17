#!/usr/bin/env python3
"""Regenerate ../web-src/data.json from the graph, so the demo's corpus never drifts
from the Python system. Run from the python/ folder:  python export_web_data.py
"""
import json
import os
import graph

con = graph.build(":memory:")
nodes = [dict(id=r[0], ntype=r[1], citation=r[2], label=r[3], tier=r[4], sub=r[5],
              syn=r[6], tags=(r[7].split("|") if r[7] else []), vf=r[8], vt=r[9])
         for r in con.execute("SELECT id,ntype,citation,label,tier,term_subtype,"
                              "synthesis,tags,valid_from,valid_to FROM node")]
edges = [dict(s=r[0], d=r[1], t=r[2], dir=r[3], seq=r[4], grp=r[5], m=r[6])
         for r in con.execute("SELECT src,dst,etype,direction,seq,grp,mechanism FROM edge")]

dest = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web-src", "data.json")
json.dump(dict(nodes=nodes, edges=edges), open(dest, "w"))
print(f"wrote {dest} ({len(nodes)} nodes, {len(edges)} edges)")
