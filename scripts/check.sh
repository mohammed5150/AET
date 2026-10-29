#!/usr/bin/env bash
# Run the same gate as .github/workflows/ci.yml, in the same order.
# Usage: scripts/check.sh   (from any directory, with the dev install active)
set -euo pipefail
cd "$(dirname "$0")/.."

step() { printf '\n== %s\n' "$1"; }

step "ruff";   ruff check .
step "black";  black --check .
step "mypy";   mypy
step "pytest"; pytest -q --cov=aet --cov-report=term-missing:skip-covered
step "cli";    aet version

printf '\nAll checks passed.\n'
