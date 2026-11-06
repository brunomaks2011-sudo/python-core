# LEGO NEWS UA — YouTube Shorts (HyperFrames)

Vertical video, 1080×1920, 30 FPS, 89.8 s: four LEGO 2027 leaks plus one official news item of the week.

| Шлях | Що це |
|---|---|
| `renders/LEGO_NEWS_UA_Shorts_2027_leaks.mp4` | finished MP4 (not in git because of its size) |
| `subtitles_uk.srt` | Ukrainian subtitles (the video also has animated burned-in captions) |
| `deliverables/cover_1080x1920.png` | vertical cover (source: `deliverables/cover.html`) |
| `deliverables/shorts_description.md` | title, description, hashtags, tags |
| `index.html`, `compositions/*.html` | HyperFrames project: hook, sanctum, figs, tacos, p1000, lion, news, outro, captions, chrome |
| `script/script.json` | presenter lines; each has its own rate, pitch and pause (intonation) |
| `assets/photos/` | set photos from The Stud Ledger posts (`<post>_<n>.jpg`); `fig1–6.png` are the six 67005 minifigures |

## Свої фото

To use your own photos, put them in `assets/photos/` under the same names (for example `5897_3.jpg` is the main Sanctum shot, `fig1.png`–`fig6.png` are the minifigures). Or change the file lists in `script/build.py` (`b_sanctum`, `b_tacos`, `b_p1000`, `b_lion`). Then run:

```bash
python3 script/build.py && npx hyperframes check
npx hyperframes render --quality delivery -o renders/shorts.mp4
```

## Голос

```bash
pip install edge-tts
SSL_CERT_FILE=/root/.ccr/ca-bundle.crt python3 script/voice.py   # voice, timeline, captions, SRT
python3 script/build.py
```

Background music: put a track at `assets/audio/music.mp3`; `build.py` adds it at volume 0.14.

## Зони Shorts

Text and products stay within y 168–1330. Nothing sits under the right-hand action rail. Below 1330 there is only decoration (the large faded set number).
