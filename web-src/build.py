#!/usr/bin/env python3
"""Rebuild the self-contained index.html from the template, engine, and data.

Inlines web-src/engine.js and web-src/data.json into web-src/index.template.html
and writes the result to ../index.html. Run from anywhere:  python web-src/build.py
"""
import os

here = os.path.dirname(os.path.abspath(__file__))
tpl = open(os.path.join(here, "index.template.html")).read()
engine = open(os.path.join(here, "engine.js")).read()
data = open(os.path.join(here, "data.json")).read()

out = tpl.replace("/*__ENGINE__*/", engine).replace("/*__DATA__*/", data)
dest = os.path.join(os.path.dirname(here), "index.html")
open(dest, "w").write(out)
print(f"wrote {dest} ({len(out)//1024} KB, self-contained)")
