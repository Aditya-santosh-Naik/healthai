#!/usr/bin/env bash
# HealthAI - one-command setup (macOS / Linux).
#
#     bash setup.sh
#
# Safe to re-run: every step is idempotent.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

step() { printf '\n\033[36m=== %s ===\033[0m\n' "$1"; }
ok()   { printf '\033[32m  OK  %s\033[0m\n' "$1"; }
die()  { printf '\033[31m  !!  %s\033[0m\n' "$1"; exit 1; }

step "Checking prerequisites"

command -v python3 >/dev/null || die "python3 not found. Install Python 3.11+."
pyv="$(python3 -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
python3 -c 'import sys;sys.exit(0 if sys.version_info[:2]>=(3,11) else 1)' \
  || die "Python $pyv found, but 3.11+ is required."
ok "Python $pyv"

command -v node >/dev/null || die "node not found. Install Node 18+."
ok "Node $(node --version)"

if command -v ollama >/dev/null; then
  ok "Ollama present"
else
  printf '\033[33m  --  Ollama not found. The app still runs: every AI surface has a\n'
  printf '      deterministic fallback. Install from ollama.com for the full demo.\033[0m\n'
fi

step "Backend: virtual environment"
venv_py="$root/backend/.venv/bin/python"
[ -x "$venv_py" ] || python3 -m venv "$root/backend/.venv"
"$venv_py" -m pip install --quiet --upgrade pip
ok "backend/.venv"

step "Backend: dependencies (~700 MB on first run, mostly PyTorch)"
# On Linux the default PyPI torch wheel bundles CUDA and is several GB. This
# project runs the embedder on CPU, so pull the CPU wheel first and let
# sentence-transformers resolve against it.
if [ "$(uname -s)" = "Linux" ]; then
  "$venv_py" -m pip install --quiet --index-url https://download.pytorch.org/whl/cpu torch
fi
"$venv_py" -m pip install --quiet -r "$root/backend/requirements.txt" \
  || die "pip install failed - see the output above."
ok "requirements.txt installed"

step "Backend: sanity check"
"$venv_py" -c "import torch" >/dev/null 2>&1 || die "PyTorch will not load - see the error with: $venv_py -c 'import torch'"
ok "PyTorch loads"

step "Backend: demo database"
(cd "$root/backend" && "$venv_py" seed.py)
ok "3 demo patients seeded"

step "Backend: vector index (downloads a ~130 MB embedding model once)"
(cd "$root/backend" && "$venv_py" -m rag.index)
ok "data/index.npz built"

step "Frontend: npm install"
(cd "$root/frontend" && npm install --silent)
ok "node_modules installed"

cat <<'DONE'

Setup complete. Start the two servers in separate terminals:

  cd backend  && .venv/bin/python -m uvicorn main:app --port 8000
  cd frontend && npm run dev

Then open http://localhost:5173

Demo logins - password 'demo123456' for all three:
  rajesh@example.com   48M, hypertension + diabetes, penicillin allergy
  priya@example.com    29F, GERD, NSAID allergy
  arjun@example.com    35M, vegan, smoker, self-medicating

DONE
