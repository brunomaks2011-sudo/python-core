#!/usr/bin/env python3
"""Original game audio for BLUE vs RED, synthesised from scratch with numpy.

Builds five sound sheets (one upload each) and the clip map the game reads:

  Assets/Audio/SFX/sfx.ogg            one-shots: weapons, explosions, impacts, UI
  Assets/Audio/SFX/loops.ogg          seamless loops: engines, wind, rain, battle
  Assets/Audio/Music/music.ogg        menu theme (loop), victory and defeat stings
  Assets/Audio/Voice/voice_blue.ogg   Blue HQ radio lines (from gen_voice.py)
  Assets/Audio/Voice/voice_red.ogg    Red HQ radio lines
  Assets/Scripts/Shared/AudioSprites.luau   clip -> sheet, start, length, loop

Roblox plays one clip out of a sheet with Sound.PlaybackRegion / LoopRegion,
so the whole soundtrack is 5 uploads instead of ~70 (audio uploads are
rate-limited per account).

Usage: python3 Tools/audio/build_audio.py [--preview DIR]
  --preview DIR   also write every clip as its own WAV into DIR for listening
Needs numpy and ffmpeg (libvorbis). Output is deterministic (fixed seeds).
"""
import argparse
import json
import pathlib
import subprocess
import sys
import wave

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[2]
AUDIO = ROOT / "Assets" / "Audio"
SPRITES = ROOT / "Assets" / "Scripts" / "Shared" / "AudioSprites.luau"
SR = 44100


# ---------------------------------------------------------------------------
# DSP core
# ---------------------------------------------------------------------------
def rng(seed):
    return np.random.default_rng(seed)


def n_of(sec):
    return max(1, int(round(sec * SR)))


def tvec(n):
    return np.arange(n, dtype=np.float64) / SR


def response(freqs, lp=None, hp=None, order=2, peaks=()):
    f = np.maximum(freqs, 1e-3)
    h = np.ones_like(f)
    if lp is not None:
        h = h / np.sqrt(1 + (f / lp) ** (2 * order))
    if hp is not None:
        h = h / np.sqrt(1 + (hp / f) ** (2 * order))
    for fc, gain_db, width in peaks:  # width in octaves
        h = h * (1 + (10 ** (gain_db / 20) - 1) * np.exp(-0.5 * (np.log2(f / fc) / width) ** 2))
    return h


def min_phase(mag, N):
    """Causal minimum-phase spectrum with the given magnitude (real cepstrum)."""
    cep = np.fft.irfft(np.log(np.maximum(mag, 1e-9)), N)
    fold = np.zeros(N)
    fold[0] = 1
    fold[1:(N + 1) // 2] = 2
    if N % 2 == 0:
        fold[N // 2] = 1
    return np.exp(np.fft.rfft(cep * fold, N))


def filt(x, lp=None, hp=None, order=2, peaks=(), circular=False):
    """Butterworth-magnitude filter. One-shots use a causal minimum-phase
    response (no pre-ringing); loops filter circularly so they stay seamless."""
    x = np.asarray(x, dtype=np.float64)
    n = x.shape[-1]
    N = n if circular else 1 << int(np.ceil(np.log2(n + SR)))
    mag = response(np.fft.rfftfreq(N, 1 / SR), lp, hp, order, peaks)
    H = mag if circular else min_phase(mag, N)
    return np.fft.irfft(np.fft.rfft(x, N) * H, N)[..., :n]


def conv(x, ir, circular=False):
    n = x.shape[-1]
    if circular:
        return np.fft.irfft(np.fft.rfft(x, n) * np.fft.rfft(ir, n), n)
    N = 1 << int(np.ceil(np.log2(n + ir.shape[-1])))
    return np.fft.irfft(np.fft.rfft(x, N) * np.fft.rfft(ir, N), N)[..., :n]


def env(n, tau, attack=0.0004):
    t = tvec(n)
    e = np.exp(-t / tau)
    return e * (1 - np.exp(-t / attack)) if attack > 0 else e


def sweep(n, f_start, f_end, tau, phase0=0.0):
    t = tvec(n)
    f = f_end + (f_start - f_end) * np.exp(-t / tau)
    return np.sin(phase0 + 2 * np.pi * np.cumsum(f) / SR)


def norm(x, peak=0.89):
    m = float(np.max(np.abs(x)))
    return x * (peak / m) if m > 0 else x


def sat(x, drive):
    x = norm(x, 1.0)
    return np.tanh(x * drive) / np.tanh(drive)


def fade(x, fin=0.0, fout=0.02):
    x = np.array(x, dtype=np.float64)
    n = x.shape[-1]
    if fin > 0:
        k = min(n, n_of(fin))
        x[..., :k] *= np.linspace(0, 1, k)
    if fout > 0:
        k = min(n, n_of(fout))
        x[..., n - k:] *= np.linspace(1, 0, k)
    return x


def add(buf, x, i, gain=1.0, circular=False):
    """Mix x into buf starting at sample i (wrapping around when circular)."""
    n, m = buf.shape[-1], x.shape[-1]
    if circular:
        i %= n
        first = min(m, n - i)
        buf[..., i:i + first] += gain * x[..., :first]
        off = first
        while off < m:
            k = min(m - off, n)
            buf[..., :k] += gain * x[..., off:off + k]
            off += k
        return
    if i >= n or i + m <= 0:
        return
    s = max(0, -i)
    k = min(m, n - i)
    buf[..., i + s:i + k] += gain * x[..., s:k]


def outdoor_ir(length, decay, lp, early=((0.045, 0.45), (0.09, 0.3), (0.16, 0.22), (0.27, 0.14)), level=0.5, seed=1, stereo=False):
    """Impulse response of open ground with buildings: a few discrete slap
    echoes and a diffuse, darkening tail. The direct sound is not included."""
    r = rng(seed)
    n = n_of(length)
    t = tvec(n)
    ch = 2 if stereo else 1
    tail = r.standard_normal((ch, n)) * np.exp(-t / decay) * (1 - np.exp(-t / 0.03))
    tail *= level * np.sqrt(2 / (decay * SR))  # tail energy == level^2
    for c in range(ch):
        for d, g in early:
            j = n_of(d * (1 + 0.09 * c))
            if j < n:
                tail[c, j] += g * (1 if r.random() < 0.7 else -1)
    ir = filt(tail, lp=lp, order=1)
    return ir if stereo else ir[0]


# ---------------------------------------------------------------------------
# One-shots
# ---------------------------------------------------------------------------
def gunshot(seed, dur, crack_hp, body, body_tau, thump, thump_tau, tail_tau, tail_lp, tail_gain,
            rev_decay, rev, drive, crack_tau=0.006, mech=0.0):
    r = rng(seed)
    n = n_of(dur)
    crack = filt(r.standard_normal(n), hp=crack_hp, order=2) * env(n, crack_tau, 0.00005)
    k = n_of(0.0012)
    nwave = np.zeros(n)
    nwave[:k] = np.linspace(1, -1, k)  # supersonic N-wave
    bod = filt(r.standard_normal(n), hp=body[0], lp=body[1], order=2) * env(n, body_tau, 0.0003)
    th = sweep(n, thump[0], thump[1], 0.012) * env(n, thump_tau, 0.0008)
    x = 0.8 * norm(crack, 1) + 0.6 * nwave + 0.9 * norm(bod, 1) + 0.9 * th
    if mech > 0:  # action cycling a moment after the shot
        m = n_of(0.012)
        click = filt(r.standard_normal(m), hp=2500, lp=8000) * env(m, 0.0018)
        add(x, norm(click, mech), n_of(0.05))
    x = sat(x, drive)
    tail = filt(r.standard_normal(n), lp=tail_lp, order=2) * env(n, tail_tau, 0.015)
    x = x + tail_gain * norm(tail, 1)
    ir = outdoor_ir(min(dur, 2.5), rev_decay, 2200, level=0.6, seed=seed + 100)
    x = x + rev * conv(x, ir)
    return fade(norm(x), 0, 0.03)


GUNS = {
    #             seed dur  crack  body          b_tau  thump      t_tau  tail  t_lp  t_g   r_dec rev  drive c_tau  mech
    "pistol":     (11, 0.7, 2000, (250, 2600), 0.030, (170, 80), 0.030, 0.22, 1200, 0.15, 0.35, 0.45, 3.0, 0.004, 0.0),
    "smg":        (12, 0.6, 2200, (220, 2800), 0.028, (150, 75), 0.026, 0.20, 1300, 0.14, 0.30, 0.40, 3.0, 0.004, 0.0),
    "rifle":      (13, 1.0, 2500, (180, 2400), 0.040, (125, 55), 0.040, 0.35, 1100, 0.22, 0.45, 0.55, 3.5, 0.006, 0.25),
    "lmg":        (14, 1.0, 2400, (160, 2200), 0.045, (115, 50), 0.045, 0.38, 1000, 0.24, 0.45, 0.55, 3.8, 0.006, 0.20),
    "mg":         (15, 1.0, 2300, (150, 2000), 0.048, (110, 48), 0.048, 0.40, 1000, 0.25, 0.45, 0.55, 3.8, 0.006, 0.0),
    "sniper":     (16, 2.2, 3000, (140, 2000), 0.065, (100, 40), 0.070, 0.90, 900, 0.32, 0.80, 0.70, 4.5, 0.008, 0.0),
    "hmg":        (17, 1.4, 1800, (110, 1500), 0.070, (90, 38), 0.080, 0.55, 800, 0.30, 0.60, 0.60, 4.5, 0.008, 0.0),
    "autocannon": (18, 1.8, 1500, (90, 1200), 0.090, (75, 30), 0.110, 0.80, 700, 0.35, 0.80, 0.65, 5.0, 0.010, 0.0),
    "tank_gun":   (19, 4.0, 1100, (60, 800), 0.200, (60, 22), 0.250, 1.50, 450, 0.50, 1.30, 0.80, 6.0, 0.014, 0.0),
    "howitzer":   (20, 4.5, 1000, (50, 700), 0.220, (52, 18), 0.300, 1.90, 380, 0.55, 1.60, 0.80, 6.0, 0.016, 0.0),
}


def banded_sweep(noise, centres, f_of_t, width=0.45):
    """Noise through a band-pass whose centre follows f_of_t (crossfaded bank)."""
    out = np.zeros_like(noise)
    wsum = np.zeros_like(noise)
    lf = np.log2(np.maximum(f_of_t, 20))
    for fc in centres:
        band = filt(noise, hp=fc / 1.5, lp=fc * 1.5, order=2)
        w = np.exp(-0.5 * ((np.log2(fc) - lf) / width) ** 2)
        out += w * band
        wsum += w
    return out / np.maximum(wsum, 1e-6)


def rocket(seed, dur, pop, roar_tau, sweep_hz, low):
    r = rng(seed)
    n = n_of(dur)
    t = tvec(n)
    p = filt(r.standard_normal(n), hp=200, lp=3200) * env(n, 0.03, 0.0002)
    p = norm(p, 1) + 0.8 * sweep(n, 95, 40, 0.03) * env(n, 0.06, 0.001)
    fc = sweep_hz[1] + (sweep_hz[0] - sweep_hz[1]) * np.exp(-t / (dur * 0.35))
    centres = np.geomspace(min(sweep_hz) / 1.3, max(sweep_hz) * 1.3, 6)
    whoosh = banded_sweep(r.standard_normal(n), centres, fc)
    flutter = 0.7 + 0.3 * norm(filt(r.standard_normal(n), lp=45, order=2), 1)
    shape = (1 - np.exp(-t / 0.04)) * np.exp(-t / roar_tau)
    roar = filt(r.standard_normal(n), lp=420, order=2)
    crackle = np.zeros(n)
    for tt in r.uniform(0.02, dur * 0.8, int(220 * dur)):
        m = n_of(0.003)
        add(crackle, filt(r.standard_normal(m), hp=1500) * env(m, 0.0007), n_of(tt), r.uniform(0.3, 1) * np.exp(-tt / roar_tau))
    x = pop * norm(p, 1) + (norm(whoosh, 1) + low * norm(roar, 1)) * shape * flutter + 0.25 * norm(crackle, 1)
    x = sat(x, 2.5)
    x = x + 0.5 * conv(x, outdoor_ir(min(dur, 2.0), 0.6, 2000, level=0.6, seed=seed + 3))
    return fade(norm(x), 0, 0.15)


def grenade_throw(seed):
    r = rng(seed)
    n = n_of(0.45)
    t = tvec(n)
    m = n_of(0.08)
    tm = tvec(m)
    clink = sum(a * np.sin(2 * np.pi * f * tm) for f, a in ((2810, 1), (4130, 0.6), (6370, 0.35))) * env(m, 0.012, 0.0002)
    swoosh = filt(r.standard_normal(n), hp=600, lp=3200) * np.exp(-0.5 * ((t - 0.26) / 0.06) ** 2)
    x = np.zeros(n)
    add(x, 0.5 * norm(clink, 1), 0)
    x += 0.8 * norm(swoosh, 1)
    return fade(norm(x, 0.7), 0, 0.03)


def explosion(seed, dur, boom, boom_tau, rumble_tau, rumble_lp, debris_n, drive, rev_decay):
    r = rng(seed)
    n = n_of(dur)
    crack = filt(r.standard_normal(n), hp=300, order=1) * env(n, 0.02, 0.0002)
    blast = filt(r.standard_normal(n), lp=1800, order=2) * env(n, 0.14, 0.001)
    b = sweep(n, boom[0], boom[1], 0.08) * env(n, boom_tau, 0.002)
    am = 0.6 + 0.4 * norm(filt(r.standard_normal(n), lp=6, order=2), 1)
    rumble = filt(r.standard_normal(n), lp=rumble_lp, order=3) * env(n, rumble_tau, 0.03) * am
    x = 0.7 * norm(crack, 1) + 0.9 * norm(blast, 1) + 1.0 * b + 0.8 * norm(rumble, 1)
    x = sat(x, drive)
    deb = np.zeros(n)
    for tt in r.exponential(0.5, debris_n) + 0.15:  # falling debris
        if tt > dur - 0.1:
            continue
        m = n_of(r.uniform(0.004, 0.02))
        grain = filt(r.standard_normal(m), hp=r.uniform(400, 1500), lp=r.uniform(2500, 7000)) * env(m, m / SR / 4)
        add(deb, grain, n_of(tt), r.uniform(0.2, 1.0) * np.exp(-tt / 1.0))
    x = x + 0.25 * norm(deb, 1)
    ir = outdoor_ir(2.5, rev_decay, 1500, early=((0.09, 0.5), (0.21, 0.35), (0.42, 0.25), (0.75, 0.15)), level=0.7, seed=seed + 7)
    x = x + 0.6 * conv(x, ir)
    return fade(norm(x), 0, 0.25)


def collapse(seed):
    r = rng(seed)
    dur = 2.4
    n = n_of(dur)
    x = 0.6 * norm(filt(r.standard_normal(n), lp=240, order=3) * env(n, 0.8, 0.05), 1)
    for tt in np.sort(r.exponential(0.45, 140)):
        if tt > dur - 0.15:
            continue
        m = n_of(r.uniform(0.006, 0.03))
        grain = filt(r.standard_normal(m), hp=r.uniform(200, 900), lp=r.uniform(1500, 5000)) * env(m, m / SR / 3)
        add(x, norm(grain, 1), n_of(tt), r.uniform(0.15, 0.8) * np.exp(-tt / 0.9))
    for tt in r.uniform(0.0, 0.9, 6):  # heavy chunks landing
        m = n_of(0.25)
        add(x, sweep(m, 90, 45, 0.05) * env(m, 0.06, 0.001), n_of(tt), r.uniform(0.4, 0.9))
    x = sat(x, 2.0)
    x = x + 0.4 * conv(x, outdoor_ir(1.5, 0.5, 2000, level=0.6, seed=seed + 1))
    return fade(norm(x), 0, 0.2)


def glass(seed):
    r = rng(seed)
    n = n_of(1.1)
    x = norm(filt(r.standard_normal(n), hp=3000) * env(n, 0.012, 0.0001), 0.7)
    for tt in r.exponential(0.12, 70):
        if tt > 0.9:
            continue
        m = n_of(0.12)
        tm = tvec(m)
        tau = r.uniform(0.015, 0.07)
        shard = sum(np.sin(2 * np.pi * r.uniform(3000, 10000) * tm + r.uniform(0, 6.28)) for _ in range(3)) * env(m, tau, 0.0002)
        add(x, shard, n_of(tt), r.uniform(0.05, 0.3) * np.exp(-tt / 0.4))
    x = x + 0.3 * conv(x, outdoor_ir(0.8, 0.25, 6000, level=0.5, seed=seed + 1))
    return fade(norm(x, 0.8), 0, 0.05)


def impact(seed):
    r = rng(seed)
    n = n_of(0.3)
    x = norm(filt(r.standard_normal(n), hp=800, lp=4500) * env(n, 0.012, 0.0001), 1)
    x = x + 0.7 * sweep(n, 180, 90, 0.01) * env(n, 0.02, 0.0005)
    for tt in r.uniform(0.01, 0.12, 5):
        m = n_of(0.006)
        add(x, filt(r.standard_normal(m), hp=1500, lp=6000) * env(m, 0.0015), n_of(tt), r.uniform(0.1, 0.35))
    return fade(norm(sat(x, 2.0), 0.85), 0, 0.03)


def thunder(seed):
    r = rng(seed)
    dur = 7.5
    n = n_of(dur)
    t = tvec(n)
    x = 0.4 * norm(filt(r.standard_normal(n), hp=700) * env(n, 0.06, 0.003), 1)
    rumble = filt(r.standard_normal(n), lp=180, order=3)
    shape = np.zeros(n)
    for start in np.sort(r.uniform(0.0, 4.0, 7)):
        att, dec = r.uniform(0.08, 0.3), r.uniform(0.5, 1.6)
        s = np.clip(t - start, 0, None)
        shape += r.uniform(0.4, 1.0) * (1 - np.exp(-s / att)) * np.exp(-s / dec) * (t >= start)
    x = x + norm(rumble * shape, 1)
    x = x + 0.6 * norm(sweep(n, 55, 32, 0.6) * env(n, 1.2, 0.1), 1)
    x = sat(x, 2.5)
    x = x + 0.7 * conv(x, outdoor_ir(3.0, 1.4, 900, level=0.8, seed=seed + 1))
    return fade(norm(x), 0, 0.6)


def radio_click(seed):
    r = rng(seed)
    n = n_of(0.2)
    x = np.zeros(n)
    x[0] = 1.0
    x[1] = -0.6
    hiss = filt(r.standard_normal(n_of(0.12)), hp=1200, lp=4000) * 0.25
    add(x, hiss, n_of(0.01))
    add(x, np.array([0.8, -0.5]), n_of(0.14))
    return fade(norm(filt(x, hp=400, lp=5000), 0.6), 0, 0.02)


def ui_click():
    n = n_of(0.07)
    t = tvec(n)
    x = (np.sin(2 * np.pi * 2200 * t) + 0.3 * np.sin(2 * np.pi * 3300 * t)) * env(n, 0.012, 0.0003)
    return fade(norm(x, 0.45), 0, 0.01)


def capture_chime():
    n = n_of(1.0)
    x = np.zeros(n)
    for at, f in ((0.0, 1318.5), (0.12, 1760.0)):
        m = n_of(0.85)
        tm = tvec(m)
        bell = (np.sin(2 * np.pi * f * tm) + 0.3 * np.sin(2 * np.pi * 2 * f * tm) + 0.1 * np.sin(2 * np.pi * 3.01 * f * tm)) * env(m, 0.3, 0.002)
        add(x, bell, n_of(at))
    return fade(norm(x, 0.55), 0, 0.05)


# ---------------------------------------------------------------------------
# Seamless loops (every component is periodic or wrapped around the loop)
# ---------------------------------------------------------------------------
def engine(seed, L, fire_hz, lp, harmonics, clatter_hz=0.0, clatter_gain=0.0, whine_hz=0.0, whine_gain=0.0, drive=2.0):
    r = rng(seed)
    n = n_of(L)
    t = tvec(n)
    pulses = 2 * int(round(fire_hz * L / 2))  # even, so half-order tones loop too
    fire = pulses / L
    buf = np.zeros(n)
    m = n_of(1.2 / fire)
    for k in range(pulses):
        pos = (k + r.normal(0, 0.04)) / fire
        grain = r.standard_normal(m) * env(m, 0.25 / fire, 0.0005)
        add(buf, grain, int(round(pos * SR)), 1 + r.normal(0, 0.12), circular=True)
    x = norm(filt(buf, lp=lp, hp=25, order=2, circular=True), 1)
    tone = np.zeros(n)
    for h, a in enumerate(harmonics, 1):
        tone += a * np.sin(2 * np.pi * (fire / 2) * h * t + r.uniform(0, 2 * np.pi))
    x += 0.6 * norm(tone, 1)
    mech = filt(r.standard_normal(n), hp=1200, lp=5000, circular=True) * (0.6 + 0.4 * np.sin(2 * np.pi * fire * t))
    x += 0.12 * norm(mech, 1)
    if clatter_hz:
        cl = np.zeros(n)
        c = int(round(clatter_hz * L))
        mm = n_of(0.012)
        for k in range(c):
            grain = filt(r.standard_normal(mm), hp=1800, lp=7000) * env(mm, 0.0025)
            add(cl, grain, int(round((k + r.normal(0, 0.08)) * L / c * SR)), r.uniform(0.4, 1.0), circular=True)
        x += clatter_gain * norm(cl, 1)
    if whine_hz:
        x += whine_gain * np.sin(2 * np.pi * (round(whine_hz * L) / L) * t)
    return norm(sat(x, drive), 0.8)


def helicopter(seed, L=4.0):
    r = rng(seed)
    n = n_of(L)
    t = tvec(n)
    blades = int(round(11 * L))
    slap = np.zeros(n)
    m = n_of(0.08)
    for k in range(blades):
        g = 1.0 if k % 2 == 0 else 0.82  # slight rotor imbalance
        burst = norm(filt(r.standard_normal(m), lp=900) * env(m, 0.018, 0.002), 1) + 0.8 * np.sin(2 * np.pi * 75 * tvec(m)) * env(m, 0.02, 0.002)
        add(slap, burst, int(round(k * L / blades * SR)), g, circular=True)
    fv = 1 / L  # vibrato with whole cycles per loop
    def tone(f, a):
        f = round(f * L) / L
        return a * np.sin(2 * np.pi * (f * t + 0.6 * np.sin(2 * np.pi * fv * t)))
    whine = tone(2150, 1.0) + tone(4300, 0.35) + tone(6450, 0.1)
    tail = sum(np.sin(2 * np.pi * (round(92 * k * L) / L) * t) / k for k in (1, 3, 5, 7))
    hiss = filt(r.standard_normal(n), hp=800, lp=9000, circular=True) * (0.7 + 0.3 * np.cos(2 * np.pi * (blades / L) * t))
    x = norm(slap, 1) + 0.12 * norm(whine, 1) + 0.15 * norm(tail, 1) + 0.25 * norm(hiss, 1)
    return norm(sat(x, 1.8), 0.8)


def wind(seed, L=10.0):
    r = rng(seed)
    n = n_of(L)
    t = tvec(n)
    base = filt(r.standard_normal(n), lp=500, hp=40, order=2, circular=True)
    whistle = filt(r.standard_normal(n), hp=650, lp=1300, order=4, circular=True)
    gust = 0.55 + 0.45 * (0.6 * np.sin(2 * np.pi * t / L + r.uniform(0, 6.28)) + 0.4 * np.sin(2 * np.pi * 3 * t / L + r.uniform(0, 6.28)))
    x = norm(base, 1) * gust + 0.35 * norm(whistle, 1) * gust ** 3
    return norm(x, 0.7)


def rain(seed, L=6.0):
    r = rng(seed)
    n = n_of(L)
    x = 0.25 * norm(filt(r.standard_normal(n), hp=800, lp=8000, circular=True), 1)
    m = n_of(0.006)
    tm = tvec(m)
    for _ in range(4200):
        f, tau = r.uniform(1500, 6000), r.uniform(0.0008, 0.003)
        add(x, np.sin(2 * np.pi * f * tm) * env(m, tau, 0.0001), int(r.uniform(0, n)), min(1.0, 0.08 * r.pareto(3) + 0.02), circular=True)
    m = n_of(0.02)
    tm = tvec(m)
    for _ in range(160):  # heavier drips off roofs and leaves
        f, tau = r.uniform(500, 1500), r.uniform(0.004, 0.01)
        add(x, np.sin(2 * np.pi * f * tm) * env(m, tau, 0.0002), int(r.uniform(0, n)), r.uniform(0.1, 0.3), circular=True)
    return norm(filt(x, lp=9000, circular=True), 0.6)


def battle_ambience(seed, L=24.0):
    """Distant fighting: the battle over the hill, heard through the air."""
    r = rng(seed)
    n = n_of(L)
    x = np.zeros(n)
    far = [filt(gunshot(*GUNS[w]), lp=lpf, order=2) for w, lpf in (("rifle", 800), ("lmg", 650), ("rifle", 1200), ("hmg", 600))]
    t = 0.0
    while t < L:
        shot = far[r.integers(0, len(far))]
        g = float(np.clip(r.lognormal(np.log(0.12), 0.6), 0.03, 0.4))
        if r.random() < 0.55:  # automatic burst
            for k in range(int(r.integers(3, 9))):
                add(x, shot, n_of(t + k * r.uniform(0.075, 0.11)), g * r.uniform(0.8, 1.1), circular=True)
        else:  # aimed single shots
            for k in range(int(r.integers(1, 4))):
                add(x, shot, n_of(t + k * r.uniform(0.5, 1.3)), g, circular=True)
        t += r.uniform(0.6, 2.2)
    for k in range(5):
        boom = filt(explosion(30 + k, 3.0, (80, 25), 0.4, 1.0, 300, 20, 5, 1.0), lp=320, order=2)
        add(x, boom, n_of(r.uniform(0, L)), r.uniform(0.25, 0.6), circular=True)
    x += 0.08 * norm(filt(r.standard_normal(n), lp=90, order=2, circular=True), 1)
    x = x + 0.5 * conv(x, outdoor_ir(2.5, 1.2, 1200, level=0.7, seed=seed + 1), circular=True)
    return norm(x, 0.6)


# ---------------------------------------------------------------------------
# Music: a small orchestral synth with a score for each piece
# ---------------------------------------------------------------------------
NOTE = {"C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6,
        "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11}


def midi(name):
    return 12 * (int(name[-1]) + 1) + NOTE[name[:-1]]


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


TAB_N = 4096


def _table(H, kind):
    ph = np.arange(TAB_N) / TAB_N
    x = np.zeros(TAB_N)
    for k in range(1, H + 1):
        if kind == "saw":
            x += np.sin(2 * np.pi * k * ph) / k
        elif kind == "square" and k % 2:
            x += np.sin(2 * np.pi * k * ph) / k
        elif kind == "tri" and k % 2:
            x += (-1) ** ((k - 1) // 2) * np.sin(2 * np.pi * k * ph) / (k * k)
    return x / np.max(np.abs(x))


LEVELS = (4, 8, 16, 32, 64, 128)
TABLES = {kind: {H: _table(H, kind) for H in LEVELS} for kind in ("saw", "square", "tri")}


def osc(freq, n, kind="saw", phase0=0.0, vib=None):
    """Band-limited wavetable oscillator (no aliasing up to ~19 kHz)."""
    f = np.full(n, float(freq))
    if vib:
        rate, depth, delay = vib
        tt = tvec(n)
        f *= 1 + depth * np.sin(2 * np.pi * rate * tt) * np.clip((tt - delay) / 0.3, 0, 1)
    top = 19000 / float(np.max(f))
    H = max([h for h in LEVELS if h <= top] or [4])
    ph = (phase0 + np.cumsum(f) / SR) % 1.0
    idx = ph * TAB_N
    i0 = idx.astype(np.int64) % TAB_N
    frac = idx - np.floor(idx)
    tab = TABLES[kind][H]
    return tab[i0] * (1 - frac) + tab[(i0 + 1) % TAB_N] * frac


def adsr(n, a, d, s, r, hold):
    t = tvec(n)
    pre = np.where(t < a, t / max(a, 1e-4), s + (1 - s) * np.exp(-(t - a) / max(d, 1e-4)))
    at_rel = (hold / a) if hold < a else s + (1 - s) * np.exp(-(hold - a) / max(d, 1e-4))
    return np.where(t <= hold, pre, at_rel * np.exp(-(t - hold) / max(r, 1e-4)))


def pan(x, p):
    """Constant-power pan, p in [-1, 1]."""
    a = (p + 1) * np.pi / 4
    return np.stack([np.cos(a) * x, np.sin(a) * x])


class Mix:
    """Stereo stems; each stem gets one static filter at render time."""

    def __init__(self, seconds):
        self.n = n_of(seconds)
        self.stems = {}

    def stem(self, name):
        if name not in self.stems:
            self.stems[name] = np.zeros((2, self.n))
        return self.stems[name]

    def place(self, name, x, at, gain=1.0, p=0.0):
        add(self.stem(name), pan(x, p) if x.ndim == 1 else x, n_of(at), gain)


def strings(f, dur, vel, seed, a=0.35, r_=0.6):
    rr = rng(seed)
    n = n_of(dur + r_ * 5)
    e = adsr(n, a, 0.4, 0.85, r_, dur)
    x = sum(osc(f * 2 ** (c / 1200), n, "saw", rr.random()) for c in (-7, 0, 6))
    return x * e * vel


def ostinato_note(f, dur, vel, seed):
    rr = rng(seed)
    n = n_of(dur + 0.3)
    e = adsr(n, 0.008, 0.12, 0.55, 0.06, dur)
    x = osc(f, n, "saw", rr.random()) + 0.7 * osc(f * 1.004, n, "saw", rr.random())
    return x * e * vel


def brass(f, dur, vel, seed):
    rr = rng(seed)
    n = n_of(dur + 0.5)
    e = adsr(n, 0.06, 0.25, 0.8, 0.12, dur)
    vib = (5.2, 0.004, 0.25)
    x = osc(f, n, "saw", rr.random(), vib) * 0.75 + osc(f, n, "square", rr.random(), vib) * 0.25
    x += 0.5 * osc(f * 1.003, n, "saw", rr.random(), vib)
    return x * e * vel


def timpani(f, vel, seed, length=2.5):
    rr = rng(seed)
    n = n_of(length)
    t = tvec(n)
    fr = f * (1 + 0.04 * np.exp(-t / 0.05))
    body = sum(a * np.sin(2 * np.pi * np.cumsum(fr * k) / SR + rr.random()) * np.exp(-t / tau)
               for k, a, tau in ((1.0, 1.0, 0.7), (1.5, 0.45, 0.45), (1.99, 0.25, 0.3)))
    hit = filt(rr.standard_normal(n), lp=1200, hp=60) * env(n, 0.02, 0.0005)
    return (0.85 * body + 0.4 * norm(hit, 1)) * (1 - np.exp(-t / 0.002)) * vel


def snare(vel, seed):
    rr = rng(seed)
    n = n_of(0.35)
    noise = filt(rr.standard_normal(n), hp=1500, lp=9000) * env(n, 0.075, 0.0003)
    tone = np.sin(2 * np.pi * 190 * tvec(n)) * env(n, 0.03, 0.0003)
    return (norm(noise, 1) + 0.5 * tone) * vel


def bass_drum(vel, seed):
    n = n_of(0.8)
    return (sweep(n, 70, 45, 0.04) * env(n, 0.25, 0.001) + 0.15 * filt(rng(seed).standard_normal(n), lp=2500) * env(n, 0.006)) * vel


def crash(vel, seed):
    rr = rng(seed)
    n = n_of(3.5)
    x = np.stack([filt(rr.standard_normal(n), hp=4500, lp=14000) for _ in range(2)]) * env(n, 1.1, 0.002)
    return norm(x, 1) * vel


CHORDS = {"Dm": ("D", "F", "A"), "Bb": ("Bb", "D", "F"), "F": ("F", "A", "C"), "C": ("C", "E", "G"),
          "Gm": ("G", "Bb", "D"), "A": ("A", "C#", "E"), "D": ("D", "F#", "A"), "G": ("G", "B", "D")}


def root_in(chord, lo, hi):
    pc = NOTE[CHORDS[chord][0]]
    m = lo + ((pc - lo) % 12)
    return m if m <= hi else m - 12


def voicing(chord, lo):
    """Chord tones as midi notes, the lowest at or above lo."""
    out = []
    for name in CHORDS[chord]:
        pc = NOTE[name]
        out.append(lo + ((pc - lo) % 12))
    return sorted(out)


def render(mix, filters, rev_decay, rev_level, loop_seconds=None, seed=0):
    """Filter each stem, sum, add hall reverb, master. With loop_seconds the
    tails are folded back onto the start so the piece loops seamlessly."""
    out = np.zeros((2, mix.n))
    for name, x in mix.stems.items():
        lp, hp, peaks, gain = filters.get(name, (None, None, (), 1.0))
        out += gain * (filt(x, lp=lp, hp=hp, peaks=peaks) if (lp or hp or peaks) else x)
    ir = outdoor_ir(3.0, rev_decay, 5000, early=((0.023, 0.3), (0.041, 0.25), (0.067, 0.2), (0.093, 0.15)), level=0.8, seed=seed, stereo=True)
    if loop_seconds:
        L = n_of(loop_seconds)
        folded = out[:, :L].copy()
        tail = out[:, L:]
        add(folded, tail, 0, 1.0, circular=True)
        wet = np.stack([conv(folded[c], ir[c], circular=True) for c in range(2)])
        out = folded + rev_level * wet
    else:
        wet = np.stack([conv(out[c], ir[c]) for c in range(2)])
        out = out + rev_level * wet
    out = np.tanh(norm(out, 1.0) * 1.3) / np.tanh(1.3)
    return norm(out, 0.85)


MUSIC_FILTERS = {
    "ost": (1500, 40, (), 0.55),
    "pad": (2600, 90, (), 0.45),
    "brass": (2200, 150, ((1200, 4, 0.8),), 0.6),
    "timp": (None, None, (), 0.9),
    "snare": (None, 120, (), 0.35),
    "kick": (None, None, (), 0.7),
    "crash": (None, None, (), 0.25),
}


def menu_theme():
    bpm = 96
    beat = 60 / bpm
    bar = 4 * beat
    A = ["Dm", "Dm", "Bb", "Bb", "F", "F", "C", "C"]
    C = ["Gm", "Gm", "Bb", "Bb", "Dm", "Dm", "A", "A"]
    bars = A + A + C
    L = len(bars) * bar
    mix = Mix(L + 5.0)
    seed = 1000
    for b, ch in enumerate(bars):
        t0 = b * bar
        section = b // 8
        root = root_in(ch, 38, 49)
        for k, (iv, acc) in enumerate(zip((0, 0, 12, 0, 7, 0, 12, 7), (1.0, 0.6, 0.75, 0.6, 0.9, 0.6, 0.75, 0.65))):
            seed += 1
            mix.place("ost", ostinato_note(hz(root + iv), beat / 2 * 0.9, acc, seed), t0 + k * beat / 2, 1.0, -0.25)
        if b % 2 == 0:
            for j, m in enumerate(voicing(ch, 53)):
                seed += 1
                mix.place("pad", strings(hz(m), 2 * bar - 0.1, 0.5, seed), t0, 1.0, (-0.6, 0.1, 0.6)[j])
                seed += 1
                mix.place("pad", strings(hz(m + 12), 2 * bar - 0.1, 0.22, seed), t0, 1.0, (0.5, -0.5, 0.0)[j])
        tim = hz(root_in(ch, 38, 49) - 12 if root_in(ch, 38, 49) > 44 else root_in(ch, 38, 49))
        seed += 1
        mix.place("timp", timpani(tim, 0.9, seed), t0, 1.0, 0.1)
        seed += 1
        mix.place("timp", timpani(tim, 0.45 if section == 0 else 0.7, seed), t0 + 2 * beat, 1.0, 0.1)
        if b % 8 == 7:  # roll into the next phrase
            for k in range(8):
                seed += 1
                mix.place("timp", timpani(tim, 0.25 + 0.06 * k, seed, 0.8), t0 + 3 * beat + k * beat / 8, 1.0, 0.1)
        if section >= 1:
            for k in range(8):
                seed += 1
                v = 0.85 if k in (2, 6) else 0.28
                mix.place("snare", snare(v, seed), t0 + k * beat / 2, 1.0, 0.2)
            if b % 2 == 1:
                for k in range(4):
                    seed += 1
                    mix.place("snare", snare(0.3 + 0.12 * k, seed), t0 + 3.5 * beat + k * beat / 8, 1.0, 0.2)
        if section == 2:
            for at in (0, 2, 3.5):
                seed += 1
                mix.place("kick", bass_drum(0.9, seed), t0 + at * beat, 1.0, 0.0)
        if b in (8, 16):
            seed += 1
            mix.place("crash", crash(1.0, seed), t0, 1.0, 0.0)
    melody = {
        8: [("A3", 1), ("D4", 1), ("E4", 1), ("F4", 1)], 9: [("A4", 3), ("G4", 1)],
        10: [("F4", 2), ("D4", 2)], 11: [("F4", 3), ("Bb3", 1)],
        12: [("C4", 1), ("F4", 1), ("G4", 1), ("A4", 1)], 13: [("C5", 3), ("Bb4", 1)],
        14: [("A4", 2), ("G4", 2)], 15: [("E4", 4)],
        16: [("G4", 2), ("Bb4", 2)], 17: [("D5", 3), ("C5", 1)],
        18: [("Bb4", 2), ("F4", 2)], 19: [("D5", 4)],
        20: [("A4", 2), ("F4", 2)], 21: [("D5", 3), ("E5", 1)],
        22: [("C#5", 2), ("E5", 2)], 23: [("A4", 4)],
    }
    for b, notes in melody.items():
        t = b * bar
        for name, beats in notes:
            seed += 1
            mix.place("brass", brass(hz(midi(name)), beats * beat * 0.95, 0.8, seed), t, 1.0, 0.15)
            t += beats * beat
    return render(mix, MUSIC_FILTERS, 1.1, 0.35, loop_seconds=L, seed=77), L


def victory_sting():
    beat = 60 / 96
    mix = Mix(11.0)
    seed = 5000
    lead = [("D5", 0, 1), ("D5", 1, 0.5), ("D5", 1.5, 0.5), ("F#5", 2, 1), ("A5", 3, 1),
            ("G5", 4, 2), ("E5", 6, 1), ("F#5", 7, 1), ("A5", 8, 6)]
    for name, at, dur in lead:
        seed += 1
        mix.place("brass", brass(hz(midi(name)), dur * beat * 0.95, 0.9, seed), at * beat, 1.0, 0.1)
    for ch, at, dur in (("D", 0, 4), ("G", 4, 2), ("A", 6, 2), ("D", 8, 6)):
        for j, m in enumerate(voicing(ch, 50) + voicing(ch, 62)):
            seed += 1
            mix.place("pad", strings(hz(m), dur * beat - 0.05, 0.45, seed, a=0.08, r_=0.9), at * beat, 1.0, (-0.6, 0.0, 0.6)[j % 3])
        seed += 1
        mix.place("brass", brass(hz(root_in(ch, 45, 56)), dur * beat * 0.95, 0.6, seed), at * beat, 1.0, -0.2)
    for at, note in ((0, "D2"), (2, "A1"), (4, "G1"), (6, "A1")):
        seed += 1
        mix.place("timp", timpani(hz(midi(note)) * 2, 0.9, seed), at * beat, 1.0, 0.1)
    for k in range(16):  # roll into the final chord
        seed += 1
        mix.place("timp", timpani(hz(midi("A2")), 0.2 + 0.05 * k, seed, 0.6), (6 + k / 8) * beat, 1.0, 0.1)
    seed += 1
    mix.place("timp", timpani(hz(midi("D2")), 1.0, seed, 3.0), 8 * beat, 1.0, 0.1)
    seed += 1
    mix.place("crash", crash(1.0, seed), 8 * beat, 1.0, 0.0)
    for at in (0, 4, 8):
        seed += 1
        mix.place("kick", bass_drum(1.0, seed), at * beat, 1.0, 0.0)
    out = render(mix, MUSIC_FILTERS, 1.3, 0.4, seed=78)
    return fade(out, 0, 1.2)


def defeat_sting():
    beat = 60 / 72
    mix = Mix(14.0)
    seed = 7000
    for ch, at, low in (("Dm", 0, 38), ("Bb", 4, 34), ("Gm", 8, 31), ("Dm", 12, 38)):
        dur = 4 * beat if at < 12 else 5 * beat
        for j, m in enumerate([low, low + 7, low + 12] + voicing(ch, low + 15)):
            seed += 1
            mix.place("pad", strings(hz(m), dur - 0.1, 0.5 if j < 3 else 0.35, seed, a=0.6, r_=1.2), at * beat, 1.0, (-0.5, 0.5, 0.0, -0.3, 0.3, 0.0)[j % 6])
        seed += 1
        mix.place("timp", timpani(hz(low) * 2, 0.55, seed, 3.0), at * beat, 1.0, 0.1)
    for name, at, dur in (("A4", 0, 2), ("G4", 2, 1), ("F4", 3, 1), ("D4", 4, 2), ("C4", 6, 1), ("Bb3", 7, 1), ("A3", 8, 4), ("D4", 12, 5)):
        seed += 1
        mix.place("brass", brass(hz(midi(name)), dur * beat * 0.95, 0.55, seed), at * beat, 1.0, 0.15)
    for k in range(int(4 * beat * 16)):  # distant snare roll fading out
        seed += 1
        mix.place("snare", snare(0.18 * (1 - k / (4 * beat * 16)), seed), 12 * beat + k / 16, 1.0, 0.25)
    out = render(mix, {**MUSIC_FILTERS, "brass": (1600, 150, ((900, 3, 0.8),), 0.6)}, 1.6, 0.45, seed=79)
    return fade(out, 0, 2.0)


# ---------------------------------------------------------------------------
# Radio voice treatment
# ---------------------------------------------------------------------------
def decode(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f64le", "-ac", "1", "-ar", str(SR), "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float64).copy()


def radio_voice(x, seed):
    r = rng(seed)
    # trim silence
    a = np.abs(x)
    level = 10 ** (-42 / 20) * float(np.max(a))
    idx = np.nonzero(a > level)[0]
    if len(idx):
        x = x[max(0, idx[0] - n_of(0.03)):min(len(x), idx[-1] + n_of(0.08))]
    # handheld radio: narrow band, compressed, a little grit
    x = filt(x, hp=350, lp=3200, order=3, peaks=((1800, 3, 0.6),))
    rms = np.sqrt(np.convolve(x ** 2, np.ones(n_of(0.02)) / n_of(0.02), "same")) + 1e-4
    gain = (0.12 / rms) ** 0.5
    gain = np.convolve(gain, np.ones(n_of(0.01)) / n_of(0.01), "same")
    x = sat(x * np.minimum(gain, 6.0), 2.2)
    open_n, close_n = n_of(0.11), n_of(0.16)
    n = open_n + len(x) + close_n
    out = np.zeros(n)
    hiss = filt(r.standard_normal(n), hp=900, lp=4000) * 0.02
    out += hiss
    out[0] += 0.9
    out[1] -= 0.6
    add(out, filt(r.standard_normal(n_of(0.07)), hp=1000, lp=4000) * 0.18 * env(n_of(0.07), 0.03), n_of(0.005))
    add(out, x * 0.85, open_n)
    tail = filt(r.standard_normal(close_n), hp=1000, lp=4500) * 0.3 * env(close_n, 0.05, 0.002)
    add(out, tail, open_n + len(x) + n_of(0.02))
    return fade(norm(out, 0.9), 0, 0.01)


# ---------------------------------------------------------------------------
# Sheets
# ---------------------------------------------------------------------------
GAP = 0.3  # silence between clips so neighbours never bleed


def pack(clips, channels):
    """clips: [(name, samples, loop)] -> (sheet samples, {name: (start, length, loop)})."""
    parts, regions, pos = [], {}, n_of(0.05)
    parts.append(np.zeros((channels, pos)))
    for name, x, loop in clips:
        x = np.atleast_2d(x)
        if x.shape[0] != channels:
            x = np.repeat(x[:1], channels, axis=0)
        regions[name] = (pos / SR, x.shape[1] / SR, loop)
        parts.append(x)
        gap = np.zeros((channels, n_of(GAP)))
        parts.append(gap)
        pos += x.shape[1] + gap.shape[1]
    return np.concatenate(parts, axis=1), regions


def encode(path, x, quality):
    path.parent.mkdir(parents=True, exist_ok=True)
    x = np.clip(np.atleast_2d(x), -1, 1).astype(np.float32)
    data = x.T.tobytes()  # interleaved
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "f32le", "-ar", str(SR), "-ac", str(x.shape[0]), "-i", "-",
                    "-c:a", "libvorbis", "-q:a", str(quality), str(path)], input=data, check=True)


def write_wav(path, x):
    x = np.atleast_2d(x)
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2").T.tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(x.shape[0])
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)


def lua_sprites(sheets):
    lines = [
        "--!strict",
        "-- GENERATED by Tools/audio/build_audio.py - do not edit by hand.",
        "-- Every game sound is a region of one of five uploaded sheets; see AudioIds.",
        "",
        "export type Region = { sheet: string, start: number, length: number, loop: boolean }",
        "",
        "local clips: { [string]: Region } = {",
    ]
    for sheet, regions in sheets.items():
        lines.append(f"\t-- {sheet}")
        for name, (start, length, loop) in regions.items():
            lines.append(f'\t["{name}"] = {{ sheet = "{sheet}", start = {start:.4f}, length = {length:.4f}, loop = {"true" if loop else "false"} }},')
    lines += ["}", "", "return {", "\tclips = clips,", f'\tsheets = {{ {", ".join(f"{json.dumps(s)}" for s in sheets)} }},', "}", ""]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=pathlib.Path)
    args = ap.parse_args()

    print("synthesising one-shots ...")
    sfx = [(name, gunshot(*p), False) for name, p in GUNS.items()]
    sfx += [
        ("rocket", rocket(21, 1.8, 0.6, 0.6, (2600, 900), 0.5), False),
        ("rpg", rocket(22, 1.4, 1.0, 0.45, (2200, 800), 0.4), False),
        ("mlrs_launch", rocket(23, 2.4, 0.8, 0.9, (1800, 600), 0.9), False),
        ("grenade", grenade_throw(24), False),
        ("explosion", explosion(25, 3.8, (85, 26), 0.35, 1.0, 320, 50, 6, 0.9), False),
        ("explosion_big", explosion(26, 6.0, (70, 18), 0.55, 1.8, 260, 90, 7, 1.4), False),
        ("debris", collapse(27), False),
        ("glass", glass(28), False),
        ("impact", impact(29), False),
        ("thunder", thunder(31), False),
        ("radio_click", radio_click(32), False),
        ("ui_click", ui_click(), False),
        ("capture", capture_chime(), False),
    ]
    print("synthesising loops ...")
    loops = [
        ("engine_tank", engine(41, 4.0, 30, 700, (1.0, 0.7, 0.5, 0.35, 0.2, 0.12), clatter_hz=13.5, clatter_gain=0.35, whine_hz=420, whine_gain=0.05, drive=2.6), True),
        ("engine_truck", engine(42, 4.0, 24, 900, (1.0, 0.8, 0.45, 0.3, 0.15), drive=2.2), True),
        ("engine_car", engine(43, 4.0, 45, 1400, (0.6, 1.0, 0.5, 0.3, 0.2, 0.1), drive=1.6), True),
        ("engine_heli", helicopter(44), True),
        ("wind", wind(45), True),
        ("rain", rain(46), True),
        ("battle_ambience", battle_ambience(47), True),
    ]
    print("composing music ...")
    theme, _ = menu_theme()
    music = [("music_menu", theme, True), ("music_victory", victory_sting(), False), ("music_defeat", defeat_sting(), False)]

    print("treating radio voice ...")
    raw = AUDIO / "Voice" / "raw"
    voice = {1: [], 2: []}
    for i, path in enumerate(sorted(raw.glob("*.mp3"))):
        team, line = path.stem.split("_", 1)
        voice[int(team)].append((f"voice_{team}_{line}", radio_voice(decode(path), 900 + i), False))
    if not voice[1] or not voice[2]:
        sys.exit("no voice lines found - run Tools/audio/gen_voice.py first")

    sheets = {}
    for sheet, clips, ch, q, out in (
        ("sfx", sfx, 1, 5, AUDIO / "SFX" / "sfx.ogg"),
        ("loops", loops, 1, 5, AUDIO / "SFX" / "loops.ogg"),
        ("music", music, 2, 6, AUDIO / "Music" / "music.ogg"),
        ("voice_blue", voice[1], 1, 4, AUDIO / "Voice" / "voice_blue.ogg"),
        ("voice_red", voice[2], 1, 4, AUDIO / "Voice" / "voice_red.ogg"),
    ):
        for name, x, _ in clips:
            if not np.all(np.isfinite(x)):
                sys.exit(f"{name}: non-finite samples")
        data, regions = pack(clips, ch)
        encode(out, data, q)
        sheets[sheet] = regions
        print(f"  {out.relative_to(ROOT)}  {data.shape[1] / SR:6.1f} s  {len(clips)} clips  {out.stat().st_size // 1024} KB")
        if args.preview:
            args.preview.mkdir(parents=True, exist_ok=True)
            for name, x, _ in clips:
                write_wav(args.preview / f"{name}.wav", x)
    SPRITES.write_text(lua_sprites(sheets))
    print(f"  {SPRITES.relative_to(ROOT)}  {sum(len(r) for r in sheets.values())} clips")


if __name__ == "__main__":
    main()
