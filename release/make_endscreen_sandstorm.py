"""make_endscreen_sandstorm - the release end picture: work/sirocco5/endscreen/make_endscreen.py (our own picture) WITHOUT the
'OPERATION SIROCCO' line - TO BE CONTINUED, the Arabic word, and MADE BY 1QDEATH / DISCORD: 1QDEATH at the bottom. The original generator is not changed: this runs its
source with that one line taken out and the output pointed here.
    python -P work/release/make_endscreen_sandstorm.py   -> work/release/endscreen/congratulations.jpg (640x480 RGB baseline JPEG)
"""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, '..', 'sirocco5', 'endscreen', 'make_endscreen.py')
OUT = os.path.join(HERE, 'endscreen')
src = open(SRC, encoding='utf-8').read()
old_b1 = "    b1 = centre('OPERATION SIROCCO', f_small, 18 * S, (170, 150, 110), spacing=5 * S)\n"
assert src.count(old_b1) == 1
src = src.replace(old_b1, "    b1 = 18 * S\n")
src = src.replace("print('title block: OPERATION SIROCCO to y %.0f, ", "print('title block: top %.0f, ")
src = src.replace("HERE = os.path.dirname(os.path.abspath(__file__))", "HERE = %r" % OUT)
src = src.replace("    img.save(os.path.join(HERE, 'preview_2x.png'))\n", "")
# (owner 11-23 release spec) the bottom line becomes the credit: MADE BY 1QDEATH, then DISCORD: 1QDEATH under it
old_hook = "    hook = 'JONES... DON\\'T COME HOME. NOT YET.'\n"
assert src.count(old_hook) == 1, 'hook line moved'
src = src.replace(old_hook, "    hook = 'CREATED BY 1QDEATH'\n"
                            "    centre('DISCORD: 1QDEATH   |   GITHUB.COM/1QDEATH', f_small, int(h * 0.945), (200, 165, 95), spacing=1 * S)\n")
src = src.replace("int(h * 0.90) + d.textbbox", "int(h * 0.885) + d.textbbox")
assert 'SIROCCO' not in src.upper().replace('SIROCCO5', ''), 'Sirocco text left'
os.makedirs(OUT, exist_ok=True)
g = {'__name__': '__main__', '__file__': SRC}
exec(compile(src, SRC, 'exec'), g)
