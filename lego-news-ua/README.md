# LEGO NEWS UA — щотижневий випуск (HyperFrames)

Ukrainian-language weekly LEGO news show. Issue of 06.11.2026, 7:20, 1920×1080, 30 fps.
News and photos come from the Telegram channel [The Stud Ledger](https://t.me/thestudledger).

## Що де лежить

| Шлях | Що це |
|---|---|
| `renders/LEGO_NEWS_UA_2026-11-06.mp4` | finished video (not committed to git because of its size) |
| `subtitles_uk.srt` | Ukrainian subtitles |
| `deliverables/thumbnail_1280x720.png` | YouTube thumbnail (source: `deliverables/thumbnail.html`) |
| `deliverables/youtube_description.md` | title, description with chapters, tags |
| `deliverables/SOURCES.md` | every The Stud Ledger post used, statuses, fact checks |
| `index.html`, `compositions/*.html` | HyperFrames project: one scene per news item, plus the ticker, wipes and captions |
| `script/script.json` | presenter script: on-screen text and the text the voice reads (numbers spelled out) |
| `assets/photos/` | photos from the channel posts (`<post>_<n>.jpg`), `fig1–6.png` are crops of the minifigure line-up |

## Як редагувати і перезібрати

Edit the generated HTML directly (in the HyperFrames desktop app or by hand). To rebuild from the script:

```bash
pip install edge-tts
SSL_CERT_FILE=/root/.ccr/ca-bundle.crt python3 script/tts.py   # voice + timeline (skips unchanged lines)
python3 script/caps.py                                         # captions + subtitles_uk.srt
python3 script/build.py                                        # index.html + compositions/
npx hyperframes check
npx hyperframes render --quality delivery -o renders/LEGO_NEWS_UA.mp4
```

Each week, update `script/script.json` and the scene settings (`SETS` in `script/build.py`) with new posts and photos, then run the same commands.
`build.py` overwrites `index.html` and `compositions/`. Make lasting changes in the script and the generator, not in the generated HTML.

## Музика

This issue has no background music. HyperFrames' music catalogue needs a HeyGen sign-in (`npx hyperframes auth login`).
To add your own track, save it as `assets/audio/music.mp3` and run `python3 script/build.py`: the generator adds it at volume 0.14 with fades. By hand, add this line to `index.html`, next to `#vo`:
`<audio id="bgm" src="assets/audio/music.mp3" data-start="0" data-duration="439.84" data-track-index="19" data-volume="0.14" data-fade-in="1" data-fade-out="3"></audio>`
