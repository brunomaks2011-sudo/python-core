"""LEGO NEWS UA — генератор проєкту HyperFrames.

Reads script/timeline.json (voice timing), script/caption_groups.json and the scene
config below, and writes index.html + compositions/*.html. The generated HTML is plain,
editable HyperFrames source: you can edit it by hand or in the HyperFrames desktop app,
or change this file / script.json and run:  python3 script/tts.py && python3 script/caps.py && python3 script/build.py
"""
import json, os, html, re

P = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TL = json.load(open(f"{P}/script/timeline.json"))
CAPS = json.load(open(f"{P}/script/caption_groups.json"))
SC = {s["id"]: s for s in TL["scenes"]}
DUR = round(TL["duration"], 2)
ISSUE_DATE = "06.11.2026"
SRC = "https://t.me/thestudledger"

E = html.escape

# ---------------------------------------------------------------- helpers
def rel(sid, t):  # absolute -> scene-local seconds
    return round(t - SC[sid]["start"], 3)

def line_t(sid, i):
    return rel(sid, SC[sid]["lines"][i]["start"])

def word_t(sid, i, needle, nth=0):
    """time (scene-local) of the nth tts word in line i that contains needle"""
    hits = [w for w in SC[sid]["lines"][i]["words"] if w["text"].lower().strip("—–-.,!?:«»").startswith(needle.lower())]
    return rel(sid, hits[nth]["start"])

def scene_len(sid):
    return round(SC[sid]["end"] - SC[sid]["start"], 3)

def fmt_num(n):
    return f"{n:,}".replace(",", " ")

FONTS = """
@font-face{font-family:'LNU Display';font-weight:700;src:url('assets/fonts/montserrat-latin-700-normal.woff2') format('woff2');unicode-range:U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+20AC,U+2122,U+2212,U+FEFF;}
@font-face{font-family:'LNU Display';font-weight:700;src:url('assets/fonts/montserrat-cyrillic-700-normal.woff2') format('woff2');unicode-range:U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116;}
@font-face{font-family:'LNU Display';font-weight:800;src:url('assets/fonts/montserrat-latin-800-normal.woff2') format('woff2');unicode-range:U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+20AC,U+2122,U+2212,U+FEFF;}
@font-face{font-family:'LNU Display';font-weight:800;src:url('assets/fonts/montserrat-cyrillic-800-normal.woff2') format('woff2');unicode-range:U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116;}
@font-face{font-family:'LNU Display';font-weight:900;src:url('assets/fonts/montserrat-latin-900-normal.woff2') format('woff2');unicode-range:U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+20AC,U+2122,U+2212,U+FEFF;}
@font-face{font-family:'LNU Display';font-weight:900;src:url('assets/fonts/montserrat-cyrillic-900-normal.woff2') format('woff2');unicode-range:U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116;}
@font-face{font-family:'LNU Text';font-weight:500;src:url('assets/fonts/inter-latin-500-normal.woff2') format('woff2');unicode-range:U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+20AC,U+2122,U+2212,U+FEFF;}
@font-face{font-family:'LNU Text';font-weight:500;src:url('assets/fonts/inter-cyrillic-500-normal.woff2') format('woff2');unicode-range:U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116;}
@font-face{font-family:'LNU Text';font-weight:600;src:url('assets/fonts/inter-latin-600-normal.woff2') format('woff2');unicode-range:U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+20AC,U+2122,U+2212,U+FEFF;}
@font-face{font-family:'LNU Text';font-weight:600;src:url('assets/fonts/inter-cyrillic-600-normal.woff2') format('woff2');unicode-range:U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116;}
@font-face{font-family:'LNU Text';font-weight:700;src:url('assets/fonts/inter-latin-700-normal.woff2') format('woff2');unicode-range:U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+20AC,U+2122,U+2212,U+FEFF;}
@font-face{font-family:'LNU Text';font-weight:700;src:url('assets/fonts/inter-cyrillic-700-normal.woff2') format('woff2');unicode-range:U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116;}
"""

TOKENS = """
:root{--red:#E3000B;--red-deep:#A8000A;--yellow:#FFD500;--white:#FFFFFF;--black:#0B0B0D;--ink:#141416;
--official:#15803D;--leak:#C2410C;--rumor:#1D4ED8;}
"""

STATUS = {
    "OFFICIAL": ("OFFICIAL", "Офіційно", "var(--official)"),
    "LEAK": ("LEAK", "Витік", "var(--leak)"),
    "RUMOR": ("RUMOR", "Чутка", "var(--rumor)"),
}

def scene_file(cid, dur, css, body, js, extra_attrs=""):
    return f"""<template>
  <style>
{FONTS}{TOKENS}
    #root {{ position:absolute; inset:0; overflow:hidden; font-family:'LNU Text',sans-serif; color:var(--white); }}
    #root .bg {{ position:absolute; inset:0; background:
        radial-gradient(1200px 700px at 78% 20%, rgba(227,0,11,.38), transparent 60%),
        radial-gradient(900px 600px at 10% 100%, rgba(255,213,0,.10), transparent 60%),
        linear-gradient(160deg,#18181b 0%,#0b0b0d 70%); }}
    #root .studs {{ position:absolute; inset:-60px; opacity:.07;
        background-image: radial-gradient(circle at 30px 30px, #fff 0 13px, transparent 14px);
        background-size:60px 60px; }}
{css}
  </style>
  <div id="root" data-composition-id="{cid}" data-width="1920" data-height="1080" data-duration="{dur}"{extra_attrs}>
    <div class="bg"></div>
    <div class="studs" data-layout-ignore></div>
{body}
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
    const fmt = (v) => Math.round(v).toLocaleString('en-US').replace(/,/g, '\\u2009');
    tl.fromTo('#root .studs', {{ x: 0, y: 0 }}, {{ x: -60, y: -60, duration: {dur}, ease: 'none' }}, 0);
{js}
    window.__timelines["{cid}"] = tl;
  </script>
</template>
"""

# ---------------------------------------------------------------- set scene (photos + card)
SET_CSS = """
    #root .stage { position:absolute; left:192px; top:176px; width:960px; height:680px; border-radius:28px;
        background:#fff; overflow:hidden; box-shadow:0 30px 80px rgba(0,0,0,.55), 0 0 0 6px var(--yellow); }
    #root .ph { position:absolute; inset:0; }
    #root .ph img { position:absolute; inset:0; width:100%; height:100%; object-fit:contain; }
    #root .ph-src { position:absolute; right:18px; bottom:14px; padding:6px 12px; border-radius:8px; background:rgba(11,11,13,.78);
        font:600 28px 'LNU Text'; color:#fff; letter-spacing:.01em; }
    #root .card { position:absolute; left:1196px; top:176px; width:532px; height:680px; }
    #root .badge { display:inline-flex; align-items:center; gap:12px; padding:10px 20px 10px 16px; border-radius:999px;
        font:900 28px 'LNU Display'; letter-spacing:.12em; color:#fff; }
    #root .badge i { width:16px; height:16px; border-radius:50%; background:#fff; display:block; }
    #root .badge small { font:700 28px 'LNU Text'; letter-spacing:.02em; opacity:.92; text-transform:none; }
    #root .theme { margin-top:22px; font:800 28px 'LNU Display'; letter-spacing:.1em; color:var(--yellow); text-transform:uppercase; }
    #root .num { margin-top:4px; font:900 118px/1 'LNU Display'; color:#fff; letter-spacing:-.02em; }
    #root .name { margin-top:10px; font:800 44px/1.08 'LNU Display'; color:#fff; }
    #root .stats { position:absolute; left:0; right:0; bottom:0; display:flex; flex-direction:column; gap:14px; }
    #root .stat { display:flex; align-items:center; gap:18px; height:84px; padding:0 22px; border-radius:18px; background:rgba(255,255,255,.07);
        border:1px solid rgba(255,255,255,.12); }
    #root .stat .ico { width:54px; height:54px; flex:none; border-radius:12px; display:grid; place-items:center; }
    #root .stat .lbl { font:600 26px 'LNU Text'; color:rgba(255,255,255,.75); width:150px; }
    #root .stat .val { font:900 44px 'LNU Display'; color:#fff; font-variant-numeric:tabular-nums; white-space:nowrap; }
    #root .stat .val small { font:700 28px 'LNU Text'; color:var(--yellow); margin-left:10px; }
    #root .ico-brick { background:var(--red); position:relative; }
    #root .ico-brick::before, #root .ico-brick::after { content:''; position:absolute; top:-7px; width:16px; height:9px; border-radius:4px 4px 0 0; background:var(--red); }
    #root .ico-brick::before { left:9px; } #root .ico-brick::after { right:9px; }
    #root .price .ico { background:var(--yellow); color:var(--black); font:900 30px 'LNU Display'; }
    #root .date .ico { background:#fff; color:var(--red); font:900 15px 'LNU Display'; flex-direction:column; line-height:1; }
    #root .warn { position:absolute; left:216px; top:200px; z-index:60; box-shadow:0 10px 24px rgba(0,0,0,.35); padding:8px 16px; border-radius:10px; background:var(--yellow); color:var(--black);
        font:800 28px 'LNU Display'; letter-spacing:.02em; }
"""

def ken(i):
    # deterministic Ken Burns variety: (scale from, scale to, x from, x to, y from, y to)
    pats = [(1.0, 1.12, -10, 10, 0, -8), (1.14, 1.02, 14, -6, -6, 6), (1.02, 1.16, 0, -16, 10, -4), (1.12, 1.0, -14, 12, 4, 0)]
    return pats[i % len(pats)]

def photos_html(sid, photos, t0, t1, pref):
    """photos spread across [t0,t1); each a timed .clip; returns (html, js)"""
    n = len(photos); seg = (t1 - t0) / n; h = []; j = []
    for i, ph in enumerate(photos):
        if isinstance(ph, dict):
            src, s, e = ph["src"], ph["t0"], ph["t1"]
        else:
            src, s, e = ph, t0 + i * seg, t0 + (i + 1) * seg
        s = round(max(0, s - (0.0 if i == 0 else 0.5)), 3); d = round(e - s + (0.0 if i == n - 1 else 0.02), 3)
        pid = f"{pref}{i+1}"
        tag = ""
        h.append(f'      <div id="{pid}" class="ph clip" data-start="{s}" data-duration="{d}" data-track-index="{2+i%2}" style="z-index:{i+1}">'
                 f'<img id="{pid}-img" src="assets/photos/{src}" alt="">{tag}</div>')
        a, b, x0, x1, y0, y1 = ken(i)
        j.append(f"    tl.fromTo('#{pid}-img', {{scale:{a}, x:{x0}, y:{y0}}}, {{scale:{b}, x:{x1}, y:{y1}, duration:{d}, ease:'sine.inOut'}}, {s});")
        if i > 0:
            j.append(f"    tl.fromTo('#{pid}', {{opacity:0}}, {{opacity:1, duration:0.5, ease:'power2.out'}}, {s});")
    return "\n".join(h), "\n".join(j)

def card_html(cid, c, s, d):
    st = STATUS[c["status"]]
    stats = []
    if c.get("pieces") is not None:
        note = f'<small>{E(c["pieces_note"])}</small>' if c.get("pieces_note") else ""
        stats.append(f'<div class="stat pieces"><div class="ico ico-brick"></div><div class="lbl">Деталей</div>'
                     f'<div class="val"><span id="{cid}-pcs">0</span>{note}</div></div>')
    if c.get("price"):
        stats.append(f'<div class="stat price"><div class="ico">€</div><div class="lbl">Ціна</div><div class="val">{E(c["price"])}</div></div>')
    if c.get("date"):
        dd, mm = (c.get("date_ico") or ("01", "СІЧ"))
        stats.append(f'<div class="stat date"><div class="ico" data-layout-ignore><b>{dd}</b><span>{mm}</span></div><div class="lbl">Вихід</div><div class="val">{E(c["date"])}</div></div>')
    stats_html = "".join(f'<div id="{cid}-st{k}">{x}</div>' for k, x in enumerate(stats))
    return (f'      <div id="{cid}" class="card clip" data-start="{s}" data-duration="{d}" data-track-index="5">\n'
            f'        <div id="{cid}-badge" class="badge" style="background:{st[2]}"><i></i>{st[0]} <small>· {st[1]}</small></div>\n'
            f'        <div id="{cid}-theme" class="theme">{E(c["theme"])}</div>\n'
            f'        <div id="{cid}-num" class="num">{E(c["num"])}</div>\n'
            f'        <div id="{cid}-name" class="name">{E(c["name"])}</div>\n'
            f'        <div class="stats">{stats_html}</div>\n'
            f'      </div>'), len(stats)

def card_js(cid, c, s, nstats):
    q = 0.35 if c.get('at') else 1.0
    j = [f"    tl.fromTo('#{cid}-badge', {{x:-40, opacity:0}}, {{x:0, opacity:1, duration:0.45, ease:'back.out(2)'}}, {s+0.25});",
         f"    tl.fromTo('#{cid}-theme', {{y:18, opacity:0}}, {{y:0, opacity:1, duration:0.4, ease:'power3.out'}}, {s+0.4});",
         f"    tl.fromTo('#{cid}-num', {{y:50, opacity:0, rotationX:-70, transformPerspective:800}}, {{y:0, opacity:1, rotationX:0, duration:0.7, ease:'power4.out'}}, {s+0.5});",
         f"    tl.fromTo('#{cid}-name', {{y:24, opacity:0}}, {{y:0, opacity:1, duration:0.5, ease:'power3.out'}}, {s+0.7});"]
    for k in range(nstats):
        j.append(f"    tl.fromTo('#{cid}-st{k}', {{x:60, opacity:0}}, {{x:0, opacity:1, duration:0.45, ease:'power3.out'}}, {round(s+q+k*0.15,3)});")
    if c.get("pieces") is not None:
        j.append(f"    {{ const o={{v:0}}, el=document.querySelector('#{cid}-pcs'); tl.fromTo(o, {{v:0}}, {{v:{c['pieces']}, duration:1.4, ease:'power2.out', onUpdate:()=>{{el.textContent=fmt(o.v);}}}}, {round(s+q,3)}); }}")
    return "\n".join(j)

def build_set(sid, cfg):
    L = scene_len(sid); body = []; js = []
    ph_h, ph_j = photos_html(sid, cfg["photos"], 0, L, f"{sid}-p")
    posts = sorted({re.match(r'(\d+)_', (p if isinstance(p, str) else p['src'])).group(1) for p in cfg['photos'] if re.match(r'\d+_', (p if isinstance(p, str) else p['src']))})
    srct = 'Фото: The Stud Ledger · t.me/thestudledger/' + ', '.join(posts)
    body.append(f'    <div id="{sid}-stage" class="stage" data-layout-allow-overflow>\n{ph_h}\n      <div id="{sid}-src" class="ph-src" style="z-index:50">{E(srct)}</div>\n    </div>')
    js.append(f"    tl.fromTo('#{sid}-stage', {{x:-160, rotationY:28, opacity:0, transformPerspective:1400}}, {{x:0, rotationY:0, opacity:1, duration:0.9, ease:'power4.out'}}, 0.15);")
    js.append(ph_j)
    cards = cfg["cards"]
    for k, c in enumerate(cards):
        s = 0 if k == 0 else round(c["at"], 3)
        e = L if k == len(cards) - 1 else round(cards[k + 1]["at"], 3)
        cid = f"{sid}-c{k+1}"
        h, n = card_html(cid, c, s, round(e - s, 3))
        body.append(h); js.append(card_js(cid, c, s, n))
        if k > 0:
            js.append(f"    tl.fromTo('#{cid}', {{opacity:0}}, {{opacity:1, duration:0.3}}, {s});")
    if cfg.get("warn"):
        w = cfg["warn"]
        body.append(f'    <div id="{sid}-warn" class="warn clip" data-start="{w["at"]}" data-duration="{round(L-w["at"],3)}" data-track-index="6">⚠ {E(w["text"])}</div>')
        js.append(f"    tl.fromTo('#{sid}-warn', {{scale:0.6, opacity:0}}, {{scale:1, opacity:1, duration:0.45, ease:'back.out(2.4)'}}, {w['at']});")
    return scene_file(sid, L, SET_CSS, "\n".join(body), "\n".join(js))

# ---------------------------------------------------------------- scene configs
def T(sid, i, w, nth=0): return word_t(sid, i, w, nth)

JAN = "01.01.2027"; NOV = ("27", "ЛИС")
SETS = {
    "godzilla": {"photos": ["5924_1.jpg", "5924_4.jpg", "5924_3.jpg", "5924_6.jpg", "5924_5.jpg", "5924_2.jpg"],
                 "cards": [dict(status="OFFICIAL", theme="LEGO Ideas", num="21375", name="Ґодзіла", pieces=5363, price="400 €", date="27.11.2026", date_ico=NOV)]},
    "gwp40888": {"photos": ["5921_1.jpg", "5921_3.jpg", "5921_2.jpg"],
                 "cards": [dict(status="OFFICIAL", theme="Подарунковий набір", num="40888", name="Логотип і слід Ґодзіли", pieces=359, price="Подарунок", date="27.11.2026", date_ico=NOV)]},
    "ninjago": {"photos": ["5949_1.jpg", "5949_3.jpg", "5949_5.jpg", "5949_4.jpg", "5949_2.jpg"],
                "cards": [dict(status="LEAK", theme="LEGO Ninjago", num="71888", name="Додзьо Іво", pieces=3495, price="280 €", date=JAN)]},
    "cny80123": {"photos": ["5964_1.jpg", "5964_3.jpg", "5964_4.jpg", "5964_6.jpg", "5964_5.jpg", "5964_2.jpg"],
                 "cards": [dict(status="LEAK", theme="Китайський Новий рік", num="80123", name="Подорож на весняне свято", pieces=1529, price="100 €", date=JAN)]},
    "cny80122": {"photos": ["5959_1.jpg", "5959_2.jpg", "5959_3.jpg", "5959_4.jpg", "5959_5.jpg"],
                 "cards": [dict(status="LEAK", theme="Китайський Новий рік", num="80122", name="Сприятлива Піксіу під деревом Щастя", pieces=829, pieces_note="/ 879?", price="70 €", date=JAN)]},
    "tacos": {"photos": ["5932_1.jpg", "5932_3.jpg", "5932_4.jpg", "5916_3.jpg", "5916_4.jpg", "5911_2.jpg", "5932_2.jpg"],
              "cards": [dict(status="LEAK", theme="LEGO Fortnite", num="77088", name="Такос Гуакос", pieces=193, price="20 €", date=JAN)]},
    "p1000": {"photos": ["5936_1.jpg", "5936_3.jpg", "5936_4.jpg", "5916_1.jpg", "5916_2.jpg", "5936_5.jpg", "5936_2.jpg"],
              "cards": [dict(status="LEAK", theme="LEGO Fortnite", num="77084", name="P-1000", pieces=1103, price="90 €", date=JAN)]},
    "lion": {"photos": ["5955_1.jpg", "5955_3.jpg", "5955_4.jpg", "5955_2.jpg"],
             "cards": [dict(status="LEAK", theme="Китайський Новий рік", num="40976", name="Лев процвітання", pieces=411, price="30 €", date=JAN)]},
    "sanctum": {"photos": ["5897_1.jpg", "5897_3.jpg", "5897_4.jpg", "5897_2.jpg"],
                "cards": [dict(status="LEAK", theme="LEGO Marvel · What If…?", num="67005", name="Дивний Верховний Санктум", pieces=814, price="100 €", date=JAN)]},
    "torso": {"photos": ["5930_1.jpg", "5930_2.jpg"],
              "cards": [dict(status="LEAK", theme="LEGO Marvel", num="67002", name="Мех Червоного Павука", pieces=146, pieces_note="(ранні)", date="січень 2027", date_ico=("01", "2027"))]},
}

def late_cfg():
    b = "botanicals"; f = "firstlook"; d = "figdetails"
    SETS[b] = {"photos": [{"src": "5941_1.jpg", "t0": 0, "t1": T(b, 1, "Пастельн") - 0.1 + 0.0},
                          {"src": "5941_2.jpg", "t0": T(b, 1, "Пастельн") - 0.1, "t1": T(b, 1, "півоній") - 0.4},
                          {"src": "5941_3.jpg", "t0": T(b, 1, "півоній") - 0.4, "t1": T(b, 1, "орхідея") - 0.4},
                          {"src": "5941_5.jpg", "t0": T(b, 1, "орхідея") - 0.4, "t1": T(b, 1, "сакури") - 0.4},
                          {"src": "5941_7.jpg", "t0": T(b, 1, "сакури") - 0.4, "t1": T(b, 2, "Цін") - 0.2},
                          {"src": "5941_8.jpg", "t0": T(b, 2, "Цін") - 0.2, "t1": scene_len(b)}],
                "cards": [dict(status="LEAK", theme="LEGO Botanicals", num="11522", name="Пастельний букет", pieces=650, price="невідома", date="січ–лют 2027"),
                          dict(at=T(b, 1, "півоній") - 0.4, status="LEAK", theme="LEGO Botanicals", num="11515", name="Букет півоній", pieces=633, price="невідома", date="січ–лют 2027"),
                          dict(at=T(b, 1, "орхідея") - 0.4, status="LEAK", theme="LEGO Botanicals", num="11519", name="Дика орхідея", pieces=606, price="невідома", date="січ–лют 2027"),
                          dict(at=T(b, 1, "сакури") - 0.4, status="LEAK", theme="LEGO Botanicals", num="11516", name="Гілки сакури", pieces=405, price="невідома", date="січ–лют 2027")]}
    a1 = line_t(f, 1) - 0.2
    SETS[f] = {"photos": [{"src": "5911_4.jpg", "t0": 0, "t1": a1}, {"src": "5920_1.jpg", "t0": a1, "t1": scene_len(f)}],
               "cards": [dict(status="LEAK", theme="LEGO Technic", num="42254", name="Планети Сонячної системи на орбіті", pieces=572, price="невідома", date="невідомо", date_ico=("?", "")),
                         dict(at=a1, status="LEAK", theme="Подарунковий набір", num="40914", name="Ретро-музичний автомат", pieces=287, price="Подарунок", date="невідомо", date_ico=("?", ""))]}
    a2 = line_t(d, 1) - 0.2
    SETS[d] = {"photos": [{"src": "5949_6.jpg", "t0": 0, "t1": a2}, {"src": "5915_1.jpg", "t0": a2, "t1": scene_len(d)}],
               "cards": [dict(status="LEAK", theme="Мініфігурки · Ninjago", num="71888", name="Команда Додзьо Іво"),
                         dict(at=a2, status="LEAK", theme="Мініфігурка · Fortnite", num="77084", name="Мініфігурка з P-1000")]}
    SETS["cny80122"]["warn"] = {"at": T("cny80122", 1, "розбіжн"), "text": "Розбіжність: 829 у дописі / 879 на коробці"}

# ---------------------------------------------------------------- special scenes
def build_intro():
    sid = "intro"; L = scene_len(sid)
    css = """
    #root .brick { position:absolute; width:240px; height:96px; border-radius:10px; }
    #root .brick::before { content:''; position:absolute; left:18px; right:18px; top:-26px; height:28px;
        background:radial-gradient(circle at 24px 14px, var(--c) 0 17px, transparent 18px) 0 0/50px 28px repeat-x; }
    #root .brick { background:linear-gradient(180deg, color-mix(in srgb, var(--c), #fff 14%), var(--c) 40%, color-mix(in srgb, var(--c), #000 22%)); box-shadow:inset 0 -8px 0 rgba(0,0,0,.18), 0 18px 30px rgba(0,0,0,.45); }
    #root .logo { position:absolute; left:0; right:0; top:330px; text-align:center; }
    #root .logo-box { display:inline-block; padding:28px 60px 30px; border-radius:26px; background:var(--red); box-shadow:0 0 0 10px var(--yellow), 0 40px 90px rgba(0,0,0,.6); }
    #root .logo-l1 { font:900 150px/0.95 'LNU Display'; color:#fff; letter-spacing:-.02em; -webkit-text-stroke:4px #000; paint-order:stroke fill; }
    #root .logo-l2 { margin-top:6px; font:900 64px/1 'LNU Display'; color:var(--yellow); letter-spacing:.32em; padding-left:.32em; }
    #root .tag { position:absolute; left:0; right:0; top:744px; text-align:center; font:800 34px 'LNU Display'; letter-spacing:.2em; color:#fff; text-transform:uppercase; }
    #root .tag b { color:var(--yellow); }
    #root .flash { position:absolute; inset:0; background:#fff; opacity:0; }
"""
    cols = ["var(--red)", "var(--yellow)", "#ffffff", "#1f1f23", "var(--red)", "var(--yellow)", "#2563EB", "var(--red)", "#ffffff", "var(--yellow)", "#1f1f23", "var(--red)"]
    pos = [(150, 820), (420, 820), (690, 820), (960, 820), (1230, 820), (1500, 820), (285, 690), (555, 690), (825, 690), (1095, 690), (1365, 690), (1635, 690)]
    body = []; js = []
    for i, ((x, y), c) in enumerate(zip(pos, cols)):
        body.append(f'    <div id="ib{i}" class="brick" style="left:{x}px;top:{y+60}px;--c:{c}"></div>')
        js.append(f"    tl.fromTo('#ib{i}', {{y:-1100, rotation:{(-8 + (i*7)%17)}}}, {{y:0, rotation:0, duration:0.55, ease:'bounce.out'}}, {round(0.08*i,2)});")
    for i in range(12):
        js.append(f"    tl.to('#ib{i}', {{y:620, opacity:0, duration:0.6, ease:'power3.in'}}, {round(1.55+0.03*i,2)});")
    body.append('    <div id="i-flash" class="flash"></div>')
    body.append('    <div class="logo"><div id="i-logo" class="logo-box"><div class="logo-l1">LEGO NEWS</div><div class="logo-l2">UA</div></div></div>')
    body.append(f'    <div id="i-tag" class="tag">Щотижневий випуск · <b>{ISSUE_DATE}</b></div>')
    js += ["    tl.fromTo('#i-flash', {opacity:0}, {opacity:0.85, duration:0.08}, 1.9);",
           "    tl.to('#i-flash', {opacity:0, duration:0.5, ease:'power2.out'}, 1.98);",
           "    tl.fromTo('#i-logo', {scale:0.2, rotationX:80, opacity:0, transformPerspective:900}, {scale:1, rotationX:0, opacity:1, duration:0.9, ease:'back.out(1.6)'}, 1.9);",
           "    tl.fromTo('#i-tag', {y:30, opacity:0}, {y:0, opacity:1, duration:0.6, ease:'power3.out'}, 2.6);",
           f"    tl.fromTo('#i-logo', {{scale:1}}, {{scale:1.06, duration:{round(L-3,2)}, ease:'sine.inOut'}}, 2.8);",
           f"    tl.to('#i-logo, #i-tag', {{y:-40, opacity:0, duration:0.4, ease:'power2.in'}}, {round(L-0.5,2)});"]
    return scene_file(sid, L, css, "\n".join(body), "\n".join(js))

def build_block(sid, n, title, sub):
    L = scene_len(sid)
    css = """
    #root .bg { background: linear-gradient(135deg, var(--red) 0%, var(--red-deep) 100%); }
    #root .studs { opacity:.16; }
    #root .bn { position:absolute; left:192px; top:300px; font:900 64px 'LNU Display'; letter-spacing:.3em; color:var(--yellow); }
    #root .bt { position:absolute; left:192px; right:192px; top:390px; font:900 128px/1.0 'LNU Display'; color:#fff; letter-spacing:-.02em; text-shadow:0 10px 0 rgba(0,0,0,.25); }
    #root .bs { position:absolute; left:192px; top:690px; font:700 34px 'LNU Text'; color:rgba(255,255,255,.88); }
    #root .bar { position:absolute; left:192px; top:270px; width:220px; height:12px; background:var(--yellow); transform-origin:left center; }
    #root .big { position:absolute; right:150px; top:150px; font:900 640px/1 'LNU Display'; color:rgba(0,0,0,.16); }
"""
    body = f"""    <div id="{sid}-big" class="big" data-layout-ignore>{n}</div>
    <div id="{sid}-bar" class="bar"></div>
    <div id="{sid}-n" class="bn">БЛОК {n}</div>
    <div id="{sid}-t" class="bt">{E(title)}</div>
    <div id="{sid}-s" class="bs">{E(sub)}</div>"""
    js = f"""    tl.fromTo('#{sid}-big', {{x:200, opacity:0}}, {{x:0, opacity:1, duration:0.8, ease:'power4.out'}}, 0.05);
    tl.fromTo('#{sid}-bar', {{scaleX:0}}, {{scaleX:1, duration:0.5, ease:'power3.out'}}, 0.2);
    tl.fromTo('#{sid}-n', {{x:-60, opacity:0}}, {{x:0, opacity:1, duration:0.5, ease:'power3.out'}}, 0.3);
    tl.fromTo('#{sid}-t', {{y:70, opacity:0, rotationX:-50, transformPerspective:900}}, {{y:0, opacity:1, rotationX:0, duration:0.75, ease:'power4.out'}}, 0.45);
    tl.fromTo('#{sid}-s', {{y:20, opacity:0}}, {{y:0, opacity:1, duration:0.5, ease:'power2.out'}}, 0.85);
    tl.fromTo('#{sid}-big', {{scale:1}}, {{scale:1.08, duration:{L}, ease:'none'}}, 0);"""
    return scene_file(sid, L, css, body, js)

def build_top():
    sid = "top"; L = scene_len(sid)
    tiles = [("5924_6.jpg", "OFFICIAL", "Ґодзіла · 5363 дет.", 0.4),
             ("5964_3.jpg", "LEAK", "Новий рік · 3 набори", T(sid, 1, "Китайськ")),
             ("5949_3.jpg", "LEAK", "Ninjago · Додзьо Іво", T(sid, 1, "Ніндзяго")),
             ("5932_3.jpg", "LEAK", "Fortnite · Такос Гуакос", T(sid, 1, "Фортнайт")),
             ("5936_3.jpg", "LEAK", "Fortnite · P-1000", T(sid, 1, "дивакуват")),
             ("5897_3.jpg", "LEAK", "Marvel · Санктум", T(sid, 2, "Усі") - 0.6)]
    css = """
    #root .head { position:absolute; left:192px; top:150px; font:900 60px 'LNU Display'; color:#fff; }
    #root .head b { color:var(--yellow); }
    #root .tile { position:absolute; width:500px; height:300px; border-radius:20px; overflow:hidden; background:#fff; box-shadow:0 20px 50px rgba(0,0,0,.5); }
    #root .tile img { position:absolute; inset:0; width:100%; height:100%; object-fit:contain; }
    #root .tile .cap { position:absolute; left:0; right:0; bottom:0; padding:12px 16px; background:linear-gradient(0deg, rgba(11,11,13,.92), rgba(11,11,13,.0)); font:800 28px 'LNU Display'; color:#fff; }
    #root .tile .st { position:absolute; left:14px; top:14px; padding:5px 12px; border-radius:999px; font:900 28px 'LNU Display'; letter-spacing:.1em; color:#fff; }
    #root .src { position:absolute; left:192px; top:892px; font:700 26px 'LNU Text'; color:rgba(255,255,255,.85); }
"""
    pos = [(192, 250), (710, 250), (1228, 250), (192, 570), (710, 570), (1228, 570)]
    body = ['    <div id="top-head" class="head">Головне за <b>тиждень</b></div>']; js = ["    tl.fromTo('#top-head', {x:-80, opacity:0}, {x:0, opacity:1, duration:0.6, ease:'power4.out'}, 0.1);"]
    for i, ((x, y), (src, st, cap, at)) in enumerate(zip(pos, tiles)):
        body.append(f'    <div id="tt{i}" class="tile" style="left:{x}px;top:{y}px"><img id="tt{i}-img" src="assets/photos/{src}" alt="">'
                    f'<div class="st" style="background:{STATUS[st][2]}">{st}</div><div class="cap">{E(cap)}</div></div>')
        at = round(at, 2)
        js.append(f"    tl.fromTo('#tt{i}', {{scale:0.5, rotationY:-60, opacity:0, transformPerspective:1200}}, {{scale:1, rotationY:0, opacity:1, duration:0.7, ease:'back.out(1.5)'}}, {at});")
        js.append(f"    tl.fromTo('#tt{i}-img', {{scale:1.0}}, {{scale:1.12, duration:{round(L-at,2)}, ease:'none'}}, {at});")
    return scene_file(sid, L, css, "\n".join(body), "\n".join(js))

def build_figs():
    sid = "figs"; L = scene_len(sid)
    names = [("Злий Доктор Стрендж", "Злий"), ("Залізна Людина", "Залізна"), ("Людина-павук", "Людина-павук"),
             ("Зомбі Ванда", "Ванда"), ("Немор", "Немор"), ("Зомбі Тор", "Тор")]
    times = []
    for k, (nm, w) in enumerate(names):
        t = T(sid, 0, w) - (0.55 if w in ("Ванда", "Тор") else 0.15)
        times.append(round(t, 3))
    g0 = round(line_t(sid, 1) - 0.25, 3); n0 = round(line_t(sid, 2) - 0.25, 3)
    css = """
    #root .head { position:absolute; left:192px; top:150px; font:900 56px 'LNU Display'; color:#fff; }
    #root .head b { color:var(--yellow); }
    #root .hs { position:absolute; left:192px; top:222px; font:700 28px 'LNU Text'; color:rgba(255,255,255,.75); }
    #root .slot { position:absolute; top:290px; width:240px; height:440px; border-radius:22px; background:#fff; overflow:hidden; box-shadow:0 20px 50px rgba(0,0,0,.5); }
    #root .slot img { position:absolute; left:0; top:20px; width:100%; height:350px; object-fit:contain; }
    #root .slot .nm { position:absolute; left:0; right:0; bottom:0; height:76px; display:flex; align-items:center; justify-content:center; text-align:center; padding:0 10px;
        background:var(--red); font:800 28px/1.05 'LNU Display'; color:#fff; }
    #root .slot .ix { position:absolute; left:12px; top:10px; font:900 26px 'LNU Display'; color:var(--red); }
    #root .hero { position:absolute; left:192px; top:176px; width:1536px; height:680px; border-radius:28px; background:#fff; overflow:hidden; box-shadow:0 30px 80px rgba(0,0,0,.55), 0 0 0 6px var(--yellow); }
    #root .hero img { position:absolute; inset:0; width:100%; height:100%; object-fit:contain; }
    #root .hero .six { position:absolute; left:40px; top:30px; padding:10px 24px; border-radius:14px; background:var(--red); font:900 48px 'LNU Display'; color:#fff; }
    #root .hero .src { position:absolute; right:18px; bottom:14px; padding:6px 12px; border-radius:8px; background:rgba(11,11,13,.78); font:600 24px 'LNU Text'; color:#fff; }
    #root .note { position:absolute; left:192px; top:176px; width:1536px; height:680px; }
    #root .note .np { position:absolute; left:0; top:0; width:760px; height:680px; border-radius:28px; background:#111; overflow:hidden; box-shadow:0 0 0 6px var(--yellow); }
    #root .note .np img { position:absolute; inset:0; width:100%; height:100%; object-fit:contain; }
    #root .note .nt { position:absolute; left:820px; top:20px; right:0; }
    #root .note .nt h3 { font:900 46px/1.1 'LNU Display'; color:var(--yellow); }
    #root .note .nt p { margin-top:22px; font:600 31px/1.35 'LNU Text'; color:#fff; }
    #root .note .nt .tagx { display:inline-block; margin-top:26px; padding:8px 18px; border-radius:999px; background:var(--leak); font:900 28px 'LNU Display'; letter-spacing:.1em; }
"""
    body = [f'    <div id="figs-grid" class="clip" data-start="0" data-duration="{g0}" data-track-index="2" style="position:absolute;inset:0">',
            '      <div id="figs-head" class="head">67005 · <b>шість мініфігурок</b></div>',
            '      <div id="figs-hs" class="hs">Фото: The Stud Ledger · t.me/thestudledger/5897</div>']
    js = ["    tl.fromTo('#figs-head', {x:-80, opacity:0}, {x:0, opacity:1, duration:0.6, ease:'power4.out'}, 0.15);",
          "    tl.fromTo('#figs-hs', {opacity:0}, {opacity:1, duration:0.5}, 0.5);"]
    for k, ((nm, _), t) in enumerate(zip(names, times)):
        x = 192 + k * 259
        body.append(f'      <div id="fs{k}" class="slot" style="left:{x}px"><div class="ix">{k+1}</div><img id="fs{k}-img" src="assets/photos/fig{k+1}.png" alt=""><div id="fs{k}-nm" class="nm">{E(nm)}</div></div>')
        js.append(f"    tl.fromTo('#fs{k}', {{y:80, opacity:0, rotationY:-70, transformPerspective:1000}}, {{y:0, opacity:1, rotationY:0, duration:0.55, ease:'back.out(1.7)'}}, {t});")
        js.append(f"    tl.fromTo('#fs{k}-img', {{scale:1.25}}, {{scale:1, duration:0.9, ease:'power3.out'}}, {t});")
        js.append(f"    tl.fromTo('#fs{k}-nm', {{scaleX:0}}, {{scaleX:1, duration:0.35, ease:'power3.out'}}, {round(t+0.2,3)});")
        js.append(f"    tl.fromTo('#fs{k}', {{boxShadow:'0 0 0 0px #FFD500, 0 20px 50px rgba(0,0,0,.5)'}}, {{boxShadow:'0 0 0 8px #FFD500, 0 20px 50px rgba(0,0,0,.5)', duration:0.2, yoyo:true, repeat:1}}, {round(t+0.1,3)});")
    body.append('    </div>')
    body.append(f'    <div id="figs-hero" class="hero clip" data-start="{g0}" data-duration="{round(n0-g0,3)}" data-track-index="3"><img id="figs-hero-img" src="assets/photos/5897_5.jpg" alt="">'
                '<div id="figs-six" class="six">6 персонажів!</div><div class="src" data-layout-allow-overlap>t.me/thestudledger/5897</div></div>')
    js += [f"    tl.fromTo('#figs-hero', {{scale:0.85, opacity:0}}, {{scale:1, opacity:1, duration:0.6, ease:'power4.out'}}, {g0});",
           f"    tl.fromTo('#figs-hero-img', {{scale:1.0, x:0}}, {{scale:1.18, x:-30, duration:{round(n0-g0,3)}, ease:'sine.inOut'}}, {g0});",
           f"    tl.fromTo('#figs-six', {{scale:0, rotation:-12}}, {{scale:1, rotation:-4, duration:0.5, ease:'back.out(2.5)'}}, {round(g0+0.4,3)});"]
    body.append(f'    <div id="figs-note" class="note clip" data-start="{n0}" data-duration="{round(L-n0,3)}" data-track-index="4">'
                '<div class="np" data-layout-allow-overflow><img id="figs-note-img" src="assets/photos/5522_1.jpg" alt=""></div>'
                '<div class="nt"><h3>⚠ Інформація різниться</h3>'
                '<p>Ранній список The Stud Ledger (червень): Зомбі Тор, Зомбі Залізна Людина, Зомбі Ванда, Зомбі Неймор, Людина-павук і «Дивне Верховне» — Стрендж Верховний.</p>'
                '<div class="tagx">LEAK · уточнюється</div></div></div>')
    js += [f"    tl.fromTo('#figs-note', {{x:120, opacity:0}}, {{x:0, opacity:1, duration:0.6, ease:'power4.out'}}, {n0});",
           f"    tl.fromTo('#figs-note-img', {{scale:1.0}}, {{scale:1.15, duration:{round(L-n0,3)}, ease:'none'}}, {n0});"]
    return scene_file(sid, L, css, "\n".join(body), "\n".join(js))

def build_next():
    sid = "next"; L = scene_len(sid)
    sets = [("67001", "Людина-павук проти Демо-Гобліна", "82"), ("67002", "Мех Червоного Павука", "146"), ("67003", "Мех Тора проти Доктора Дума", "237"),
            ("67004", "Людина-павук проти Зеленого Гобліна", "240"), ("67005", "Дивний Верховний Санктум", "814"), ("67022", "Збірний логотип Людини-павука", "480"),
            ("67023", "Джефф Земляна Акула", "495")]
    a = round(line_t(sid, 1) - 0.2, 3)
    themes = ["Marvel", "Fortnite", "Ninjago", "Китайський Новий рік", "Botanicals"]
    tw = ["Марвел", "Фортнайт", "Ніндзяго", "Китайськ", "Ботанікалс"]
    css = """
    #root .head { position:absolute; left:192px; top:150px; font:900 60px 'LNU Display'; color:#fff; }
    #root .head b { color:var(--yellow); }
    #root .chips { position:absolute; left:192px; right:192px; top:300px; display:flex; flex-wrap:wrap; gap:26px; }
    #root .chip { padding:26px 40px; border-radius:22px; background:#fff; color:var(--black); font:900 54px 'LNU Display'; box-shadow:0 14px 0 var(--red-deep), 0 30px 60px rgba(0,0,0,.4); }
    #root .chip:nth-child(odd) { background:var(--yellow); }
    #root .jan { position:absolute; left:192px; top:700px; font:800 40px 'LNU Display'; color:rgba(255,255,255,.85); }
    #root .list { position:absolute; left:192px; top:240px; width:1536px; display:grid; grid-template-columns:1fr 1fr; gap:16px 26px; }
    #root .row { display:flex; align-items:center; gap:20px; height:86px; padding:0 22px; border-radius:16px; background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.14); }
    #root .row b { font:900 40px 'LNU Display'; color:var(--yellow); width:150px; flex:none; }
    #root .row span { font:700 28px/1.1 'LNU Text'; color:#fff; flex:1; }
    #root .row em { font:800 28px 'LNU Display'; font-style:normal; color:rgba(255,255,255,.7); white-space:nowrap; }
    #root .rum { position:absolute; left:192px; top:150px; display:flex; align-items:center; gap:20px; }
    #root .rum .b { padding:10px 20px; border-radius:999px; background:var(--rumor); font:900 28px 'LNU Display'; letter-spacing:.12em; }
    #root .rum h2 { font:900 52px 'LNU Display'; }
    #root .srcl { position:absolute; left:192px; top:820px; font:600 28px 'LNU Text'; color:rgba(255,255,255,.7); }
"""
    body = [f'    <div id="nx-a" class="clip" data-start="0" data-duration="{a}" data-track-index="2" style="position:absolute;inset:0">',
            '      <div id="nx-head" class="head">Січень 2027: <b>що на нас чекає</b></div>', '      <div class="chips">']
    js = ["    tl.fromTo('#nx-head', {x:-80, opacity:0}, {x:0, opacity:1, duration:0.6, ease:'power4.out'}, 0.1);"]
    for k, (th, w) in enumerate(zip(themes, tw)):
        body.append(f'        <div id="nx-c{k}" class="chip">{E(th)}</div>')
        js.append(f"    tl.fromTo('#nx-c{k}', {{y:-300, rotation:{(-6+k*3)}, opacity:0}}, {{y:0, rotation:0, opacity:1, duration:0.6, ease:'bounce.out'}}, {round(T(sid,0,w)-0.1,3)});")
    body += ['      </div>', '      <div id="nx-jan" class="jan">Релізи — з 1 січня 2027 року</div>', '    </div>']
    js.append(f"    tl.fromTo('#nx-jan', {{opacity:0}}, {{opacity:1, duration:0.5}}, 1.0);")
    body += [f'    <div id="nx-b" class="clip" data-start="{a}" data-duration="{round(L-a,3)}" data-track-index="3" style="position:absolute;inset:0">',
             '      <div class="rum"><div id="nx-rb" class="b">RUMOR · Чутка</div><h2 id="nx-rh">Хвиля Marvel · січень 2027</h2></div>', '      <div class="list">']
    js += [f"    tl.fromTo('#nx-rb', {{scale:0}}, {{scale:1, duration:0.45, ease:'back.out(2.5)'}}, {a+0.1});",
           f"    tl.fromTo('#nx-rh', {{x:-40, opacity:0}}, {{x:0, opacity:1, duration:0.5, ease:'power3.out'}}, {a+0.2});"]
    for k, (n, nm, pc) in enumerate(sets):
        body.append(f'        <div id="nx-r{k}" class="row"><b>{n}</b><span>{E(nm)}</span><em>{pc} дет.</em></div>')
        js.append(f"    tl.fromTo('#nx-r{k}', {{x:80, opacity:0}}, {{x:0, opacity:1, duration:0.45, ease:'power3.out'}}, {round(a+0.5+k*0.55,3)});")
    body += ['      </div>', '      <div class="srcl">Джерело: The Stud Ledger · t.me/thestudledger/5274 (текстовий список, без фото)</div>', '    </div>']
    return scene_file(sid, L, css, "\n".join(body), "\n".join(js))

def build_outro():
    sid = "outro"; L = scene_len(sid)
    b = round(line_t(sid, 1) - 0.2, 3)
    css = """
    #root .q { position:absolute; left:192px; right:192px; top:200px; font:900 76px/1.1 'LNU Display'; color:#fff; }
    #root .q b { color:var(--yellow); }
    #root .qs { position:absolute; left:192px; top:560px; display:flex; gap:22px; }
    #root .qs img { width:280px; height:220px; object-fit:contain; background:#fff; border-radius:18px; box-shadow:0 18px 40px rgba(0,0,0,.5); }
    #root .sub { position:absolute; left:0; right:0; top:240px; text-align:center; }
    #root .logo-box { display:inline-block; padding:22px 50px 24px; border-radius:22px; background:var(--red); box-shadow:0 0 0 9px var(--yellow), 0 40px 90px rgba(0,0,0,.6); }
    #root .l1 { font:900 112px/0.95 'LNU Display'; color:#fff; -webkit-text-stroke:3px #000; paint-order:stroke fill; }
    #root .l2 { font:900 50px/1 'LNU Display'; color:var(--yellow); letter-spacing:.32em; padding-left:.32em; margin-top:4px; }
    #root .btn { display:inline-flex; align-items:center; gap:18px; margin-top:70px; padding:24px 54px; border-radius:999px; background:#fff; color:var(--red); font:900 50px 'LNU Display'; letter-spacing:.06em; }
    #root .btn i { width:0; height:0; border-left:30px solid var(--red); border-top:18px solid transparent; border-bottom:18px solid transparent; display:block; }
    #root .cred { margin-top:46px; font:700 28px 'LNU Text'; color:rgba(255,255,255,.85); }
    #root .cred b { color:var(--yellow); }
"""
    imgs = ["5924_6.jpg", "5897_3.jpg", "5932_3.jpg", "5955_3.jpg", "5964_3.jpg"]
    body = [f'    <div id="o-a" class="clip" data-start="0" data-duration="{b}" data-track-index="2" style="position:absolute;inset:0">',
            '      <div id="o-q" class="q">Яка новина тижня — <b>ваша улюблена?</b><br>Пишіть у коментарях!</div>', '      <div class="qs">']
    js = ["    tl.fromTo('#o-q', {y:50, opacity:0}, {y:0, opacity:1, duration:0.7, ease:'power4.out'}, 0.15);"]
    for k, im in enumerate(imgs):
        body.append(f'        <img id="o-i{k}" src="assets/photos/{im}" alt="">')
        js.append(f"    tl.fromTo('#o-i{k}', {{y:120, opacity:0, rotation:{(-5+k*2.5)}}}, {{y:0, opacity:1, rotation:0, duration:0.6, ease:'back.out(1.6)'}}, {round(0.8+k*0.25,2)});")
    body += ['      </div>', '    </div>',
             f'    <div id="o-b" class="clip" data-start="{b}" data-duration="{round(L-b,3)}" data-track-index="3" style="position:absolute;inset:0">',
             '      <div class="sub"><div id="o-logo" class="logo-box"><div class="l1">LEGO NEWS</div><div class="l2">UA</div></div><br>',
             '        <div id="o-btn" class="btn"><i></i>ПІДПИСАТИСЯ</div>',
             '        <div id="o-cred" class="cred">Новини та фото: <b>The Stud Ledger</b> · t.me/thestudledger</div></div>', '    </div>']
    js += [f"    tl.fromTo('#o-logo', {{scale:0.3, rotationX:70, opacity:0, transformPerspective:900}}, {{scale:1, rotationX:0, opacity:1, duration:0.8, ease:'back.out(1.6)'}}, {b});",
           f"    tl.fromTo('#o-btn', {{scale:0, opacity:0}}, {{scale:1, opacity:1, duration:0.5, ease:'back.out(2.6)'}}, {b+0.6});",
           f"    tl.fromTo('#o-btn', {{scale:1}}, {{scale:1.07, duration:0.35, yoyo:true, repeat:5, ease:'sine.inOut'}}, {b+1.5});",
           f"    tl.fromTo('#o-cred', {{opacity:0, y:20}}, {{opacity:1, y:0, duration:0.5}}, {b+1.0});"]
    return scene_file(sid, L, css, "\n".join(body), "\n".join(js))

# ---------------------------------------------------------------- overlays
def build_chrome():
    """logo bug + date chip + bottom news ticker, visible after the intro until the outro"""
    s = round(SC["intro"]["end"], 3); e = round(SC["outro"]["start"], 3); L = round(e - s, 3)
    items = ["Ґодзіла 21375 — офіційно: 5363 деталі, 400 €, 27 листопада", "Додзьо Іво 71888 — 3495 деталей, 280 € (витік)",
             "Fortnite: Такос Гуакос 77088 і P-1000 77084 — 1 січня 2027", "Санктум 67005 — 814 деталей, шість мініфігурок",
             "Лев процвітання 40976 — 411 деталей, 30 €", "Botanicals 2027 — чотири нові букети", "Джерело новин і фото: The Stud Ledger · t.me/thestudledger"]
    track = "".join(f'<span class="ti"><i></i>{E(x)}</span>' for x in items)
    css = """
    #root { font-family:'LNU Text',sans-serif; }
    #root .bug { position:absolute; left:192px; top:96px; display:flex; align-items:center; gap:12px; }
    #root .bug .bx { padding:6px 14px 7px; border-radius:10px; background:var(--red); box-shadow:0 0 0 4px var(--yellow); font:900 30px 'LNU Display'; color:#fff; letter-spacing:.02em; }
    #root .bug .bx b { color:var(--yellow); }
    #root .date { position:absolute; right:192px; top:100px; padding:8px 16px; border-radius:999px; background:rgba(255,255,255,.1); border:1px solid rgba(255,255,255,.2);
        font:700 28px 'LNU Text'; color:#fff; letter-spacing:.06em; }
    #root .tk { position:absolute; left:96px; right:96px; top:962px; height:58px; display:flex; border-radius:12px; overflow:hidden; box-shadow:0 10px 30px rgba(0,0,0,.45); }
    #root .tk .lab { flex:none; width:300px; display:flex; align-items:center; justify-content:center; background:var(--red); font:900 28px 'LNU Display'; letter-spacing:.08em; color:var(--yellow); }
    #root .tk .win { position:relative; flex:1; background:#0b0b0d; overflow:hidden; }
    #root .tk .track { position:absolute; left:0; top:0; height:58px; display:flex; align-items:center; white-space:nowrap; }
    #root .ti { display:inline-flex; align-items:center; gap:16px; padding-right:48px; font:600 28px 'LNU Text'; color:#fff; }
    #root .ti i { width:14px; height:14px; border-radius:3px; background:var(--yellow); display:block; }
"""
    body = f"""    <div id="chrome-bug" class="bug"><div class="bx">LEGO NEWS <b>UA</b></div></div>
    <div id="chrome-date" class="date">ВИПУСК · {ISSUE_DATE}</div>
    <div id="chrome-tk" class="tk" data-layout-allow-overflow><div class="lab">НОВИНИ ТИЖНЯ</div><div class="win"><div id="chrome-track" class="track" data-layout-allow-occlusion>{track * 10}</div></div></div>"""
    js = f"""    tl.fromTo('#chrome-bug', {{x:-40, opacity:0}}, {{x:0, opacity:1, duration:0.5, ease:'power3.out'}}, 0.3);
    tl.fromTo('#chrome-date', {{opacity:0}}, {{opacity:1, duration:0.5}}, 0.4);
    tl.fromTo('#chrome-tk', {{y:90}}, {{y:0, duration:0.6, ease:'power3.out'}}, 0.2);
    tl.fromTo('#chrome-track', {{x:0}}, {{x:-{int(L*70)}, duration:{L}, ease:'none'}}, 0);"""
    f = scene_file("chrome", L, css, body, js).replace('    <div class="bg"></div>\n    <div class="studs" data-layout-ignore></div>\n', "") \
        .replace("    tl.fromTo('#root .studs', { x: 0, y: 0 }, { x: -60, y: -60, duration: %s, ease: 'none' }, 0);\n" % L, "")
    return f, s, L

def build_captions():
    L = DUR
    css = """
    #root { font-family:'LNU Text',sans-serif; }
    #root .cg { position:absolute; left:0; right:0; top:862px; text-align:center; opacity:0; }
    #root .cg span { display:inline-block; max-width:1500px; padding:10px 26px 12px; border-radius:14px; background:rgba(11,11,13,.72);
        font:700 40px/1.2 'LNU Text'; color:#fff; letter-spacing:.005em; }
"""
    body = []; js = []
    for i, g in enumerate(CAPS):
        s, e = round(g["start"] - 0.05, 3), round(g["end"], 3)
        body.append(f'    <div id="cap{i}" class="cg"><span>{E(g["text"])}</span></div>')
        js.append(f"    tl.fromTo('#cap{i}', {{opacity:0, y:12}}, {{opacity:1, y:0, duration:0.14, ease:'power2.out'}}, {s});")
        js.append(f"    tl.to('#cap{i}', {{opacity:0, duration:0.1, ease:'power2.in'}}, {round(e-0.1,3)}); tl.set('#cap{i}', {{opacity:0, visibility:'hidden'}}, {e});")
    f = scene_file("captions", L, css, "\n".join(body), "\n".join(js)).replace('    <div class="bg"></div>\n    <div class="studs" data-layout-ignore></div>\n', "") \
        .replace("    tl.fromTo('#root .studs', { x: 0, y: 0 }, { x: -60, y: -60, duration: %s, ease: 'none' }, 0);\n" % L, "")
    return f

def build_wipe(cuts):
    """brick wipe that covers every scene cut"""
    css = """
    #root .wp { position:absolute; top:-40px; bottom:-40px; left:0; width:2300px; display:flex; }
    #root .wp .a { width:140px; background:var(--yellow); }
    #root .wp .b { flex:1; background:var(--red); background-image:radial-gradient(circle at 40px 40px, rgba(255,255,255,.18) 0 18px, transparent 19px); background-size:80px 80px; }
    #root .wp .c { width:60px; background:#fff; }
"""
    body = []; js = []
    for k, t in enumerate(cuts):
        body.append(f'    <div id="wp{k}" class="wp" data-layout-ignore><div class="c"></div><div class="a"></div><div class="b"></div></div>')
        js.append(f"    tl.fromTo('#wp{k}', {{x:1960}}, {{x:-120, duration:0.32, ease:'power3.in'}}, {round(t-0.32,3)});")
        js.append(f"    tl.to('#wp{k}', {{x:-2420, duration:0.38, ease:'power3.out'}}, {round(t,3)});")
    f = scene_file("wipe", DUR, css, "\n".join(body), "\n".join(js)).replace('    <div class="bg"></div>\n    <div class="studs" data-layout-ignore></div>\n', "") \
        .replace("    tl.fromTo('#root .studs', { x: 0, y: 0 }, { x: -60, y: -60, duration: %s, ease: 'none' }, 0);\n" % DUR, "")
    return f

# ---------------------------------------------------------------- write everything
import subprocess
def adur(f):
    return round(float(subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',f'{P}/assets/sfx/{f}.mp3'],capture_output=True,text=True).stdout),3)

def main():
    late_cfg()
    os.makedirs(f"{P}/compositions", exist_ok=True)
    files = {"intro": build_intro(), "top": build_top(), "figs": build_figs(), "next": build_next(), "outro": build_outro(),
             "b1": build_block("b1", 1, "Головні новини тижня", "Найгучніше з The Stud Ledger за 7 днів"),
             "b2": build_block("b2", 2, "Нові набори та свіжі фото", "Ninjago · Китайський Новий рік · Botanicals · Technic"),
             "b3": build_block("b3", 3, "LEGO Leaks 2027", "Marvel · Fortnite · Китайський Новий рік"),
             "b4": build_block("b4", 4, "Деталі та мініфігурки", "Торси, принти й цілі команди героїв"),
             "b5": build_block("b5", 5, "Що чекає нас далі", "Чутки та майбутні релізи")}
    for sid, cfg in SETS.items():
        files[sid] = build_set(sid, cfg)
    for sid, src in files.items():
        open(f"{P}/compositions/{sid}.html", "w").write(src)
    chrome, cs, cl = build_chrome(); open(f"{P}/compositions/chrome.html", "w").write(chrome)
    open(f"{P}/compositions/captions.html", "w").write(build_captions())
    cuts = [SC[s["id"]]["start"] for s in TL["scenes"][1:]]
    open(f"{P}/compositions/wipe.html", "w").write(build_wipe(cuts))

    hosts = []
    for i, s in enumerate(TL["scenes"]):
        sid = s["id"]; st = round(s["start"], 3); d = round(s["end"] - s["start"], 3)
        hosts.append(f'      <div id="{sid}" data-composition-id="{sid}" data-composition-src="compositions/{sid}.html" data-start="{st}" data-duration="{d}" '
                     f'data-track-index="1" data-track-kind="graphics" data-width="1920" data-height="1080" style="z-index:1"></div>')
    # sound effects: whoosh on cuts (rotating takes), riser+impact on intro logo, impact on leaks block, pops on status badges
    sfx = []; n = 0
    wh = ["whoosh-short", "whoosh", "whoosh-cinematic"]
    for k, t in enumerate(cuts):
        sfx.append((f"sfx-w{k}", wh[k % 3], round(t - 0.3, 3), 0.55));
    sfx.append(("sfx-riser", "riser", 0.0, 0.5)); sfx.append(("sfx-imp0", "impact-bass-1", 1.9, 0.8))
    sfx.append(("sfx-imp1", "impact-bass-2", round(SC["b3"]["start"] + 0.45, 3), 0.7))
    sfx.append(("sfx-imp2", "impact-bass-1", round(SC["outro"]["start"] + line_t("outro", 1) - 0.2, 3), 0.6))
    for k, sid in enumerate(SETS):
        for c in SETS[sid]["cards"]:
            t = SC[sid]["start"] + (0 if "at" not in c else c["at"]) + 0.27
            sfx.append((f"sfx-pop-{sid}-{c['num']}", "pop", round(t, 3), 0.45))
    for k in range(6):
        pass
    audio = [f'      <audio id="vo" src="assets/audio/voice.mp3" data-start="0" data-duration="{DUR}" data-track-index="20" data-volume="1"></audio>']
    if os.path.exists(f"{P}/assets/audio/music.mp3"):  # optional music bed, ducked under the voice
        audio.append(f'      <audio id="bgm" src="assets/audio/music.mp3" data-start="0" data-duration="{DUR}" data-track-index="19" data-volume="0.14" data-fade-in="1" data-fade-out="3"></audio>')
    for idx, (aid, f, t, v) in enumerate(sfx):
        audio.append(f'      <audio id="{aid}" src="assets/sfx/{f}.mp3" data-start="{max(0,t)}" data-duration="{adur(f)}" data-track-index="{21 + idx}" data-volume="{v}"></audio>')
    idx = f"""<!doctype html>
<html lang="uk">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=1920, height=1080" />
    <title>LEGO NEWS UA — випуск {ISSUE_DATE}</title>
    <script src="https://cdn.jsdelivr.net/npm/gsap@3.15.0/dist/gsap.min.js"></script>
    <style>
      * {{ margin:0; padding:0; box-sizing:border-box; }}
      html, body {{ margin:0; width:1920px; height:1080px; overflow:hidden; background:#0b0b0d; }}
      #root {{ position:relative; width:1920px; height:1080px; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{DUR}" data-width="1920" data-height="1080">
{chr(10).join(hosts)}
      <div id="chrome" data-composition-id="chrome" data-composition-src="compositions/chrome.html" data-start="{cs}" data-duration="{cl}" data-track-index="10" data-track-kind="graphics" data-width="1920" data-height="1080" style="z-index:20"></div>
      <div id="wipe" data-composition-id="wipe" data-composition-src="compositions/wipe.html" data-start="0" data-duration="{DUR}" data-track-index="11" data-track-kind="graphics" data-width="1920" data-height="1080" style="z-index:40"></div>
      <div id="captions" data-composition-id="captions" data-composition-src="compositions/captions.html" data-start="0" data-duration="{DUR}" data-track-index="12" data-track-kind="captions" data-width="1920" data-height="1080" style="z-index:30"></div>
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
    print("scenes", len(files) + 3, "sfx", len(sfx), "duration", DUR)

main()
