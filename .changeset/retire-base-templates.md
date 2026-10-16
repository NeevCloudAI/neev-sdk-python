---
"neevai": patch
---

Examples, docs and tests use the `sb-ubuntu-26-04-dev` template, which ships `bash`, `python3` and `node`, in place of the minimal templates that are no longer offered. A new `examples/docker.py` runs a container from the `sb-ubuntu-26-04-docker` template. The template docs cover the `interpreter` and `min_memory_gb` fields and recommend `templates.list()` over hard-coded template ids.
