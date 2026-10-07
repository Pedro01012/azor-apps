"""Trilha suave + efeitos de interface para o vídeo estilo motion design (lê sfx.json do comp2.html)."""
import json
import sys
import numpy as np
from scipy.signal import butter, sosfilt
from scipy.io import wavfile

SR = 48000
DUR = float(sys.argv[3]) if len(sys.argv) > 3 else 23.2
N = int(DUR * SR)
BEAT = 0.5  # 120 BPM
rng = np.random.default_rng(11)
L = np.zeros(N)
R = np.zeros(N)
SFX = json.load(open(sys.argv[1]))
EV = {}
for e in SFX:
    EV.setdefault(e['kind'], []).append(e['t'])


def tt(d):
    return np.arange(int(d * SR)) / SR


def filt(x, kind, f, order=2):
    return sosfilt(butter(order, f, btype=kind, fs=SR, output='sos'), x)


def hz(n):
    return 440 * 2 ** ((n - 69) / 12)


def add(sig, t0, gain=1.0, pan=0.0, bus=None):
    i = int(t0 * SR)
    if i >= N or i < 0:
        return
    sig = sig[: N - i]
    gl, gr = gain * np.sqrt((1 - pan) / 2) * 1.414, gain * np.sqrt((1 + pan) / 2) * 1.414
    if bus is not None:
        bus[i:i + len(sig)] += sig * gain
        return
    L[i:i + len(sig)] += sig * gl
    R[i:i + len(sig)] += sig * gr


def noise(d):
    return rng.standard_normal(int(d * SR))


def sweep_bp(d, f0, f1, shape=lambda k: k, q=0.6, seg=600):
    t = tt(d)
    n = rng.standard_normal(len(t))
    out = np.zeros(len(t))
    for i in range(0, len(t), seg):
        fc = f0 + (f1 - f0) * shape(i / len(t))
        out[i:i + seg] = filt(n[i:i + seg], 'bandpass', [fc * (1 - q / 2), min(fc * (1 + q), 20000)], 1)
    return out


# ---------- efeitos ----------
def s_key(v):
    t = tt(0.045)
    c = filt(noise(0.045), 'bandpass', [1800 + 1500 * v, 7000]) * np.exp(-t * 160)
    thock = np.sin(2 * np.pi * (180 + 60 * v) * t) * np.exp(-t * 90) * 0.4
    return (c + thock) * 0.5


def s_click():
    t = tt(0.06)
    return (filt(noise(0.06), 'bandpass', [2500, 8000]) * np.exp(-t * 200) + np.sin(2 * np.pi * 1400 * t) * np.exp(-t * 120) * 0.3) * 0.7


def s_pop():
    t = tt(0.16)
    f = 260 + 700 * np.exp(-t * 35)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 26) * 0.6


def s_tick():
    t = tt(0.04)
    return np.sin(2 * np.pi * 2600 * t) * np.exp(-t * 140) * 0.35


def s_slide():
    t = tt(0.22)
    return sweep_bp(0.22, 900, 3500, q=0.5) * np.sin(np.pi * t / 0.22) ** 2 * 0.5


def s_whoosh(d=0.6):
    t = tt(d)
    k = t / d
    return sweep_bp(d, 300, 6000, lambda k: np.sin(np.pi * k / 2) ** 2) * (k ** 2) * 0.9


def s_swoosh():
    d = 0.9
    t = tt(d)
    k = t / d
    return sweep_bp(d, 500, 5000, lambda k: np.sin(np.pi * k)) * np.sin(np.pi * k) ** 2 * 0.8


def s_hit():
    t = tt(1.2)
    f = 42 + 80 * np.exp(-t * 14)
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.5)
    n = filt(noise(1.2), 'lowpass', 2500) * np.exp(-t * 9) * 0.35
    return np.tanh((sub + n) * 1.5) * 0.8


def s_bloom():
    d = 1.4
    t = tt(d)
    chord = sum(np.sin(2 * np.pi * hz(n) * t) for n in (77, 81, 84, 88)) / 4
    env = np.minimum(1, t / 0.05) * np.exp(-t * 1.6)
    air = filt(noise(d), 'highpass', 6000) * np.exp(-t * 3) * 0.25
    return (chord * env * 0.5 + air)


def s_open():
    t = tt(0.25)
    f = 500 + 900 * t / 0.25
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 14) * 0.35


def s_rise():
    d = 0.7
    return sweep_bp(d, 200, 3000, lambda k: k ** 2) * (tt(d) / d) ** 2 * 0.5


def s_boost():
    d = 1.6
    t = tt(d)
    f = 50 + 70 * np.exp(-t * 10)
    sub = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.5)
    sh = sum(np.sin(2 * np.pi * hz(n) * t) * np.exp(-t * (3 + i)) for i, n in enumerate((84, 88, 91, 96))) * 0.12
    return np.tanh(sub * 1.4) * 0.7 + sh


def s_success():
    d = 1.8
    t = tt(d)
    out = np.zeros(len(t))
    for i, n in enumerate((76, 81, 85, 88)):
        st = int(i * 0.07 * SR)
        tt2 = t[: len(t) - st]
        out[st:] += np.sin(2 * np.pi * hz(n) * tt2) * np.exp(-tt2 * 3) * (0.9 - i * 0.1)
    return out * 0.25


def s_word():
    t = tt(0.3)
    return (sweep_bp(0.3, 2000, 600, q=0.5) * np.exp(-t * 10) * 0.5 + np.sin(2 * np.pi * 180 * t) * np.exp(-t * 30) * 0.3)


def s_fall():
    d = 0.4
    t = tt(d)
    f = 1800 * np.exp(-t * 5) + 300
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * (t / d) * 0.12


def s_boop(v=1):
    t = tt(0.3)
    f = 110 + 220 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 12) * 0.8 * v


def s_riser():
    d = 0.8
    t = tt(d)
    tone = np.sin(2 * np.pi * np.cumsum(300 + 900 * (t / d) ** 2) / SR) * 0.15
    return (sweep_bp(d, 400, 8000, lambda k: k ** 1.5) * 0.5 + tone) * (t / d) ** 1.4


def s_sparkle():
    d = 1.2
    t = tt(d)
    out = np.zeros(len(t))
    for i in range(10):
        st = int(i * 0.045 * SR)
        n = 88 + int(rng.integers(0, 12))
        tt2 = t[: len(t) - st]
        out[st:] += np.sin(2 * np.pi * hz(n) * tt2) * np.exp(-tt2 * 9)
    return out * 0.12


def s_burst():
    d = 1.0
    out = np.zeros(int(d * SR))
    for i in range(9):
        p = s_pop() * (0.6 + 0.4 * rng.random())
        st = int(i * 0.05 * SR)
        out[st:st + len(p)] += p[: len(out) - st]
    t = tt(d)
    return out * 0.6 + filt(noise(d), 'highpass', 5000) * np.exp(-t * 6) * 0.15


def s_chime(v=1):
    d = 2.2
    t = tt(d)
    s = sum(np.sin(2 * np.pi * hz(n) * t) * np.exp(-t * (1.5 + i * 0.6)) for i, n in enumerate((81, 88, 93)))
    return s * 0.2 * v


def s_shimmer():
    d = 1.8
    t = tt(d)
    s = filt(noise(d), 'highpass', 7000) * np.sin(np.pi * t / d) ** 2 * 0.2
    for i, n in enumerate((93, 96, 100, 105)):
        st = 0.12 * i
        s += np.sin(2 * np.pi * hz(n) * t) * np.exp(-np.maximum(t - st, 0) * 4) * (t > st) * 0.06
    return s


FX = {'key': lambda v: s_key(v), 'click': lambda v: s_click() * v, 'pop': lambda v: s_pop() * v, 'tick': lambda v: s_tick() * v,
      'slide': lambda v: s_slide() * v, 'whoosh': lambda v: s_whoosh() * v, 'swoosh': lambda v: s_swoosh() * v, 'hit': lambda v: s_hit() * v,
      'bloom': lambda v: s_bloom() * v, 'open': lambda v: s_open() * v, 'rise': lambda v: s_rise() * v, 'boost': lambda v: s_boost() * v,
      'success': lambda v: s_success() * v, 'word': lambda v: s_word() * v, 'fall': lambda v: s_fall() * v, 'boop': lambda v: s_boop(v),
      'riser': lambda v: s_riser() * v, 'sparkle': lambda v: s_sparkle() * v, 'burst': lambda v: s_burst() * v, 'chime': lambda v: s_chime(v),
      'shimmer': lambda v: s_shimmer() * v}
OFFSET = {'whoosh': -0.45, 'riser': 0.0, 'fall': -0.02}
for e in SFX:
    k = e['kind']
    pan = (rng.random() - 0.5) * 0.5 if k in ('key', 'pop', 'tick') else 0
    add(FX[k](e['v']), e['t'] + OFFSET.get(k, 0), 0.9, pan)

# ---------- música ----------
def saw(f, t, det=(-0.1, 0, 0.1)):
    return sum(2 * ((t * f * 2 ** (d / 12) + rng.random()) % 1) - 1 for d in det) / len(det)


def pad(notes, d, cut):
    t = tt(d)
    s = sum(saw(hz(n), t) for n in notes) / len(notes)
    env = np.minimum(1, t / 0.4) * np.minimum(1, (d - t) / 0.4)
    return filt(s, 'lowpass', cut) * env


def pluck(n, d=0.35, cut=3000):
    t = tt(d)
    return filt(saw(hz(n), t, (-0.05, 0.05)), 'lowpass', cut) * np.exp(-t * 11)


def kick():
    t = tt(0.35)
    f = 48 + 90 * np.exp(-t * 30)
    return np.tanh(np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 8) * 1.4)


def snap():
    t = tt(0.18)
    return filt(noise(0.18), 'bandpass', [1500, 6000]) * np.exp(-t * 30) * 0.5


def shaker():
    t = tt(0.07)
    return filt(noise(0.07), 'highpass', 6500) * np.exp(-t * 50) * 0.25


T = {e['kind'] + str(i): e['t'] for i, e in enumerate(SFX)}
t_pill = min(EV['slide']) - 0.45       # entrada do seletor
t_app = EV['rise'][0]
t_words = EV['word'][0]
t_cta = EV['chime'][0] - 0.3
t_logo = EV['shimmer'][0] - 0.15
CH = [(53, [65, 69, 72, 76]), (52, [64, 67, 71, 74]), (50, [62, 65, 69, 72]), (48, [60, 64, 67, 71])]  # Fmaj7 Em7 Dm7 Cmaj7
music = np.zeros(N)
bar = BEAT * 4
nb = int(np.ceil(DUR / bar))
for b in range(nb):
    t0 = b * bar
    root, ch = CH[b % 4]
    cut = 900 if t0 < t_pill else 2200 if t0 < t_logo else 1200
    add(pad(ch, bar + 0.4, cut), t0, 0.32, bus=music)
    t = tt(bar)
    sub = np.sin(2 * np.pi * hz(root - 12) * t) * np.minimum(1, t / 0.05) * np.minimum(1, (bar - t) / 0.1)
    if t_pill <= t0 < t_logo:
        add(sub, t0, 0.35, bus=music)
    if t_app <= t0 < t_logo:  # arpejo
        arp = ch + [ch[0] + 12]
        for s in range(8):
            n = arp[[0, 2, 1, 3, 4, 3, 2, 1][s]] + 12
            add(pluck(n, cut=2600 if t0 < t_words else 4000), t0 + s * BEAT / 2, 0.08, pan=0.4 if s % 2 else -0.4)
kicks = []
for i in range(int(DUR / (BEAT / 2))):
    t0 = i * BEAT / 2
    beat = i // 2
    if t_pill <= t0 < t_cta:
        if i % 2 == 0:
            kicks.append(t0)
            add(kick(), t0, 0.55 if t0 < t_app else 0.75)
            if beat % 2 == 1 and t0 >= t_app:
                add(snap(), t0, 0.45)
        add(shaker(), t0, 0.5 if i % 2 else 0.25, pan=0.3)
    elif t_cta <= t0 < t_logo and i % 4 == 0:
        kicks.append(t0)
        add(kick(), t0, 0.5)
env = np.ones(N)
for k in kicks:
    i, d = int(k * SR), int(0.2 * SR)
    seg = 1 - 0.6 * (1 - np.linspace(0, 1, d)) ** 2
    env[i:i + d] = np.minimum(env[i:i + d], seg[: max(0, min(d, N - i))])
music *= env
L += music
R += music

mix = np.stack([L, R])
mix = filt(mix, 'highpass', 25)
fn = int(0.5 * SR)
mix[:, -fn:] *= np.linspace(1, 0, fn)
mix = np.tanh(mix / np.max(np.abs(mix)) * 1.3) / np.tanh(1.3) * 0.89
wavfile.write(sys.argv[2], SR, (mix.T * 32767).astype(np.int16))
print('ok', DUR, len(SFX), 'sfx')
