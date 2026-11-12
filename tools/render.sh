#!/bin/sh
# usage: render.sh board.kicad_pcb out_prefix "F.Cu,B.Cu,Edge.Cuts"  -> PNG via quicklook
K="$HOME/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"
"$K" pcb export svg --layers "$3" --mode-single --page-size-mode 2 --exclude-drawing-sheet -o "$2.svg" "$1" >/dev/null 2>&1
qlmanage -t -s ${4:-2400} -o "$(dirname $2)" "$2.svg" >/dev/null 2>&1
