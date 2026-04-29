---
skill_name: "gwdg_slurm_scripts"
description: "GWDG cluster Slurm partitions and sane sbatch defaults"
frameworks:
  - openhands
  - goose
  - opencode
---

# GWDG Slurm snippets (grete and friends)

- Prefer partition **`grete`** for CPU batch work; **`grete:interactive`** exists for short debugging sessions. Always pass explicit **`--time`** / **`--cpus-per-task`** — interactive defaults are tight.
- Job names: use `-J meaningful-name` so queue (`squeue -u $USER`) stays readable.
- Resource asks: start from **1 node, 1–4 CPUs, 1–4 GB RAM** unless you know the workload needs more; scale up with measured data.
- Output files: `-o /workspace/logs/%x-%j.out` (create `logs/` first with `fs_write` or a single `mkdir -p` via `code_exec` if policy allows).
- Never embed secrets in the script body; use environment variables already injected by the broker or read from files under allowed paths.

When unsure, call `fs_read` on an existing working example in `/workspace` before inventing new flags.
