#!/bin/sh
# Finish the main board: patch-route the unconnected nets, drop dangling copper, repeat.
# usage: tools/finish_main.sh in.kicad_pcb out_dir      (out_dir gets bk46_main.kicad_pcb + .kicad_pro)
set -e
T=$(cd "$(dirname "$0")" && pwd)
IN=$1; OUT=$2
mkdir -p "$OUT"
B="$OUT/bk46_main.kicad_pcb"
cp "$IN" "$B"
PRO() { python3 "$T/write_pro.py" "$OUT/bk46_main.kicad_pro" 0.10 0.25 0.45 0.2; }
PRO
NETS="+3V3,LED_EN,CHG,VLED"
for pass in 1 2 3 4 5; do
  echo "== pass $pass: $NETS"
  "$T/kpy.sh" -u "$T/patch_route.py" "$B" "$B" "$NETS" 2>&1 | grep -v "assert\|leak\|Debug" | grep -v "^routed"
  PRO
  "$T/kpy.sh" "$T/clean_dangling.py" "$B" 2>&1 | grep "total"
  PRO
  "$T/drc.sh" "$B"
  NETS=$(python3 -c "
import json,re
d=json.load(open('$OUT/drc.json'))
s=sorted({re.search(r'\[([^\]]+)\]',i['description']).group(1) for v in d['unconnected_items'] for i in v['items']})
print(','.join(s))")
  [ -z "$NETS" ] && { echo "all connected"; break; }
done
