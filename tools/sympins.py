"""Extract pin number->name tables from KiCad symbol libraries (handles 'extends')."""
import re, sys, os
SYM = os.path.expanduser('~/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols')

def _blocks(text, start_pat):
    for m in re.finditer(start_pat, text):
        i = m.start(); depth = 0; j = i
        while j < len(text):
            ch = text[j]
            if ch == '(': depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0: break
            j += 1
        yield m, text[i:j+1]

def _read_lib(lib):
    p = os.path.join(SYM, lib + '.kicad_sym')
    if os.path.isdir(p.replace('.kicad_sym','.kicad_symdir')):
        return None
    return open(p).read()

def symbol(lib, name):
    d = os.path.join(SYM, lib + '.kicad_symdir')
    if os.path.isdir(d):
        text = open(os.path.join(d, name + '.kicad_sym')).read()
        getter = lambda n: open(os.path.join(d, n + '.kicad_sym')).read()
    else:
        text = open(os.path.join(SYM, lib + '.kicad_sym')).read()
        getter = lambda n: text
    def find(n, t):
        for m, b in _blocks(t, r'\(symbol "%s"' % re.escape(n)):
            return b
        raise KeyError(n)
    blk = find(name, text)
    props = dict(re.findall(r'\(property "([^"]+)" "([^"]*)"', blk))
    ext = re.search(r'\(extends "([^"]+)"\)', blk)
    base = blk
    if ext:
        base = find(ext.group(1), getter(ext.group(1)))
    pins = {}
    for m, b in _blocks(base, r'\(pin [a-z_]+ [a-z_]+'):
        nm = re.search(r'\(name "([^"]*)"', b).group(1)
        num = re.search(r'\(number "([^"]*)"', b).group(1)
        pins[num] = nm
    return props, pins

if __name__ == '__main__':
    for a in sys.argv[1:]:
        lib, name = a.split(':')
        props, pins = symbol(lib, name)
        print('==', a, '| fp:', props.get('Footprint'), '|', props.get('Description', props.get('ki_description',''))[:90])
        def k(x):
            m = re.match(r'(\d+)', x); return (0, int(m.group(1))) if m else (1, x)
        print('  ' + ', '.join('%s=%s' % (n, pins[n]) for n in sorted(pins, key=k)))
