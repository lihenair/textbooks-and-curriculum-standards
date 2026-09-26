#!/usr/bin/env bash
# 对钉住的 ref 跑对方 check.py、run.sh，以及 graph init + topo。
# validate.sh --repo <high repo> --chapter chem-bx1-ch1 [--target high-school-ai-tutor]
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$root/core/validate.py" --pipeline-root "$root" "$@"
