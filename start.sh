#!/usr/bin/env bash
# Reopen the installed PIA on Linux or native Windows (Git Bash).
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
case "${OSTYPE:-$(uname -s)}" in
  msys*|cygwin*|MINGW*) PYTHON="$ROOT/.venv/Scripts/python.exe" ;;
  linux*|Linux*) PYTHON="$ROOT/.venv/bin/python" ;;
  *) printf 'Sistema não suportado.\n' >&2; exit 1 ;;
esac
if [[ ! -f "$PYTHON" ]]; then
  printf 'PIA ainda não instalada. Execute: bash install.sh\n' >&2
  exit 1
fi
exec "$PYTHON" -m src.launcher "$@"
