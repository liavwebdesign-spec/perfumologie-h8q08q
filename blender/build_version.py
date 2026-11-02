"""Builds a colour version of the demo page in site/<palette>/ from its renders.

  python blender/build_version.py gesso
  python blender/build_version.py colore

Run the palette's renders first (--palette <name> --scenes 2,3,4,5, into render/<name>/hi and pt).
Scene 1 is shared: it plays in the dark before any palette fades in, so it is rendered once
(--palette gesso --scenes 1, into render/hero/hi and pt).
The page at the root of site/ stays as it is: fixes for the versions go in here.
"""
import shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / 'site'

# Page colours per palette. Only tokens change; the engine and layout stay as in site/index.html.
CSS = {
    'gesso': """
  :root{--ink:#14161a;--ink-muted:rgba(20,22,26,.66);--accent-ink:#3f5a45}
  body.light{--ui:#14161a;--ui-m:rgba(20,22,26,.62);--ui-f:rgba(20,22,26,.2);--ui-f2:rgba(20,22,26,.1)}
  /* upright screens: the copy overlaps the pale bottle, where the green accent and a scrim both fail */
  @media (min-width:641px) and (orientation:portrait){
    .layer.ink:not(.ink-m){--ta:var(--ink);--tm:var(--ink)}
  }
  @media (max-width:640px){
    .layer[data-scene="3"]{--t:var(--ink);--tm:var(--ink);--ta:var(--ink);--sh:none;--shs:none}
  }
  /* upright screens: the copy lands on the green bottle, so the wall colour rises behind the words only and the bottle keeps its colour */
  @media (max-aspect-ratio:5/6){
    .layer[data-scene="3"]::before{display:block;-webkit-mask-image:none;mask-image:none;
      background:radial-gradient(ellipse min(75vw,42vh) 26vh at 0 84%,rgba(222,221,218,.94) 0%,rgba(222,221,218,.9) 60%,rgba(222,221,218,0) 100%)}
  }
  /* small phones held sideways get the landscape frames, which are white here too */
  @media (max-width:640px) and (orientation:landscape){
    .layer.ink{--t:var(--ink);--tm:var(--ink-muted);--ta:var(--accent-ink);--sh:none;--shs:none}
    .layer.ink::before{display:none}
  }
""",
    # deep walls all the way down: copy and chrome stay ivory, so nothing flips to ink
    'colore': """
  :root{--ink:#f6f1e8;--ink-muted:rgba(246,241,232,.86);--accent-ink:#ecd9ae}
  body.light{--ui:#f6f1e8;--ui-m:rgba(246,241,232,.76);--ui-f:rgba(246,241,232,.3);--ui-f2:rgba(246,241,232,.16)}
  .layer.ink .cta:hover,.layer.ink-m .cta:hover{color:#1b1a18}
  .fam i{box-shadow:0 0 0 1px rgba(246,241,232,.6)}
  /* upright tablets: the copy lands on the glow at the foot of the wall, so it keeps the scrim */
  @media (min-width:641px) and (orientation:portrait){
    .layer.ink:not(.ink-m)::before{display:block}
  }
""",
}

# Chrome tone per palette: on the white walls the chrome stays ink even where the portrait bottle fills the frame.
JS = {
    'gesso': [('return frame >= 28 && !(PORTRAIT && frame >= 70);', 'return frame >= 22;'),
              ('if(s === 3) return !PORTRAIT || frame >= 36;', 'if(s === 3) return true;')],
}

# Size fixes for both versions. They stay out of site/index.html so the page already live does not move.
COMMON_CSS = """
  /* opening: the name is in the frame, behind the bottle. The heading stays for screen readers, and the rest sits bottom left like every other scene */
  #intro::before{display:none}
  #intro h1{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}
  #intro .kicker{order:-1;margin:0 0 12px}
  #intro .kicker::before{display:block}
  #intro .sub{margin-top:0}
  /* wide and short laptops: the row of bottles takes the height, so the copy above it tightens */
  @media (min-width:641px) and (min-height:521px), (min-width:1025px){
    .layer.top h2{font-size:min(clamp(42px,7vw,112px),10.5vh)}
  }
  @media (min-width:641px) and (max-height:800px){
    .layer.top .kicker{margin-bottom:10px}
    .layer.top .en{margin-top:8px}
    .fam{margin-top:14px}
    .cta{margin-top:14px;padding:10px 24px;font-size:14px}
  }
  /* upright tablets: 3:4 crops the frame and lifts the row into the copy, so the copy moves to the floor under it, as on phones */
  @media (min-width:641px) and (max-aspect-ratio:5/6){
    .layer.top{justify-content:flex-end;padding-top:0;padding-bottom:clamp(84px,9vh,140px)}
  }
  /* small phones held sideways: the side copy has to stop short of the bottle */
  @media (max-width:640px) and (orientation:landscape){
    .layer .en{max-width:150px;line-height:1.25}
  }
  /* phones held sideways: the closing button has to stay clear of the pumps */
  @media (max-height:520px) and (max-width:1024px){
    .layer[data-scene="5"] .en{display:none}
    .layer[data-scene="5"] .cta{margin-top:8px;padding:8px 18px;font-size:13px}
  }
  /* small upright phones: the copy has only the space under the row */
  @media (max-width:640px) and (max-height:680px) and (orientation:portrait){
    .layer.top{padding-bottom:calc(54px + env(safe-area-inset-bottom,0px))}
    .layer.top .kicker{margin-bottom:6px}
    .layer.top h2{font-size:30px}
    .layer.top .en{display:none}
    .fam{gap:6px 12px;margin-top:10px;font-size:11px}
    .cta{margin-top:12px;padding:10px 20px;font-size:13px}
  }
"""

COMMON_JS = [
    # the opening is frame 0 of scene 1, so the bottle moves from the first tick of the scroll
    ('introPx: 220,       // scroll length of the opening still before scene 1 begins',
     'introPx: 1,         // the opening still is frame 0 of scene 1: no dead zone before it moves'),
    ('<section class="layer center" id="intro" data-scene="0">', '<section class="layer" id="intro" data-scene="0">'),
    # any upright screen plays the upright render, and tablets get a sharper tier of it
    ("""const USE_HI = !LOW_POWER;
""", ''),
    ("""const PORTRAIT = LOW_POWER && (innerHeight / innerWidth) > 1.4;
const proxyPath = PORTRAIT ? CONFIG.pathPt : CONFIG.pathLo;""",
     """const PORTRAIT = (innerHeight / innerWidth) > 1.2;
const USE_HI = !LOW_POWER && !PORTRAIT;
const proxyPath = PORTRAIT ? (innerWidth >= 600 ? CONFIG.pathPtl : CONFIG.pathPt) : CONFIG.pathLo;"""),
    ("""  opening: 'opening.jpg',""",
     """  pathPtl: (s,f) => `frames-ptl/${s}/${String(f).padStart(3,'0')}.jpg`, // 576x1024, upright tablets and tall screens
  opening: 'opening.jpg',"""),
    ('const nowPortrait = LOW_POWER && (innerHeight / innerWidth) > 1.4;',
     'const nowPortrait = (innerHeight / innerWidth) > 1.2;'),
    # the pump lifts out of the top of the frame in scene 3: where the screen crops top and bottom, the crop follows it
    ("""function draw(img){""",
     """function topFocus(){
  const ramp = s => { const t = Math.max(0, Math.min(1, (viewY - seg[s].start) / (30 * CONFIG.pxPerFrame))); return t*t*(3-2*t); };
  return ramp(3) - ramp(4);
}
function draw(img){"""),
    ('dy = (ch-dh)/2;', 'dy = (ch-dh)*(.5 - topFocus()/2);'),
    # computers stretch the 1280 frames to the screen, and the browser's default scaling is its roughest
    ('ctx.drawImage(img, dx, dy, dw, dh);', "ctx.imageSmoothingQuality = 'high';\n  ctx.drawImage(img, dx, dy, dw, dh);"),
    # computers went through 480 small frames before the sharp ones, so a first visit showed 640 frames for 20-30s.
    # Now they go straight to sharp, and a small frame is only fetched for a scene reached before its sharp set started
    ("""  const order = [];
  for(let s=1; s<=CONFIG.scenes; s++) if(!loaded.lo[s]) order.push({s, tier:'lo'});
""",
     """  const order = [];
  if(!USE_HI){ for(let s=1; s<=CONFIG.scenes; s++) if(!loaded.lo[s]) order.push({s, tier:'lo'}); }
  else if(!store.hi[cur] && !loaded.lo[cur]) order.push({s:cur, tier:'lo'});
"""),
]

def encode(src, dst, *vf, q=5):
    dst.mkdir(parents=True, exist_ok=True)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(src / '%03d.jpg'), *vf,
                    '-q:v', str(q), str(dst / '%03d.jpg')], check=True)

def main(name):
    out = SITE / name
    out.mkdir(parents=True, exist_ok=True)
    html = (SITE / 'index.html').read_text(encoding='utf-8')
    for old, new in COMMON_JS + JS.get(name, []):
        assert old in html, old
        html = html.replace(old, new)
    (out / 'index.html').write_text(html.replace('</style>\n</head>', COMMON_CSS + CSS[name] + '</style>\n</head>'),
                                    encoding='utf-8', newline='\n')
    shutil.copytree(SITE / 'fonts', out / 'fonts', dirs_exist_ok=True)
    hero = ROOT / 'render' / 'hero'
    shutil.copy(hero / 'hi' / '1' / '001.jpg', out / 'opening.jpg')
    shutil.copy(hero / 'pt' / '1' / '001.jpg', out / 'opening-pt.jpg')
    for s in '12345':
        render = hero if s == '1' else ROOT / 'render' / name
        # the computer tier is what gets stretched, so it keeps the bottle's fine pattern (q 5 smeared it)
        encode(render / 'hi' / s, out / 'frames' / s, q=2)
        encode(render / 'hi' / s, out / 'frames-lo' / s, '-vf', 'scale=640:360:flags=lanczos')
        encode(render / 'pt' / s, out / 'frames-pt' / s, '-vf', 'scale=405:720:flags=lanczos')
        encode(render / 'pt' / s, out / 'frames-ptl' / s)
    print(name, 'built:', sum(1 for _ in out.rglob('*.jpg')), 'images')

if __name__ == '__main__':
    main(sys.argv[1])
