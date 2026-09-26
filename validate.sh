#!/usr/bin/env bash
# 对钉住的 ref 跑对方 check.py、run.sh，以及 graph init + topo。
# validate.sh --repo <high repo> --chapter chem-bx1-ch1 [--target high-school-ai-tutor]
set -euo pipefail
root="$(cd "$(dirname "$0")" && pwd)"
if [ -n "${VIRTUAL_ENV:-}" ] && [ -x "$VIRTUAL_ENV/bin/python" ]; then
  PY="$VIRTUAL_ENV/bin/python"
elif [ -x "$HOME/.venvs/kb-pipeline/bin/python" ]; then
  PY="$HOME/.venvs/kb-pipeline/bin/python"
else
  PY=python3
fi
exec "$PY" "$root/core/validate.py" --pipeline-root "$root" "$@"
