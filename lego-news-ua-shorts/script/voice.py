"""LEGO NEWS UA Shorts: voice (edge-tts, per-line rate/pitch/pause), timeline, captions, SRT.
Run from the project folder:  SSL_CERT_FILE=/root/.ccr/ca-bundle.crt python3 script/voice.py"""
import asyncio, json, os, re, subprocess
import edge_tts
P = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = json.load(open(f"{P}/script/script.json"))
OUT = f"{P}/script/tts"; os.makedirs(OUT, exist_ok=True)

async def synth(ln, path):
    words = []
    c = edge_tts.Communicate(ln["tts"], S["voice"], rate=ln.get("rate", "+6%"), pitch=ln.get("pitch", "+0Hz"),
                             proxy=os.environ.get("HTTPS_PROXY"), boundary="WordBoundary")
    with open(path, "wb") as f:
        async for ch in c.stream():
            if ch["type"] == "audio": f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append({"text": ch["text"], "start": ch["offset"] / 1e7, "end": (ch["offset"] + ch["duration"]) / 1e7})
    return words

def dur(p): return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p], capture_output=True, text=True).stdout)

def lead_silence(p):
    """edge-tts pads ~0.1 s; trim leading silence so lines sit tight"""
    r = subprocess.run(["ffmpeg", "-i", p, "-af", "silencedetect=noise=-40dB:d=0.05", "-f", "null", "-"], capture_output=True, text=True).stderr
    m = re.search(r"silence_start: 0(?:\.0+)?\s.*?silence_end: ([\d.]+)", r, re.S)
    return float(m.group(1)) if m else 0.0

async def main():
    t = 0.0; tl = []; parts = []
    for sc in S["scenes"]:
        st = t; t += sc.get("lead", 0.1); lines = []
        for i, ln in enumerate(sc["lines"]):
            mp3 = f"{OUT}/{sc['id']}_{i}.mp3"; js = mp3[:-4] + ".json"
            key = {k: ln.get(k) for k in ("tts", "rate", "pitch")}
            if os.path.exists(js) and os.path.exists(mp3) and json.load(open(js))["key"] == key:
                words = json.load(open(js))["words"]
            else:
                words = await synth(ln, mp3); json.dump({"key": key, "words": words}, open(js, "w"), ensure_ascii=False)
            trim = max(0.0, min(lead_silence(mp3), words[0]["start"] if words else 0) - 0.03)
            d = min(dur(mp3), (words[-1]["end"] + 0.12) if words else dur(mp3)) - trim
            off = t - trim
            lines.append({"text": ln["text"], "start": round(t, 3), "end": round(t + d, 3),
                          "words": [{**w, "start": round(w["start"] + off, 3), "end": round(w["end"] + off, 3)} for w in words]})
            parts.append((mp3, off, trim, d)); t += d + ln.get("pause", 0.2)
        t += sc.get("tail", 0)
        tl.append({"id": sc["id"], "start": round(st, 3), "end": round(t, 3), "lines": lines})
    total = round(t, 3)
    args = ["ffmpeg", "-v", "error", "-y"]
    for f, _, _, _ in parts: args += ["-i", f]
    fc = "".join(f"[{i}]atrim=start={tr}:duration={dd},afade=t=out:st={max(0,dd-0.06)}:d=0.06,asetpts=PTS-STARTPTS,adelay={int((o+tr)*1000)}|{int((o+tr)*1000)}[a{i}];" for i, (_, o, tr, dd) in enumerate(parts))
    fc += "".join(f"[a{i}]" for i in range(len(parts))) + f"amix=inputs={len(parts)}:normalize=0,apad=whole_dur={total},loudnorm=I=-16:TP=-1.5:LRA=9[m]"
    subprocess.run(args + ["-filter_complex", fc, "-map", "[m]", "-ar", "48000", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "192k", f"{P}/assets/audio/voice.mp3"], check=True)
    json.dump({"duration": total, "scenes": tl}, open(f"{P}/script/timeline.json", "w"), ensure_ascii=False, indent=1)
    # captions: display words on the tts clock by relative char position
    def interp(frac, tw):
        lens = [len(w["text"]) + 1 for w in tw]; tot = sum(lens); acc = 0; pts = []
        for w, l in zip(tw, lens): pts.append((acc / tot, w["start"])); acc += l; pts.append((acc / tot, w["end"]))
        for (f0, t0), (f1, t1) in zip(pts, pts[1:]):
            if f0 <= frac <= f1: return t0 + (t1 - t0) * ((frac - f0) / (f1 - f0) if f1 > f0 else 0)
        return pts[-1][1]
    words = []
    for sc in tl:
        for li, ln in enumerate(sc["lines"]):
            dw = ln["text"].split(); tot = sum(len(w) + 1 for w in dw); acc = 0
            for w in dw:
                a = interp(acc / tot, ln["words"]); acc += len(w) + 1; b = interp(acc / tot, ln["words"])
                words.append({"text": w, "start": round(a, 3), "end": round(b, 3), "line": f"{sc['id']}_{li}"})
    groups = []; cur = []
    for i, w in enumerate(words):
        cur.append(w); nx = words[i + 1] if i + 1 < len(words) else None
        if (not nx or nx["line"] != w["line"] or re.search(r"[.!?,…]$", w["text"]) or len(cur) >= 3 or (nx and nx["text"] in "—–")):
            groups.append(cur); cur = []
    G = [{"words": g, "text": " ".join(x["text"] for x in g), "start": g[0]["start"], "end": g[-1]["end"]} for g in groups]
    for a, b in zip(G, G[1:]): a["end"] = round(min(max(a["end"] + 0.15, a["start"] + 0.5), b["start"] - 0.02), 3)
    json.dump(G, open(f"{P}/script/caption_groups.json", "w"), ensure_ascii=False, indent=0)
    def ts(x):
        ms = int(round(x * 1000)); return f"{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}"
    # SRT: sentence-level cues (easier to read than 3-word groups)
    with open(f"{P}/subtitles_uk.srt", "w") as f:
        n = 0
        for sc in tl:
            for ln in sc["lines"]:
                n += 1; f.write(f"{n}\n{ts(ln['start'])} --> {ts(ln['end'])}\n{ln['text']}\n\n")
    print("total", total, "s")
    for s in tl: print(f"  {s['id']:8} {s['start']:6.2f} → {s['end']:6.2f}")

asyncio.run(main())
