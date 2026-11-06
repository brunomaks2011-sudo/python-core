"""LEGO NEWS UA — YouTube Shorts (1080×1920) generator.

Reads script/timeline.json + script/caption_groups.json (made by script/voice.py) and the scene
config below; writes index.html and compositions/*.html as plain, editable HyperFrames source.
Swap photos: replace files in assets/photos/ (same names) or edit the photo lists below, then
    python3 script/build.py && npx hyperframes check
"""
import html, json, os, re, subprocess

P = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TL = json.load(open(f"{P}/script/timeline.json")); CAPS = json.load(open(f"{P}/script/caption_groups.json"))
SC = {s["id"]: s for s in TL["scenes"]}; DUR = round(TL["duration"], 2)
E = html.escape
W, H = 1080, 1920

def L(sid): return round(SC[sid]["end"] - SC[sid]["start"], 3)
def rel(sid, t): return round(t - SC[sid]["start"], 3)
def lt(sid, i): return rel(sid, SC[sid]["lines"][i]["start"])
def wt(sid, i, needle, nth=0):
    hits = [w for w in SC[sid]["lines"][i]["words"] if w["text"].lower().strip("—–-.,!?:«»…").startswith(needle.lower())]
    return rel(sid, hits[nth]["start"])
def ab(sid, t): return round(SC[sid]["start"] + t, 3)

RANGE_LAT = "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+20AC,U+2122,U+2212,U+FEFF"
RANGE_CYR = "U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116"
FONTS = "".join(
    f"@font-face{{font-family:'{fam}';font-weight:{w};src:url('assets/fonts/{f}-{sub}-{w}-normal.woff2') format('woff2');unicode-range:{rng};}}\n"
    for fam, f, ws in (("LNU Display", "montserrat", (700, 800, 900)), ("LNU Text", "inter", (600, 700)))
    for w in ws for sub, rng in (("latin", RANGE_LAT), ("cyrillic", RANGE_CYR)))
TOKENS = ":root{--red:#E3000B;--red-deep:#A8000A;--yellow:#FFD500;--white:#fff;--black:#0B0B0D;--official:#15803D;--leak:#C2410C;--rumor:#1D4ED8;}\n"

BASE_CSS = """
    #root { position:absolute; inset:0; overflow:hidden; font-family:'LNU Text',sans-serif; color:#fff; }
    #root .bg { position:absolute; inset:0; background:
        radial-gradient(900px 900px at 80% 25%, rgba(227,0,11,.55), transparent 62%),
        radial-gradient(800px 700px at 0% 100%, rgba(255,213,0,.14), transparent 60%),
        linear-gradient(170deg,#1b1b1f 0%,#0b0b0d 70%); }
    #root .studs { position:absolute; left:-80px; top:-80px; width:1240px; height:2080px; opacity:.08;
        background-image:radial-gradient(circle at 40px 40px,#fff 0 17px,transparent 18px); background-size:80px 80px; }
    #root .badge { position:absolute; right:90px; top:196px; display:flex; align-items:center; gap:12px; padding:10px 22px 10px 18px; border-radius:999px;
        font:900 32px 'LNU Display'; letter-spacing:.1em; color:#fff; }
    #root .badge i { width:18px; height:18px; border-radius:50%; background:#fff; display:block; }
    #root .theme { position:absolute; left:90px; top:272px; font:800 34px 'LNU Display'; letter-spacing:.12em; color:var(--yellow); text-transform:uppercase; }
    #root .num { position:absolute; left:84px; top:312px; font:900 150px/1 'LNU Display'; color:#fff; letter-spacing:-.03em; text-shadow:0 8px 0 rgba(0,0,0,.35); }
    #root .name { position:absolute; left:90px; right:90px; top:470px; font:900 52px/1.05 'LNU Display'; color:#fff; white-space:nowrap; }
    #root .stage { position:absolute; left:60px; top:548px; width:960px; height:520px; border-radius:34px; background:#fff; overflow:hidden;
        box-shadow:0 0 0 8px var(--yellow), 0 40px 90px rgba(0,0,0,.6); }
    #root .ph { position:absolute; inset:0; }
    #root .ph img { position:absolute; inset:0; width:100%; height:100%; object-fit:contain; }
    #root .src { position:absolute; right:16px; bottom:12px; padding:5px 12px; border-radius:8px; background:rgba(11,11,13,.78); font:600 28px 'LNU Text'; color:#fff; z-index:50; }
    #root .ghost { position:absolute; left:0; right:0; top:1390px; text-align:center; font:900 330px/1 'LNU Display'; color:rgba(255,255,255,.05); letter-spacing:-.04em; }
    #root .chips { position:absolute; left:60px; top:1088px; width:880px; height:100px; }
    #root .chip { position:absolute; top:0; height:100px; border-radius:22px; display:flex; align-items:center; justify-content:center; gap:10px;
        font:900 46px 'LNU Display'; white-space:nowrap; box-shadow:0 10px 0 rgba(0,0,0,.35); }
    #root .chip small { font:800 28px 'LNU Display'; opacity:.85; }
    #root .c-pcs { left:0; width:300px; background:#fff; color:var(--black); }
    #root .c-pcs::before { content:''; width:34px; height:26px; border-radius:6px; background:var(--red); box-shadow:inset 0 -5px 0 rgba(0,0,0,.2); margin-right:4px; }
    #root .c-price { left:318px; width:250px; background:var(--yellow); color:var(--black); }
    #root .c-date { left:586px; width:294px; background:var(--red); color:#fff; font-size:42px; }
"""

def scene(cid, dur, css, body, js):
    return f"""<template>
  <style>
{FONTS}{TOKENS}{BASE_CSS}{css}
  </style>
  <div id="root" data-composition-id="{cid}" data-width="{W}" data-height="{H}" data-duration="{dur}">
    <div class="bg"></div>
    <div id="{cid}-studs" class="studs" data-layout-ignore></div>
{body}
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
    const fmt = (v) => Math.round(v).toLocaleString('en-US').replace(/,/g, '\\u2009');
    tl.fromTo('#{cid}-studs', {{ y: 0 }}, {{ y: -80, duration: {dur}, ease: 'none' }}, 0);
{js}
    window.__timelines["{cid}"] = tl;
  </script>
</template>
"""

STATUS = {"LEAK": ("LEAK", "var(--leak)"), "OFFICIAL": ("OFFICIAL", "var(--official)")}

def header(sid, status, theme, num, name, t0=0.0):
    st = STATUS[status]
    body = (f'    <div id="{sid}-ghost" class="ghost" data-layout-ignore>{E(num)}</div>\n'
            f'    <div id="{sid}-badge" class="badge" style="background:{st[1]}"><i></i>{st[0]}</div>\n'
            f'    <div id="{sid}-theme" class="theme">{E(theme)}</div>\n'
            f'    <div id="{sid}-num" class="num">{E(num)}</div>\n'
            f'    <div id="{sid}-name" class="name">{E(name)}</div>')
    js = [f"    tl.fromTo('#{sid}-ghost', {{y:200, opacity:0}}, {{y:0, opacity:1, duration:1.2, ease:'expo.out'}}, {t0});",
          f"    tl.fromTo('#{sid}-badge', {{scale:0, rotation:-10}}, {{scale:1, rotation:0, duration:0.4, ease:'back.out(2.6)'}}, {t0+0.05});",
          f"    tl.fromTo('#{sid}-theme', {{x:-120, opacity:0}}, {{x:0, opacity:1, duration:0.35, ease:'expo.out'}}, {t0+0.0});",
          f"    tl.fromTo('#{sid}-num', {{scale:2.4, opacity:0, y:-30}}, {{scale:1, opacity:1, y:0, duration:0.45, ease:'expo.out'}}, {t0+0.1});",
          f"    tl.fromTo('#{sid}-name', {{x:160, opacity:0}}, {{x:0, opacity:1, duration:0.45, ease:'expo.out'}}, {t0+0.25});"]
    return body, "\n".join(js)

KB = [(1.0, 1.14, -18, 18), (1.16, 1.02, 22, -10), (1.04, 1.2, 0, -26), (1.18, 1.04, -24, 12)]

def stage(sid, photos, posts):
    """photos: list of (file, t_start, t_end). Fast whip-in per cut + Ken Burns + parallax."""
    h = []; j = []
    for i, (src, s, e) in enumerate(photos):
        s = round(s, 3); d = round(e - s, 3); pid = f"{sid}-p{i+1}"
        h.append(f'      <div id="{pid}" class="ph clip" data-start="{s}" data-duration="{d}" data-track-index="{2+i%2}" style="z-index:{i+1}"><img id="{pid}-i" src="assets/photos/{src}" alt=""></div>')
        a, b, x0, x1 = KB[i % 4]; dx = 1100 if i % 2 == 0 else -1100
        if i == 0:
            j.append(f"    tl.fromTo('#{pid}-i', {{scale:{a}, x:{x0}}}, {{scale:{b}, x:{x1}, duration:{d}, ease:'sine.inOut'}}, {s});")
        else:
            j.append(f"    tl.fromTo('#{pid}', {{x:{dx}}}, {{x:0, duration:0.32, ease:'expo.out'}}, {s});")
            j.append(f"    tl.fromTo('#{pid}-i', {{scale:{a+0.25}, x:{x0}}}, {{scale:{b}, x:{x1}, duration:{d}, ease:'expo.out'}}, {s});")
    src = "Фото: The Stud Ledger · t.me/thestudledger/" + ", ".join(posts)
    body = f'    <div id="{sid}-stage" class="stage" data-layout-allow-overflow>\n' + "\n".join(h) + f'\n      <div id="{sid}-src" class="src">{E(src)}</div>\n    </div>'
    j.insert(0, f"    tl.fromTo('#{sid}-stage', {{y:700, rotation:6, scale:0.9}}, {{y:0, rotation:0, scale:1, duration:0.55, ease:'expo.out'}}, 0.05);")
    j.append(f"    tl.fromTo('#{sid}-stage', {{rotation:0}}, {{rotation:-1.2, duration:{L(sid)}, ease:'sine.inOut'}}, 0.6);")
    return body, "\n".join(j)

def chips(sid, pcs, price, date, t_pcs, t_price, t_date, price_class=""):
    body = (f'    <div id="{sid}-chips" class="chips">\n'
            f'      <div id="{sid}-cp" class="chip c-pcs"><span id="{sid}-pcs">0</span><small>дет.</small></div>\n'
            f'      <div id="{sid}-cr" class="chip c-price">{E(price)}</div>\n'
            f'      <div id="{sid}-cd" class="chip c-date">{E(date)}</div>\n    </div>')
    js = [f"    tl.fromTo('#{sid}-cp', {{y:140, opacity:0}}, {{y:0, opacity:1, duration:0.35, ease:'back.out(2)'}}, {t_pcs});",
          f"    {{ const o={{v:0}}, el=document.querySelector('#{sid}-pcs'); tl.fromTo(o, {{v:0}}, {{v:{pcs}, duration:1.0, ease:'power3.out', onUpdate:()=>{{el.textContent=fmt(o.v);}}}}, {t_pcs}); }}",
          f"    tl.fromTo('#{sid}-cr', {{scale:0, rotation:-14}}, {{scale:1, rotation:0, duration:0.45, ease:'back.out(3)'}}, {t_price});",
          f"    tl.fromTo('#{sid}-cr', {{scale:1}}, {{scale:1.12, duration:0.16, yoyo:true, repeat:1, ease:'power2.out'}}, {round(t_price+0.45,3)});",
          f"    tl.fromTo('#{sid}-cd', {{x:300, opacity:0}}, {{x:0, opacity:1, duration:0.4, ease:'expo.out'}}, {t_date});"]
    return body, "\n".join(js)

def seq(files, cuts, end):
    """photo list from cut times"""
    out = []
    for i, f in enumerate(files):
        s = cuts[i]; e = cuts[i + 1] if i + 1 < len(cuts) else end
        out.append((f, s, e + (0.05 if i + 1 < len(cuts) else 0)))
    return out

# ------------------------------------------------------------------ scenes
def b_hook():
    sid = "hook"; d = L(sid); l2 = lt(sid, 1)
    css = """
    #root .hero { position:absolute; left:0; top:0; width:1080px; height:1920px; }
    #root .hero .ph { position:absolute; left:60px; top:520px; width:960px; height:640px; border-radius:34px; background:#fff; overflow:hidden; box-shadow:0 0 0 8px var(--yellow), 0 40px 90px rgba(0,0,0,.6); }
    #root .hero .ph img { position:absolute; inset:0; width:100%; height:100%; object-fit:contain; }
    #root .t1 { position:absolute; left:70px; right:70px; top:196px; text-align:center; font:900 96px/0.95 'LNU Display'; color:#fff; text-transform:uppercase;
        -webkit-text-stroke:4px #000; paint-order:stroke fill; text-shadow:0 10px 0 rgba(0,0,0,.45); }
    #root .t1 b { color:var(--yellow); }
    #root .figrow { position:absolute; left:60px; top:520px; width:960px; height:640px; border-radius:34px; background:#fff; box-shadow:0 0 0 8px var(--red), 0 40px 90px rgba(0,0,0,.6); }
    #root .figrow img { position:absolute; top:70px; width:150px; height:430px; object-fit:contain; }
    #root .six { position:absolute; left:0; right:0; top:1048px; z-index:20; text-align:center; }
    #root .six span { display:inline-block; padding:12px 34px; border-radius:22px; background:var(--red); font:900 76px 'LNU Display'; color:#fff; box-shadow:0 0 0 6px var(--yellow); }
"""
    shots = [("5897_3.jpg", 0, 0.85), ("5932_3.jpg", 0.85, 1.6), ("5936_3.jpg", 1.6, 2.35), ("5955_3.jpg", 2.35, l2 - 0.05)]
    body = ['    <div class="hero">']; js = []
    for i, (f, s, e) in enumerate(shots):
        pid = f"hk-p{i}"
        body.append(f'      <div id="{pid}" class="ph clip" data-start="{s}" data-duration="{round(e-s+0.04,3)}" data-track-index="{2+i%2}" style="z-index:{i+1}"><img id="{pid}-i" src="assets/photos/{f}" alt=""></div>')
        js.append(f"    tl.fromTo('#{pid}-i', {{scale:1.0}}, {{scale:1.16, duration:{round(e-s+0.04,3)}, ease:'none'}}, {s});")
        if i: js.append(f"    tl.fromTo('#{pid}', {{x:{1100 if i%2 else -1100}}}, {{x:0, duration:0.22, ease:'expo.out'}}, {s});")
    body.append('    </div>')
    body.append('    <div id="hk-t1" class="t1">4 нові <b>LEGO</b>-витоки на <b>2027</b>!</div>')
    js.append("    tl.fromTo('#hk-t1', {scale:1.0}, {scale:1.06, duration:%s, ease:'sine.inOut'}, 0);" % round(l2, 2))
    body.append(f'    <div id="hk-fr" class="figrow clip" data-start="{round(l2-0.05,3)}" data-duration="{round(d-l2+0.05,3)}" data-track-index="4" style="z-index:10">' +
                "".join(f'<img id="hk-f{k}" src="assets/photos/fig{k+1}.png" alt="" style="left:{18+k*154}px">' for k in range(6)) + '</div>')
    js.append(f"    tl.fromTo('#hk-fr', {{scale:1.25, opacity:0}}, {{scale:1, opacity:1, duration:0.3, ease:'expo.out'}}, {round(l2-0.05,3)});")
    for k in range(6):
        js.append(f"    tl.fromTo('#hk-f{k}', {{y:260, opacity:0}}, {{y:0, opacity:1, duration:0.35, ease:'back.out(2)'}}, {round(l2+0.1+k*0.09,3)});")
    t6 = wt(sid, 1, "шість")
    body.append(f'    <div class="six"><span id="hk-six">6 МІНІФІГУРОК!</span></div>')
    js.append(f"    tl.fromTo('#hk-six', {{scale:0, rotation:-12}}, {{scale:1, rotation:-3, duration:0.4, ease:'back.out(3)'}}, {round(t6-0.05,3)});")
    js.append(f"    tl.to('#hk-t1', {{y:-30, opacity:0.0, duration:0.2, ease:'power3.in'}}, {round(d-0.2,3)});")
    return scene(sid, d, css, "\n".join(body), "\n".join(js))

def b_set(sid, status, theme, num, name, files, cuts, posts, pcs, price, date, tp, tr, td, extra=("", "", "")):
    d = L(sid)
    hb, hj = header(sid, status, theme, num, name)
    sb, sj = stage(sid, seq(files, cuts, d), posts)
    cb, cj = chips(sid, pcs, price, date, tp, tr, td)
    css, body, js = extra
    return scene(sid, d, css, "\n".join([hb, sb, cb, body]), "\n".join([hj, sj, cj, js]))

def b_sanctum():
    sid = "sanctum"; d = L(sid)
    cuts = [0, lt(sid, 1) - 0.1, lt(sid, 2) - 0.1, lt(sid, 3) - 0.1]
    tb = round(wt(sid, 0, "бомба") - 0.05, 3)
    css = """
    #root .boom { position:absolute; left:0; right:0; top:620px; text-align:center; z-index:60; }
    #root .boom span { display:inline-block; padding:16px 40px; border-radius:24px; background:var(--yellow); color:var(--black); font:900 96px 'LNU Display'; box-shadow:0 0 0 8px var(--red), 0 30px 60px rgba(0,0,0,.5); }
    #root .six2 { position:absolute; left:84px; top:572px; padding:8px 22px; border-radius:16px; background:var(--red); font:900 52px 'LNU Display'; color:#fff; box-shadow:0 0 0 5px var(--yellow); z-index:60; }
"""
    body = (f'    <div id="sc-boom" class="boom clip" data-start="{tb}" data-duration="{round(lt(sid,1)-0.1-tb,3)}" data-track-index="6"><span id="sc-boom-s">БОМБА! 💥</span></div>\n'
            f'    <div id="sc-six" class="six2 clip" data-start="{round(wt(sid,3,"шість")-0.05,3)}" data-duration="{round(d-wt(sid,3,"шість")+0.05,3)}" data-track-index="7">6 МІНІФІГУРОК!</div>')
    js = (f"    tl.fromTo('#sc-boom-s', {{scale:3, rotation:-20, opacity:0}}, {{scale:1, rotation:-4, opacity:1, duration:0.35, ease:'back.out(2.2)'}}, {tb});\n"
          f"    tl.fromTo('#sc-six', {{scale:0, rotation:8}}, {{scale:1, rotation:-3, duration:0.4, ease:'back.out(3)'}}, {round(wt(sid,3,'шість')-0.05,3)});")
    return b_set(sid, "LEAK", "LEGO Marvel · What If…?", "67005", "Дивний Верховний Санктум",
                 ["5897_3.jpg", "5897_1.jpg", "5897_4.jpg", "5897_2.jpg"], cuts, ["5897"], 814, "100 €", "01.01.2027",
                 round(wt(sid, 2, "вісімсот") - 0.05, 3), round(wt(sid, 2, "сто") - 0.05, 3), round(wt(sid, 2, "сто") + 0.5, 3), (css, body, js))

def b_figs():
    sid = "figs"; d = L(sid)
    names = [("Злий Доктор Стрендж", "Злий"), ("Залізна Людина", "Залізна"), ("Людина-павук", "Людина-павук"),
             ("Зомбі Ванда", "Ванда"), ("Немор", "Немор"), ("Зомбі Тор", "Тор")]
    ts = [round(wt(sid, 0, w) - (0.45 if w in ("Ванда", "Тор") else 0.08), 3) for _, w in names]
    g = round(lt(sid, 1) - 0.12, 3)
    css = """
    #root .head { position:absolute; left:90px; top:196px; font:900 60px 'LNU Display'; color:#fff; }
    #root .head b { color:var(--yellow); }
    #root .strip { position:absolute; left:90px; top:286px; width:900px; height:150px; }
    #root .strip img { position:absolute; top:0; width:140px; height:150px; object-fit:contain; background:#fff; border-radius:16px; }
    #root .big { position:absolute; left:210px; top:470px; width:660px; height:700px; border-radius:36px; background:#fff; overflow:hidden; box-shadow:0 0 0 8px var(--yellow), 0 40px 90px rgba(0,0,0,.6); }
    #root .big img { position:absolute; left:40px; top:40px; width:580px; height:520px; object-fit:contain; }
    #root .big .nm { position:absolute; left:0; right:0; bottom:0; height:130px; display:flex; align-items:center; justify-content:center; text-align:center; padding:0 20px;
        background:var(--red); font:900 54px/1.0 'LNU Display'; color:#fff; }
    #root .big .ix { position:absolute; z-index:5; left:26px; top:18px; font:900 56px 'LNU Display'; color:var(--red); }
    #root .group { position:absolute; left:60px; top:470px; width:960px; height:600px; border-radius:34px; background:#fff; overflow:hidden; box-shadow:0 0 0 8px var(--yellow), 0 40px 90px rgba(0,0,0,.6); }
    #root .group img { position:absolute; inset:0; width:100%; height:100%; object-fit:contain; }
    #root .date2 { position:absolute; left:60px; top:1088px; padding:14px 30px; border-radius:22px; background:var(--red); font:900 56px 'LNU Display'; color:#fff; box-shadow:0 10px 0 rgba(0,0,0,.35); }
    #root .date2 small { font:800 32px 'LNU Display'; color:var(--yellow); margin-right:14px; }
    #root .srcf { position:absolute; left:90px; top:440px; font:600 28px 'LNU Text'; color:rgba(255,255,255,.75); }
"""
    body = ['    <div id="fg-head" class="head">67005 · <b>6 мініфігурок</b></div>', '    <div class="strip">']
    js = ["    tl.fromTo('#fg-head', {x:-100, opacity:0}, {x:0, opacity:1, duration:0.35, ease:'expo.out'}, 0.0);"]
    for k in range(6):
        body.append(f'      <img id="fg-s{k}" src="assets/photos/fig{k+1}.png" alt="" style="left:{k*152}px">')
        js.append(f"    tl.fromTo('#fg-s{k}', {{scale:0, opacity:0}}, {{scale:1, opacity:1, duration:0.3, ease:'back.out(2.5)'}}, {round(ts[k]+0.15,3)});")
    body.append('    </div>')
    for k, ((nm, _), t) in enumerate(zip(names, ts)):
        e = ts[k + 1] if k < 5 else g
        body.append(f'    <div id="fg-b{k}" class="big clip" data-start="{t}" data-duration="{round(e-t+0.02,3)}" data-track-index="{3+k%2}" style="z-index:{10+k}">'
                    f'<div class="ix" data-layout-allow-overlap>{k+1}/6</div><img id="fg-b{k}-i" src="assets/photos/fig{k+1}.png" alt=""><div id="fg-b{k}-n" class="nm">{E(nm)}</div></div>')
        js.append(f"    tl.fromTo('#fg-b{k}', {{rotationY:{-90 if k%2==0 else 90}, transformPerspective:1400, scale:0.8}}, {{rotationY:0, scale:1, duration:0.32, ease:'expo.out'}}, {t});")
        js.append(f"    tl.fromTo('#fg-b{k}-i', {{scale:1.35, y:40}}, {{scale:1.0, y:0, duration:{round(e-t,3)}, ease:'expo.out'}}, {t});")
        js.append(f"    tl.fromTo('#fg-b{k}-n', {{y:140}}, {{y:0, duration:0.25, ease:'expo.out'}}, {round(t+0.08,3)});")
    body.append(f'    <div id="fg-g" class="group clip" data-start="{g}" data-duration="{round(d-g,3)}" data-track-index="5" style="z-index:30"><img id="fg-g-i" src="assets/photos/5897_5.jpg" alt=""></div>')
    body.append(f'    <div id="fg-d" class="date2 clip" data-start="{round(wt(sid,1,"першого")-0.05,3)}" data-duration="{round(d-wt(sid,1,"першого")+0.05,3)}" data-track-index="6" style="z-index:31"><small>РЕЛІЗ</small>01.01.2027</div>')
    body.append('    <div id="fg-src" class="srcf">Фото: The Stud Ledger · t.me/thestudledger/5897</div>')
    js += [f"    tl.fromTo('#fg-g', {{scale:1.3, opacity:0}}, {{scale:1, opacity:1, duration:0.4, ease:'expo.out'}}, {g});",
           f"    tl.fromTo('#fg-g-i', {{scale:1.0}}, {{scale:1.12, duration:{round(d-g,3)}, ease:'sine.inOut'}}, {g});",
           f"    tl.fromTo('#fg-d', {{x:-400}}, {{x:0, duration:0.4, ease:'expo.out'}}, {round(wt(sid,1,'першого')-0.05,3)});"]
    return scene(sid, d, css, "\n".join(body), "\n".join(js))

def b_tacos():
    sid = "tacos"; d = L(sid)
    cuts = [0, lt(sid, 1) - 0.1, wt(sid, 1, "Такос") - 0.05, lt(sid, 2) - 0.1, wt(sid, 2, "всього") - 0.05, lt(sid, 3) - 0.1]
    tw = round(wt(sid, 2, "всього") - 0.05, 3)
    css = """
    #root .wow { position:absolute; left:60px; top:960px; padding:8px 22px; border-radius:16px; background:var(--red); font:900 56px 'LNU Display'; color:#fff; box-shadow:0 0 0 5px var(--yellow); z-index:60; }
"""
    body = f'    <div id="tc-wow" class="wow clip" data-start="{tw}" data-duration="{round(lt(sid,3)-0.1-tw,3)}" data-track-index="7">ВСЬОГО 20 €!</div>'
    js = f"    tl.fromTo('#tc-wow', {{scale:0, rotation:-10}}, {{scale:1, rotation:-3, duration:0.4, ease:'back.out(3)'}}, {tw});"
    return b_set(sid, "LEAK", "LEGO Fortnite", "77088", "Такос Гуакос",
                 ["5932_3.jpg", "5932_1.jpg", "5916_3.jpg", "5916_4.jpg", "5911_2.jpg", "5932_4.jpg"], cuts, ["5932", "5916", "5911"],
                 193, "20 €", "01.01.2027", round(lt(sid, 2) - 0.05, 3), round(wt(sid, 2, "двадцять") - 0.05, 3), round(wt(sid, 3, "першого") - 0.05, 3), (css, body, js))

def b_p1000():
    sid = "p1000"; d = L(sid)
    cuts = [0, wt(sid, 0, "Пі") - 0.05, lt(sid, 1) - 0.1, wt(sid, 1, "дев'яносто") - 0.1, lt(sid, 2) - 0.1, wt(sid, 2, "першого") - 0.05]
    return b_set(sid, "LEAK", "LEGO Fortnite", "77084", "P-1000",
                 ["5936_1.jpg", "5936_3.jpg", "5916_1.jpg", "5936_4.jpg", "5916_2.jpg", "5936_5.jpg"], cuts, ["5936", "5916"],
                 1103, "90 €", "01.01.2027", round(wt(sid, 1, "тисяча") - 0.05, 3), round(wt(sid, 1, "дев'яносто") - 0.05, 3), round(wt(sid, 2, "першого") - 0.05, 3))

def b_lion():
    sid = "lion"; d = L(sid)
    cuts = [0, wt(sid, 0, "Лев") - 0.05, lt(sid, 1) - 0.1, wt(sid, 1, "реліз") - 0.05]
    return b_set(sid, "LEAK", "Китайський Новий рік", "40976", "Лев процвітання",
                 ["5955_1.jpg", "5955_3.jpg", "5955_4.jpg", "5955_2.jpg"], cuts, ["5955"],
                 411, "30 €", "01.01.2027", round(lt(sid, 1) - 0.05, 3), round(wt(sid, 1, "тридцять") - 0.05, 3), round(wt(sid, 1, "першого") - 0.05, 3))

def b_news():
    sid = "news"; d = L(sid); a = round(lt(sid, 1) - 0.1, 3)
    css = """
    #root .q { position:absolute; left:70px; right:70px; top:560px; text-align:center; font:900 130px/1.0 'LNU Display'; color:#fff; text-transform:uppercase;
        -webkit-text-stroke:4px #000; paint-order:stroke fill; }
    #root .q b { color:var(--yellow); display:block; }
    #root .q2 { position:absolute; left:0; right:0; top:930px; text-align:center; font:900 200px 'LNU Display'; color:var(--red); }
"""
    body = (f'    <div id="nw-a" class="clip" data-start="0" data-duration="{a}" data-track-index="2" style="position:absolute;inset:0">'
            f'<div id="nw-q" class="q">А що ж <b>далі?</b></div><div id="nw-q2" class="q2">?</div></div>')
    js = ["    tl.fromTo('#nw-q', {scale:0.5, opacity:0}, {scale:1, opacity:1, duration:0.45, ease:'expo.out'}, 0.0);",
          "    tl.fromTo('#nw-q2', {rotation:-30, scale:0}, {rotation:12, scale:1, duration:0.6, ease:'back.out(2.5)'}, 0.3);"]
    hb, hj = header(sid, "OFFICIAL", "LEGO Ideas · вже офіційно", "21375", "Ґодзіла", a)
    files = seq(["5924_6.jpg", "5924_4.jpg", "5924_5.jpg"], [a, round(wt(sid, 1, "п'ять") - 0.05, 3), round(wt(sid, 1, "вихід") - 0.05, 3)], d)
    sb, sj = stage(sid, files, ["5924"])
    sj = sj.replace("}, 0.05);", f"}}, {a+0.05});", 1).replace("}, 0.6);", f"}}, {a+0.6});", 1)
    cb, cj = chips(sid, 5363, "400 €", "27.11.2026", round(wt(sid, 1, "п'ять") - 0.05, 3), round(wt(sid, 1, "п'ять") + 0.6, 3), round(wt(sid, 1, "вихід") - 0.05, 3))
    wrap = lambda x: f'    <div id="nw-b" class="clip" data-start="{a}" data-duration="{round(d-a,3)}" data-track-index="3" style="position:absolute;inset:0">\n{x}\n    </div>'
    return scene(sid, d, css, body + "\n" + wrap("\n".join([hb, sb, cb])), "\n".join(js + [hj, sj, cj]))

def b_outro():
    sid = "outro"; d = L(sid); b = round(lt(sid, 1) - 0.1, 3)
    css = """
    #root .q { position:absolute; left:70px; right:70px; top:196px; text-align:center; font:900 74px/1.05 'LNU Display'; color:#fff; }
    #root .q b { color:var(--yellow); }
    #root .grid { position:absolute; left:90px; top:560px; width:900px; height:620px; }
    #root .grid .t { position:absolute; width:440px; height:300px; border-radius:24px; background:#fff; overflow:hidden; box-shadow:0 0 0 5px var(--yellow); }
    #root .grid .t img { position:absolute; inset:0; width:100%; height:100%; object-fit:contain; }
    #root .grid .t b { position:absolute; left:12px; top:10px; padding:4px 12px; border-radius:10px; background:var(--red); font:900 30px 'LNU Display'; color:#fff; }
    #root .logo { position:absolute; left:0; right:0; top:420px; text-align:center; }
    #root .logo-box { display:inline-block; padding:24px 54px 26px; border-radius:26px; background:var(--red); box-shadow:0 0 0 10px var(--yellow), 0 40px 90px rgba(0,0,0,.6); }
    #root .l1 { font:900 120px/0.95 'LNU Display'; color:#fff; -webkit-text-stroke:3px #000; paint-order:stroke fill; }
    #root .l2 { font:900 64px/1 'LNU Display'; color:var(--yellow); letter-spacing:.3em; padding-left:.3em; margin-top:6px; }
    #root .btn { position:absolute; left:0; right:0; top:840px; text-align:center; }
    #root .btn span { display:inline-flex; align-items:center; gap:20px; padding:28px 60px; border-radius:999px; background:#fff; color:var(--red); font:900 64px 'LNU Display'; }
    #root .btn i { width:0; height:0; border-left:36px solid var(--red); border-top:22px solid transparent; border-bottom:22px solid transparent; display:block; }
    #root .cred { position:absolute; left:0; right:0; top:1060px; text-align:center; font:700 32px 'LNU Text'; color:rgba(255,255,255,.88); }
    #root .cred b { color:var(--yellow); }
"""
    tiles = [("5897_3.jpg", "67005"), ("5932_3.jpg", "77088"), ("5936_3.jpg", "77084"), ("5955_3.jpg", "40976")]
    body = [f'    <div id="ou-a" class="clip" data-start="0" data-duration="{b}" data-track-index="2" style="position:absolute;inset:0">',
            '      <div id="ou-q" class="q">Який набір — <b>ваш фаворит?</b><br>Пишіть у коментарях!</div>', '      <div class="grid">']
    js = ["    tl.fromTo('#ou-q', {y:60, opacity:0}, {y:0, opacity:1, duration:0.4, ease:'expo.out'}, 0.0);"]
    for k, (f, n) in enumerate(tiles):
        x, y = (k % 2) * 460, (k // 2) * 320
        body.append(f'        <div id="ou-t{k}" class="t" style="left:{x}px;top:{y}px"><img src="assets/photos/{f}" alt=""><b>{n}</b></div>')
        js.append(f"    tl.fromTo('#ou-t{k}', {{scale:0, rotation:{-8+k*5}}}, {{scale:1, rotation:0, duration:0.4, ease:'back.out(2)'}}, {round(0.3+k*0.15,2)});")
    body += ['      </div>', '    </div>',
             f'    <div id="ou-b" class="clip" data-start="{b}" data-duration="{round(d-b,3)}" data-track-index="3" style="position:absolute;inset:0">',
             '      <div class="logo"><div id="ou-logo" class="logo-box"><div class="l1">LEGO NEWS</div><div class="l2">UA</div></div></div>',
             '      <div class="btn"><span id="ou-btn"><i></i>ПІДПИСАТИСЯ</span></div>',
             '      <div id="ou-cred" class="cred">Новини та фото: <b>The Stud Ledger</b><br>t.me/thestudledger</div>', '    </div>']
    js += [f"    tl.fromTo('#ou-logo', {{scale:0.3, rotationX:70, transformPerspective:900, opacity:0}}, {{scale:1, rotationX:0, opacity:1, duration:0.5, ease:'back.out(1.8)'}}, {b});",
           f"    tl.fromTo('#ou-btn', {{scale:0}}, {{scale:1, duration:0.4, ease:'back.out(3)'}}, {round(b+0.3,3)});",
           f"    tl.fromTo('#ou-btn', {{scale:1}}, {{scale:1.08, duration:0.3, yoyo:true, repeat:3, ease:'sine.inOut'}}, {round(b+0.8,3)});",
           f"    tl.fromTo('#ou-cred', {{opacity:0}}, {{opacity:1, duration:0.4}}, {round(b+0.5,3)});"]
    return scene(sid, d, css, "\n".join(body), "\n".join(js))

# ------------------------------------------------------------------ overlays
HL = re.compile(r"(\d|€|євро|LEGO|ШІСТЬ|Санктум|Дивний|Верховний|Такос|Гуакос|P-1000|Лев|процвітання|Ґодзіла|Ideas|Marvel|січня|листопада|року|деталі|деталей|мініфігурок|МІНІФІГУРОК|NEWS|UA)", re.I)

def b_captions():
    css = """
    #root { font-family:'LNU Display',sans-serif; }
    #root .cg { position:absolute; left:40px; width:900px; top:1206px; height:120px; display:flex; align-items:center; justify-content:center; text-align:center; opacity:0; }
    #root .cg span { font:900 64px/1.02 'LNU Display'; color:#fff; text-transform:uppercase; -webkit-text-stroke:10px #000; paint-order:stroke fill;
        text-shadow:0 8px 0 rgba(0,0,0,.55); }
    #root .cg em { font-style:normal; color:var(--yellow); }
"""
    body = []; js = []
    for i, g in enumerate(CAPS):
        s, e = round(g["start"] - 0.04, 3), round(g["end"], 3)
        words = " ".join(f"<em>{E(w['text'])}</em>" if HL.search(w["text"]) else E(w["text"]) for w in g["words"])
        body.append(f'    <div id="cap{i}" class="cg"><span id="cap{i}-s">{words}</span></div>')
        js.append(f"    tl.fromTo('#cap{i}', {{opacity:0}}, {{opacity:1, duration:0.05}}, {s}); tl.fromTo('#cap{i}-s', {{scale:0.72, y:14}}, {{scale:1, y:0, duration:0.18, ease:'back.out(2.4)'}}, {s});")
        js.append(f"    tl.to('#cap{i}', {{opacity:0, duration:0.06}}, {round(e-0.06,3)}); tl.set('#cap{i}', {{opacity:0, visibility:'hidden'}}, {e});")
    f = scene("captions", DUR, css, "\n".join(body), "\n".join(js))
    return f.replace('    <div class="bg"></div>\n    <div id="captions-studs" class="studs" data-layout-ignore></div>\n', "").replace(
        "    tl.fromTo('#captions-studs', { y: 0 }, { y: -80, duration: %s, ease: 'none' }, 0);\n" % DUR, "")

def b_chrome(cuts):
    css = """
    #root .bug { position:absolute; left:90px; top:196px; padding:6px 16px 8px; border-radius:12px; background:var(--red); box-shadow:0 0 0 4px var(--yellow);
        font:900 32px 'LNU Display'; color:#fff; }
    #root .bug b { color:var(--yellow); }
    #root .prog { position:absolute; left:0; top:0; width:1080px; height:12px; background:var(--yellow); transform-origin:left center; }
    #root .fl { position:absolute; left:-200px; top:-200px; width:1480px; height:2320px; background:linear-gradient(100deg, transparent 0 38%, var(--yellow) 38% 50%, var(--red) 50% 62%, transparent 62%); }
"""
    body = ['    <div id="ch-prog" class="prog" data-layout-ignore></div>']
    js = [f"    tl.fromTo('#ch-prog', {{scaleX:0}}, {{scaleX:1, duration:{DUR}, ease:'none'}}, 0);"]
    for k, t in enumerate(cuts):
        body.append(f'    <div id="ch-f{k}" class="fl" data-layout-ignore style="opacity:1"></div>')
        js.append(f"    tl.fromTo('#ch-f{k}', {{x:-1500}}, {{x:1500, duration:0.36, ease:'power2.inOut'}}, {round(t-0.18,3)});")
    f = scene("chrome", DUR, css, "\n".join(body), "\n".join(js))
    return f.replace('    <div class="bg"></div>\n    <div id="chrome-studs" class="studs" data-layout-ignore></div>\n', "").replace(
        "    tl.fromTo('#chrome-studs', { y: 0 }, { y: -80, duration: %s, ease: 'none' }, 0);\n" % DUR, "")

def adur(f):
    return round(float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f"{P}/assets/sfx/{f}.mp3"], capture_output=True, text=True).stdout), 3)

def main():
    os.makedirs(f"{P}/compositions", exist_ok=True)
    files = {"hook": b_hook(), "sanctum": b_sanctum(), "figs": b_figs(), "tacos": b_tacos(), "p1000": b_p1000(), "lion": b_lion(), "news": b_news(), "outro": b_outro()}
    for k, v in files.items(): open(f"{P}/compositions/{k}.html", "w").write(v)
    open(f"{P}/compositions/captions.html", "w").write(b_captions())
    cuts = [SC[s["id"]]["start"] for s in TL["scenes"][1:]]
    open(f"{P}/compositions/chrome.html", "w").write(b_chrome(cuts))
    hosts = [f'      <div id="{s["id"]}" data-composition-id="{s["id"]}" data-composition-src="compositions/{s["id"]}.html" data-start="{s["start"]}" '
             f'data-duration="{round(s["end"]-s["start"],3)}" data-track-index="1" data-track-kind="graphics" data-width="{W}" data-height="{H}" style="z-index:1"></div>'
             for s in TL["scenes"]]
    # sound design: whoosh per scene cut (rotating takes), impacts on the big reveals, pops on chips, clicks per minifigure
    sfx = [("riser", 0.0, 0.35), ("impact-bass-1", 0.02, 0.7)]
    wh = ["whoosh-short", "whoosh", "whoosh-cinematic"]
    for k, t in enumerate(cuts): sfx.append((wh[k % 3], round(t - 0.25, 3), 0.5))
    sfx.append(("impact-bass-2", ab("hook", wt("hook", 1, "шість") - 0.05), 0.8))
    sfx.append(("impact-bass-1", ab("sanctum", wt("sanctum", 0, "бомба") - 0.05), 0.85))
    sfx.append(("impact-bass-2", ab("sanctum", wt("sanctum", 3, "шість") - 0.05), 0.7))
    for sid, ln, w in (("sanctum", 2, "сто"), ("tacos", 2, "двадцять"), ("p1000", 1, "дев'яносто"), ("lion", 1, "тридцять"), ("news", 1, "п'ять")):
        sfx.append(("pop", ab(sid, wt(sid, ln, w) - 0.05), 0.55))
    for w in ("Злий", "Залізна", "Людина-павук", "Ванда", "Немор", "Тор"):
        sfx.append(("whoosh-short", ab("figs", wt("figs", 0, w) - (0.45 if w in ("Ванда", "Тор") else 0.08)), 0.35))
    sfx.append(("sparkle", ab("news", lt("news", 1)), 0.5))
    sfx.append(("impact-bass-1", ab("outro", lt("outro", 1) - 0.1), 0.6))
    audio = [f'      <audio id="vo" src="assets/audio/voice.mp3" data-start="0" data-duration="{DUR}" data-track-index="20" data-volume="1"></audio>']
    if os.path.exists(f"{P}/assets/audio/music.mp3"):
        audio.append(f'      <audio id="bgm" src="assets/audio/music.mp3" data-start="0" data-duration="{DUR}" data-track-index="19" data-volume="0.14" data-fade-in="0.5" data-fade-out="1.5"></audio>')
    for i, (f, t, v) in enumerate(sfx):
        audio.append(f'      <audio id="sfx{i}" src="assets/sfx/{f}.mp3" data-start="{max(0, t)}" data-duration="{adur(f)}" data-track-index="{21+i}" data-volume="{v}"></audio>')
    idx = f"""<!doctype html>
<html lang="uk">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={W}, height={H}" />
    <title>LEGO NEWS UA — Shorts: витоки LEGO 2027</title>
    <script src="assets/vendor/gsap.min.js"></script>
    <style>
      * {{ margin:0; padding:0; box-sizing:border-box; }}
      html, body {{ margin:0; width:{W}px; height:{H}px; overflow:hidden; background:#0b0b0d; }}
      #root {{ position:relative; width:{W}px; height:{H}px; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{DUR}" data-width="{W}" data-height="{H}" data-motion-blur="on" data-motion-blur-shutter="220">
{chr(10).join(hosts)}
      <div id="chrome" data-composition-id="chrome" data-composition-src="compositions/chrome.html" data-start="0" data-duration="{DUR}" data-track-index="10" data-track-kind="graphics" data-width="{W}" data-height="{H}" style="z-index:20"></div>
      <div id="captions" data-composition-id="captions" data-composition-src="compositions/captions.html" data-start="0" data-duration="{DUR}" data-track-index="11" data-track-kind="captions" data-width="{W}" data-height="{H}" style="z-index:30"></div>
{chr(10).join(audio)}
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      window.__timelines["main"] = gsap.timeline({{ paused: true }});
    </script>
  </body>
</html>
"""
    open(f"{P}/index.html", "w").write(idx)
    print("built", len(files) + 2, "compositions,", len(sfx), "sfx,", DUR, "s")

main()
