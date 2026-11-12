#!/bin/sh
# try several routing orders; each result goes to pcb/try_<seed>/ ; prints the number of failed connections
cd "$(dirname "$0")/.."
for s in "$@"; do
  SEED=$s OUTDIR=try_$s tools/kpy.sh pcb/gen_main.py 2>/dev/null | grep -E "^FAILED" | sed "s/^/seed $s /"
done
