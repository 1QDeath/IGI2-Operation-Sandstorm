"""ILFF resource (.res) reader/writer for IGI 2."""
import struct,sys
def read(path_or_bytes):
    d=open(path_or_bytes,'rb').read() if isinstance(path_or_bytes,str) else path_or_bytes
    assert d[:4]==b'ILFF',d[:4]
    size,align,_=struct.unpack_from('<3I',d,4)
    form=d[16:20]
    p=20; chunks=[]
    while p<len(d):
        tag=d[p:p+4]; sz,al,nxt=struct.unpack_from('<3I',d,p+4)
        chunks.append((tag,d[p+16:p+16+sz],al))
        if nxt==0: break
        p+=nxt
    return form,chunks,(size,align,_)
def entries(chunks):
    """pair NAME chunks with following data chunk"""
    out=[];i=0
    while i<len(chunks):
        t,b,_=chunks[i]
        if t==b'NAME' and i+1<len(chunks):
            out.append((b.rstrip(b'\0').decode('latin1'),chunks[i+1][0].decode(),chunks[i+1][1])); i+=2
        else:
            out.append((None,t.decode(),b)); i+=1
    return out
if __name__=='__main__':
    form,ch,h=read(sys.argv[1]); print(form,h,len(ch))
    for n,t,b in entries(ch): print(t,len(b),n)

def write(form, chunks, align=4, pad_last=False):
    """chunks: list of (tag bytes, data bytes, align). Rebuilds an ILFF file."""
    body=bytearray()
    for i,(tag,data,al) in enumerate(chunks):
        last=i==len(chunks)-1
        pad=0 if (last and not pad_last) else (-len(data))%4   # (originals differ: loadingscreen.res / MENUSYSTEM menusystem.res
                                                              #  pad the LAST chunk too, the language files do not - 10-12)
        nxt=0 if last else 16+len(data)+pad
        body+=tag+struct.pack('<3I',len(data),al,nxt)+data+b'\0'*pad
    total=20+len(body)
    return b'ILFF'+struct.pack('<3I',total,align,0)+form+bytes(body)
