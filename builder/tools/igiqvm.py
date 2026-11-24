"""IGI 2 QVM (LOOP v8.7) <-> QSC decompiler / compiler.

Covers the statement subset used by mission data files (objects.qvm, mission.qvm,
config files): top-level function-call statements whose arguments are literal
ints / floats / strings / identifiers, unary minus, and nested calls.

Opcodes (v8): 0 BRK 3 BRA 7 CALL 8 PUSH(i32) 9 PUSHB 0a PUSHW 0b PUSHF
0d PUSHS 0e PUSHSI 0f PUSHSIB 10 PUSHSIW 11 PUSHI 12 PUSHII 13 PUSHIIB 14 PUSHIIW
15 PUSH0 16 PUSH1 18 POP 2c MINUS
"""
import struct, re, sys

OPN = {0x00: 'BRK', 0x01: 'NOP', 0x02: 'RET', 0x03: 'BRA', 0x04: 'BF', 0x05: 'BT', 0x06: 'JSR', 0x07: 'CALL',
       0x08: 'PUSH', 0x09: 'PUSHB', 0x0a: 'PUSHW', 0x0b: 'PUSHF', 0x0c: 'PUSHA', 0x0d: 'PUSHS', 0x0e: 'PUSHSI',
       0x0f: 'PUSHSIB', 0x10: 'PUSHSIW', 0x11: 'PUSHI', 0x12: 'PUSHII', 0x13: 'PUSHIIB', 0x14: 'PUSHIIW',
       0x15: 'PUSH0', 0x16: 'PUSH1', 0x17: 'PUSHM', 0x18: 'POP', 0x2c: 'MINUS'}


class Int(int): pass
class Flt(float): pass
class Str(str): pass
class Ident(str): pass
class Neg:
    def __init__(s, e): s.e = e
class Call:
    def __init__(s, name, args): s.name, s.args = name, args


def f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]


def fmt_float(x):
    for p in range(1, 18):
        s = '%.*g' % (p, x)
        if f32(float(s)) == f32(x):
            break
    if not re.search(r'[.eEn]', s):
        s += '.0'
    return s


# ---------------------------------------------------------------- read
def read_qvm(data):
    if data[:4] != b'LOOP':
        raise ValueError('not a QVM')
    h = struct.unpack('<4s12I', data[:52])
    ver = h[1:3]
    symT, symD, symTS, symDS, strT, strD, strTS, strDS, code, codesz = h[3:13]

    def table(t, ts, d):
        out = []
        for o in struct.unpack('<%dI' % (ts // 4), data[t:t + ts]):
            e = data.index(b'\0', d + o)
            out.append(data[d + o:e].decode('latin1'))
        return out
    return ver, table(symT, symTS, symD), table(strT, strTS, strD), data[code:code + codesz]


class Decoder:
    def __init__(s, syms, strs, code):
        s.syms, s.strs, s.c = syms, strs, code

    def u(s, fmt, p):
        return struct.unpack_from(fmt, s.c, p)[0]

    def expr(s, p, stop):
        """evaluate a straight-line expression program from p; returns (expr, p_after_terminator)"""
        st = []
        c = s.c
        while True:
            op = c[p]
            if op == 0x00 or op == 0x18:
                if op != stop:
                    raise ValueError('terminator %02x at %x, wanted %02x' % (op, p, stop))
                if len(st) != 1:
                    raise ValueError('stack %d at %x' % (len(st), p))
                return st[0], p + 1
            if op == 0x08: st.append(Int(s.u('<i', p + 1))); p += 5
            elif op == 0x09: st.append(Int(s.u('<b', p + 1))); p += 2
            elif op == 0x0a: st.append(Int(s.u('<h', p + 1))); p += 3
            elif op == 0x0b: st.append(Flt(s.u('<f', p + 1))); p += 5
            elif op == 0x0e: st.append(Str(s.strs[s.u('<I', p + 1)])); p += 5
            elif op == 0x0f: st.append(Str(s.strs[c[p + 1]])); p += 2
            elif op == 0x10: st.append(Str(s.strs[s.u('<H', p + 1)])); p += 3
            elif op == 0x12: st.append(Ident(s.syms[s.u('<I', p + 1)])); p += 5
            elif op == 0x13: st.append(Ident(s.syms[c[p + 1]])); p += 2
            elif op == 0x14: st.append(Ident(s.syms[s.u('<H', p + 1)])); p += 3
            elif op == 0x15: st.append(Int(0)); p += 1
            elif op == 0x16: st.append(Int(1)); p += 1
            elif op == 0x2c: st.append(Neg(st.pop())); p += 1
            elif op == 0x07:
                fn = st.pop()
                if not isinstance(fn, Ident):
                    raise ValueError('call of non-ident at %x' % p)
                n = s.u('<I', p + 1)
                offs = struct.unpack_from('<%dI' % n, c, p + 5)
                p += 5 + 4 * n
                if c[p] != 0x03:
                    raise ValueError('expected BRA at %x' % p)
                end = p + 5 + s.u('<I', p + 1)
                args = []
                for k, o in enumerate(offs):
                    a, nxt = s.expr(o, 0x00)
                    want = offs[k + 1] if k + 1 < n else end
                    if nxt != want:
                        raise ValueError('arg %d of call at %x ends %x, next %x' % (k, p, nxt, want))
                    args.append(a)
                st.append(Call(str(fn), args))
                p = end
            else:
                raise ValueError('unhandled opcode %02x (%s) at %x' % (op, OPN.get(op, '?'), p))


def decompile(data):
    ver, syms, strs, code = read_qvm(data)
    d = Decoder(syms, strs, code)
    p, stmts = 0, []
    while code[p] != 0x00:
        e, p = d.expr(p, 0x18)
        stmts.append(e)
    if p != len(code) - 1:
        raise ValueError('trailing code after BRK at %x' % p)
    return ver, stmts


# ---------------------------------------------------------------- text
def qstr(v):
    return '"' + v.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'


def to_text(e, ind=0):
    if isinstance(e, Call):
        inner = [to_text(a, ind + 1) for a in e.args]
        one = '%s(%s)' % (e.name, ', '.join(inner))
        if len(one) + ind * 4 < 160 and '\n' not in one:
            return one
        pad = '    ' * (ind + 1)
        return '%s(\n%s%s\n%s)' % (e.name, pad, (',\n' + pad).join(inner), '    ' * ind)
    if isinstance(e, Neg): return '-' + to_text(e.e, ind)
    if isinstance(e, Flt): return fmt_float(e)
    if isinstance(e, Int): return str(int(e))
    if isinstance(e, Str): return qstr(e)
    if isinstance(e, Ident): return str(e)
    raise TypeError(type(e))


def stmts_to_qsc(stmts):
    return ''.join(to_text(s) + ';\n' for s in stmts)


TOK = re.compile(r'\s*(?:(//[^\n]*)|(/\*.*?\*/)|("(?:[^"\\]|\\.)*")|(\d+\.\d*(?:[eE][-+]?\d+)?|\d+[eE][-+]?\d+)|(\d+)|([A-Za-z_][A-Za-z0-9_]*)|([(),;-]))', re.S)


def tokenize(src):
    p, out = 0, []
    while True:
        m = TOK.match(src, p)
        if not m:
            if src[p:].strip():
                ln = src.count('\n', 0, p) + 1
                raise SyntaxError('bad token at line %d: %r' % (ln, src[p:p + 30]))
            return out
        p = m.end()
        if m.group(1) or m.group(2): continue
        if m.group(3) is not None:
            s = m.group(3)[1:-1]
            s = re.sub(r'\\(.)', lambda k: {'n': '\n'}.get(k.group(1), k.group(1)), s)
            out.append(('S', s))
        elif m.group(4): out.append(('F', float(m.group(4))))
        elif m.group(5): out.append(('I', int(m.group(5))))
        elif m.group(6): out.append(('ID', m.group(6)))
        else: out.append(('P', m.group(7)))


def parse_qsc(src):
    toks = tokenize(src)
    i = 0

    def peek():
        return toks[i] if i < len(toks) else ('EOF', None)

    def take(kind, val=None):
        nonlocal i
        t = peek()
        if t[0] != kind or (val is not None and t[1] != val):
            raise SyntaxError('expected %s %s, got %r (token %d)' % (kind, val, t, i))
        i += 1
        return t[1]

    def expr():
        nonlocal i
        t = peek()
        if t == ('P', '-'):
            i += 1
            return Neg(expr())
        if t[0] == 'S': i += 1; return Str(t[1])
        if t[0] == 'F': i += 1; return Flt(t[1])
        if t[0] == 'I': i += 1; return Int(t[1])
        if t[0] == 'ID':
            i += 1
            if peek() == ('P', '('):
                i += 1
                args = []
                if peek() != ('P', ')'):
                    args.append(expr())
                    while peek() == ('P', ','):
                        i += 1
                        args.append(expr())
                take('P', ')')
                return Call(t[1], args)
            return Ident(t[1])
        raise SyntaxError('unexpected %r' % (t,))
    stmts = []
    while peek()[0] != 'EOF':
        stmts.append(expr())
        take('P', ';')
    return stmts


# ---------------------------------------------------------------- write
class Encoder:
    def __init__(s):
        s.syms, s.symi, s.strs, s.stri = [], {}, [], {}
        s.c = bytearray()

    def sym(s, n):
        if n not in s.symi:
            s.symi[n] = len(s.syms); s.syms.append(n)
        return s.symi[n]

    def str_(s, v):
        if v not in s.stri:
            s.stri[v] = len(s.strs); s.strs.append(v)
        return s.stri[v]

    def emit(s, e):
        c = s.c
        if isinstance(e, Call):
            k = s.sym(e.name)
            s.push_ident(k)
            n = len(e.args)
            c.append(0x07); c += struct.pack('<I', n)
            tab = len(c); c += b'\0' * (4 * n)
            c.append(0x03); bra = len(c); c += b'\0\0\0\0'
            start = len(c)
            for j, a in enumerate(e.args):
                struct.pack_into('<I', c, tab + 4 * j, len(c))
                s.emit(a)
                c.append(0x00)
            struct.pack_into('<I', c, bra, len(c) - start)
        elif isinstance(e, Neg):
            s.emit(e.e); c.append(0x2c)
        elif isinstance(e, Flt):
            c.append(0x0b); c += struct.pack('<f', e)
        elif isinstance(e, Int):
            v = int(e)
            if v == 0: c.append(0x15)
            elif v == 1: c.append(0x16)
            elif -128 <= v < 128: c += struct.pack('<Bb', 0x09, v)
            elif -32768 <= v < 32768: c.append(0x0a); c += struct.pack('<h', v)
            else: c.append(0x08); c += struct.pack('<i', v)
        elif isinstance(e, Str):
            k = s.str_(e)
            if k < 256: c += bytes([0x0f, k])
            elif k < 65536: c.append(0x10); c += struct.pack('<H', k)
            else: c.append(0x0e); c += struct.pack('<I', k)
        elif isinstance(e, Ident):
            s.push_ident(s.sym(str(e)))
        else:
            raise TypeError(type(e))

    def push_ident(s, k):
        if k < 256: s.c += bytes([0x13, k])
        elif k < 65536: s.c.append(0x14); s.c += struct.pack('<H', k)
        else: s.c.append(0x12); s.c += struct.pack('<I', k)


def compile_stmts(stmts, ver=(8, 7)):
    en = Encoder()
    for st in stmts:
        en.emit(st)
        en.c.append(0x18)
    en.c.append(0x00)

    def table(items):
        offs, blob = [], bytearray()
        for it in items:
            offs.append(len(blob)); blob += it.encode('latin1') + b'\0'
        return struct.pack('<%dI' % len(offs), *offs), bytes(blob)
    symT, symD = table(en.syms)
    strT, strD = table(en.strs)
    base = 0x40
    o_symT = base; o_symD = o_symT + len(symT); o_strT = o_symD + len(symD); o_strD = o_strT + len(strT)
    o_code = o_strD + len(strD)
    hdr = struct.pack('<4s12I', b'LOOP', ver[0], ver[1], o_symT, o_symD, len(symT), len(symD),
                      o_strT, o_strD, len(strT), len(strD), o_code, len(en.c))
    hdr += b'\0' * (base - len(hdr))
    return hdr + symT + symD + strT + strD + bytes(en.c)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['d', 'c'])
    ap.add_argument('src'); ap.add_argument('dst')
    a = ap.parse_args()
    if a.mode == 'd':
        ver, stmts = decompile(open(a.src, 'rb').read())
        open(a.dst, 'w', encoding='latin1', newline='\n').write(stmts_to_qsc(stmts))
    else:
        stmts = parse_qsc(open(a.src, encoding='latin1').read())
        open(a.dst, 'wb').write(compile_stmts(stmts))


if __name__ == '__main__':
    main()
