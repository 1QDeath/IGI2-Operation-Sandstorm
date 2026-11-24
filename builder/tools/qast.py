import sys,os,collections
sys.path.insert(0,os.path.dirname(__file__)); import igiqvm
def load(p):
    if p.endswith('.qvm'): return igiqvm.decompile(open(p,'rb').read())[1]
    return igiqvm.parse_qsc(open(p,encoding='latin1').read())
def walk(e,depth=0,parent=None):
    if isinstance(e,igiqvm.Call):
        yield e,depth,parent
        for a in e.args: yield from walk(a,depth+1,e)
def tasks(stmts):
    for s in stmts:
        for e,d,par in walk(s):
            if e.name=='Task_New': yield e,d,par
def lit(x):
    if isinstance(x,igiqvm.Neg): return -lit(x.e)
    if isinstance(x,(igiqvm.Int,igiqvm.Flt)): return float(x) if isinstance(x,igiqvm.Flt) else int(x)
    return str(x)
