"""Generate the voiceover (edge-tts), word timings, timeline and SRT from script.json.
Run: SSL_CERT_FILE=... python3 script/tts.py   (from the project folder)"""
import asyncio, json, os, subprocess, re
import edge_tts

P = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = json.load(open(f"{P}/script/script.json"))
OUT = f"{P}/script/tts"; os.makedirs(OUT, exist_ok=True)
PROXY = os.environ.get("HTTPS_PROXY")

async def synth(text, path):
    words = []
    c = edge_tts.Communicate(text, S["voice"], rate=S["rate"], pitch=S["pitch"], proxy=PROXY, boundary="WordBoundary")
    with open(path, "wb") as f:
        async for ch in c.stream():
            if ch["type"] == "audio": f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append({"text": ch["text"], "start": ch["offset"]/1e7, "end": (ch["offset"]+ch["duration"])/1e7})
    return words

def dur(path):
    return float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",path],capture_output=True,text=True).stdout)

def norm(w): return re.sub(r"[^\w'’-]", "", w.lower())

async def main():
    t = 0.0; timeline = []; parts = []
    for sc in S["scenes"]:
        start = t; t += sc.get("lead", 0.5)
        lines = []
        for i, ln in enumerate(sc["lines"]):
            mp3 = f"{OUT}/{sc['id']}_{i}.mp3"; wj = mp3.replace(".mp3", ".json")
            if os.path.exists(wj) and json.load(open(wj))["tts"] == ln["tts"]:
                words = json.load(open(wj))["words"]
            else:
                words = await synth(ln["tts"], mp3)
                json.dump({"tts": ln["tts"], "words": words}, open(wj, "w"), ensure_ascii=False)
            d = dur(mp3)
            lines.append({"text": ln["text"], "start": round(t,3), "end": round(t+d,3), "file": mp3, "words": [{**w, "start": round(w["start"]+t,3), "end": round(w["end"]+t,3)} for w in words]})
            parts.append((mp3, t)); t += d + S["gap"]
        t += sc.get("tail", 0) + S["scene_gap"] - S["gap"]
        timeline.append({"id": sc["id"], "start": round(start,3), "end": round(t,3), "lines": lines})
    total = round(t, 3)
    # mix voice into one track
    args = ["ffmpeg","-v","error","-y"]
    for f,_ in parts: args += ["-i", f]
    fc = "".join(f"[{i}]adelay={int(o*1000)}|{int(o*1000)}[a{i}];" for i,(_,o) in enumerate(parts))
    fc += "".join(f"[a{i}]" for i in range(len(parts))) + f"amix=inputs={len(parts)}:normalize=0,apad=whole_dur={total}[m]"
    os.makedirs(f"{P}/assets/audio", exist_ok=True)
    subprocess.run(args + ["-filter_complex", fc, "-map","[m]","-ar","48000","-ac","2","-c:a","libmp3lame","-b:a","192k", f"{P}/assets/audio/voice.mp3"], check=True)
    json.dump({"duration": total, "scenes": timeline}, open(f"{P}/script/timeline.json","w"), ensure_ascii=False, indent=1)
    # captions: map display words onto tts timing per line (proportional by word index)
    caps = []
    for sc in timeline:
        for ln in sc["lines"]:
            dw = ln["text"].split(); tw = ln["words"]
            if not tw: continue
            for j, w in enumerate(dw):
                k = min(int(j * len(tw) / len(dw)), len(tw)-1)
                k2 = min(int((j+1) * len(tw) / len(dw)) - 1, len(tw)-1)
                caps.append({"text": w, "start": tw[k]["start"], "end": tw[max(k,k2)]["end"], "lineEnd": ln["end"]})
    json.dump(caps, open(f"{P}/script/words.json","w"), ensure_ascii=False)
    # SRT: one cue per sentence-ish chunk (<= 9 words)
    def ts(x):
        h=int(x//3600); m=int(x%3600//60); s=x%60; return f"{h:02}:{m:02}:{int(s):02},{int(round((s-int(s))*1000)):03}".replace(",1000",",999")
    cues=[]; cur=[]
    for i,w in enumerate(caps):
        cur.append(w)
        endsent = re.search(r"[.!?…:]$", w["text"]) or (i+1<len(caps) and caps[i+1]["start"]-w["end"]>0.3)
        if len(cur)>=9 or endsent or i+1==len(caps) or w["lineEnd"]!=caps[i+1]["lineEnd"]:
            cues.append((cur[0]["start"], max(cur[-1]["end"], cur[0]["start"]+0.8), " ".join(x["text"] for x in cur))); cur=[]
    with open(f"{P}/subtitles_uk.srt","w") as f:
        for n,(a,b,tx) in enumerate(cues,1): f.write(f"{n}\n{ts(a)} --> {ts(b)}\n{tx}\n\n")
    print("total", total, "s; scenes", len(timeline), "; cues", len(cues))

asyncio.run(main())
