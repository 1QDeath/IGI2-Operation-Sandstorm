"""Parse IGI2 AI graph .dat (tagged records) -> list of node dicts."""
import struct,sys
SZ={5:4,6:4,8:24,9:2}
def parse(path):
    d=open(path,'rb').read(); assert d[:4]==b'\xcc\xdd\xee\xff'
    p=4; recs=[]
    while p<len(d):
        assert d[p]==4,(p,d[p:p+8].hex())
        key=struct.unpack_from('<I',d,p+1)[0]; t=d[p+7]; assert d[p+6]==t
        p+=8
        if t==9:
            n=d[p]; v=d[p+1:p+n].decode('latin1'); p+=1+n; recs.append((key,t,v)); continue
        n=SZ[t]
        v={5:lambda b:struct.unpack('<i',b)[0],6:lambda b:struct.unpack('<f',b)[0],8:lambda b:struct.unpack('<3d',b)}[t](d[p:p+n])
        recs.append((key,t,v)); p+=n
    return recs
def nodes(path):
    recs=parse(path); out=[]; cur=None
    for k,t,v in recs:
        if k==0x0735ce04 or (cur is None):
            pass
        if t==8: cur={'pos':v}; out.append(cur)
        elif cur is not None: cur[hex(k)]=v
    return recs,out
if __name__=='__main__':
    recs=parse(sys.argv[1])
    for r in recs[:30]: print(hex(r[0]),r[1],r[2])
    print(len(recs))


def topology(path):
    """-> (node_ids, edges[(a,b)]); node id key 0x735ce, edge keys 0x9104a/0x918f6"""
    recs = parse(path)
    nodes, edges, cur = [], [], {}
    for k, t, v in recs:
        if k == 0x735ce:
            nodes.append(v)
        elif k == 0x9104a:
            cur = {'a': v}
        elif k == 0x918f6:
            cur['b'] = v; edges.append((cur['a'], v))
    return nodes, edges


def components(path):
    nodes, edges = topology(path)
    parent = {n: n for n in nodes}
    def f(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for a, b in edges:
        parent[f(a)] = f(b)
    comp = {}
    for n in nodes:
        comp.setdefault(f(n), []).append(n)
    return sorted((len(c) for c in comp.values()), reverse=True)


# ---------------------------------------------------------------- writer (same record layout as the originals)
def _rec(key, t, payload):
    return b'\x04' + struct.pack('<I', key) + bytes([0, t, t]) + payload


def write(nodes, edges, max_nodes=None):
    """nodes: list of dict(id, pos(x,y,z), material=int, light=float, terrain=0|1, crit=str); ids 1..N
    edges: iterable of (a, b) node ids (stored once, larger id first, like the originals)"""
    out = bytearray(b'\xcc\xdd\xee\xff')
    if max_nodes is None:
        max_nodes = ((len(nodes) + 99) // 100) * 100 + 100
    out += _rec(0xd3ae6, 5, struct.pack('<i', max_nodes))
    for n in nodes:
        out += _rec(0x735ce, 5, struct.pack('<i', n['id']))
        out += _rec(0x1d4295, 8, struct.pack('<3d', *n['pos']))
        out += _rec(0xf7e9c, 6, struct.pack('<f', n.get('f7e9c', 0.0)))
        out += _rec(0x143023, 6, struct.pack('<f', n.get('f143023', 0.5)))
        out += _rec(0x1bb629, 5, struct.pack('<i', n.get('material', 1)))
        out += _rec(0x2654de, 6, struct.pack('<f', n.get('light', 0.3)))
        out += _rec(0x214e00, 5, struct.pack('<i', n.get('terrain', 1)))
        c = n.get('crit', '').encode('latin1') + b'\0'
        out += _rec(0x1bd3e5, 9, bytes([len(c)]) + c)
    seen = set()
    for a, b in edges:
        a, b = max(a, b), min(a, b)
        if a == b or (a, b) in seen:
            continue
        seen.add((a, b))
        out += _rec(0x9104a, 5, struct.pack('<i', a))
        out += _rec(0x918f6, 5, struct.pack('<i', b))
        out += _rec(0xda923, 5, struct.pack('<i', 1))
    return bytes(out), len(seen), max_nodes
