#!/bin/sh
# usage: drc.sh board.kicad_pcb  -> writes drc.json next to it and prints a summary
K="$HOME/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
D=$(dirname "$1")
"$K" pcb drc --format json --severity-all -o "$D/drc.json" "$1" >/dev/null 2>&1
python3 - "$D/drc.json" <<'PY'
import json,collections,sys,re
d=json.load(open(sys.argv[1]))
c=collections.Counter((v['type'],v['severity']) for v in d.get('violations',[]))
for k,v in c.most_common(): print('%4d %s (%s)'%(v,k[0],k[1]))
u=d.get('unconnected_items',[])
cn=collections.Counter()
for x in u:
    m=re.search(r'\[([^\]]+)\]',x['items'][0]['description']); cn[m.group(1) if m else '?']+=1
print('unconnected items:',len(u), dict(cn.most_common(40)))
PY
