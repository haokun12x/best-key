"""Remove dangling tracks and vias reported by KiCad DRC, repeat until none are left.

usage: tools/kpy.sh tools/clean_dangling.py board.kicad_pcb
(each round reloads the board in a fresh process; pcbnew does not like a second LoadBoard)
"""
import json
import os
import subprocess
import sys

import pcbnew

PCB = sys.argv[1]
CLI = os.path.expanduser('~/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli')
REP = os.path.join(os.path.dirname(os.path.abspath(PCB)), 'drc_clean.json')
total = 0
if len(sys.argv) > 2:          # child: one round
    rnd = int(sys.argv[2])
else:
    for rnd in range(20):
        r = subprocess.run([sys.executable, __file__, PCB, str(rnd)], capture_output=True, text=True)
        n = [l for l in r.stdout.splitlines() if l.startswith('removed ')]
        k = int(n[-1].split()[1]) if n else 0
        print('round', rnd, 'removed', k)
        total += k
        if not k:
            break
    print('removed in total', total)
    sys.exit(0)
for _ in range(1):
    subprocess.run([CLI, 'pcb', 'drc', '--format', 'json', '--severity-all', '-o', REP, PCB], capture_output=True)
    d = json.load(open(REP))
    bad = set()
    for v in d.get('violations', []):
        if v['type'] in ('track_dangling', 'via_dangling'):
            for i in v['items']:
                bad.add(i['uuid'])
    if not bad:
        print('removed 0')
        break
    b = pcbnew.LoadBoard(PCB)
    n = 0
    for t in list(b.GetTracks()):
        if t.m_Uuid.AsString() in bad:
            b.Remove(t)
            n += 1
    total += n
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(PCB, b)
    print('removed', n)
os.remove(REP)
