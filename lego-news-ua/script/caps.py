"""Build caption word timings (script/words.json) and subtitles_uk.srt from script/timeline.json.
Display words are mapped onto the TTS word clock by their relative character position in the line."""
import json, re, os
P = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T = json.load(open(f"{P}/script/timeline.json"))
def interp(frac, tw):
    # tts words -> cumulative char fraction -> time
    lens = [len(w["text"]) + 1 for w in tw]; tot = sum(lens); acc = 0; pts = []
    for w, l in zip(tw, lens):
        pts.append((acc / tot, w["start"])); acc += l; pts.append((acc / tot, w["end"]))
    for (f0, t0), (f1, t1) in zip(pts, pts[1:]):
        if f0 <= frac <= f1: return t0 + (t1 - t0) * ((frac - f0) / (f1 - f0) if f1 > f0 else 0)
    return pts[-1][1]
caps = []
for sc in T["scenes"]:
    for li, ln in enumerate(sc["lines"]):
        dw = ln["text"].split(); tw = ln["words"]
        tot = sum(len(w) + 1 for w in dw); acc = 0
        for w in dw:
            a = interp(acc / tot, tw); acc += len(w) + 1; b = interp(acc / tot, tw)
            caps.append({"text": w, "start": round(a, 3), "end": round(b, 3), "line": f"{sc['id']}_{li}"})
json.dump(caps, open(f"{P}/script/words.json", "w"), ensure_ascii=False)
# groups: break at sentence end / comma after 3+ words / 7 words / line change
groups = []; cur = []
for i, w in enumerate(caps):
    cur.append(w); nxt = caps[i + 1] if i + 1 < len(caps) else None
    if (not nxt or nxt["line"] != w["line"] or re.search(r"[.!?…]$", w["text"]) or len(cur) >= 8
            or (len(cur) >= 3 and re.search(r"[,:—–]$", w["text"])) or (nxt and nxt["text"] in "—–" and len(cur) >= 3)):
        groups.append(cur); cur = []
G = [{"text": " ".join(x["text"] for x in g), "start": g[0]["start"], "end": g[-1]["end"]} for g in groups]
for a, b in zip(G, G[1:]):
    a["end"] = round(min(max(a["end"] + 0.25, a["start"] + 0.9), b["start"] - 0.02), 3)
json.dump(G, open(f"{P}/script/caption_groups.json", "w"), ensure_ascii=False, indent=0)
def ts(x):
    ms = int(round(x * 1000)); return f"{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}"
with open(f"{P}/subtitles_uk.srt", "w") as f:
    for n, g in enumerate(G, 1): f.write(f"{n}\n{ts(g['start'])} --> {ts(g['end'])}\n{g['text']}\n\n")
print(len(G), "groups")
