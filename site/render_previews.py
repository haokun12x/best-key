"""Landscape line-art previews for index.html, from the exported STEP files.
usage: .venv/bin/python site/render_previews.py"""
import os, cadquery as cq
M = 'mech/out'; O = 'site/render'
def load(n): return cq.importers.importStep(os.path.join(M, n + '.step'))
def exp(shape, name, d, w=1600, h=640):
    cq.exporters.export(shape, os.path.join(O, name + '.svg'),
        opt={'projectionDir': d, 'width': w, 'height': h, 'showAxes': False, 'showHidden': False,
             'strokeColor': (40, 40, 40), 'strokeWidth': -1})
for n, d in (('tub', (-1, -0.45, 0.7)), ('bezel', (-1, -0.45, 0.7)), ('plate', (-1, -0.001, 3))):
    exp(load(n), n, d)
parts = [load(n) for n in ('tub', 'bezel', 'plate')]
w = parts[0]
for p in parts[1:]: w = w.union(p)
exp(w, 'assembly', (-1, -0.45, 0.7), 1600, 700)
