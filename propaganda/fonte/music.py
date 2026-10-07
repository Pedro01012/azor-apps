"""Trilha + efeitos sintetizados para a propaganda do AZOR (128 BPM, F# menor), sincronizados com comp.html."""
import sys
import numpy as np
from scipy.signal import butter, sosfilt
from scipy.io import wavfile

SR = 48000
BEAT = 60 / 128
BAR = BEAT * 4
DUR = BAR * 17 + 0.2
N = int(DUR * SR)
rng = np.random.default_rng(7)
L = np.zeros(N)
R = np.zeros(N)


def tt(d):
    return np.arange(int(d * SR)) / SR


def add(sig, t0, gain=1.0, pan=0.0):
    i = int(t0 * SR)
    if i >= N:
        return
    sig = sig[: N - i]
    gl, gr = gain * np.sqrt((1 - pan) / 2) * 1.414, gain * np.sqrt((1 + pan) / 2) * 1.414
    L[i:i + len(sig)] += sig * gl
    R[i:i + len(sig)] += sig * gr


def filt(x, kind, f, order=2):
    sos = butter(order, f, btype=kind, fs=SR, output='sos')
    return sosfilt(sos, x)


def hz(note):  # nome MIDI -> Hz
    return 440 * 2 ** ((note - 69) / 12)


# ---------- instrumentos ----------
def kick(big=False):
    t = tt(0.55 if big else 0.32)
    f = 45 + (150 if big else 120) * np.exp(-t * 28)
    ph = 2 * np.pi * np.cumsum(f) / SR
    env = np.exp(-t * (5 if big else 9))
    click = filt(rng.standard_normal(len(t)), 'highpass', 2500) * np.exp(-t * 300) * 0.4
    return np.tanh((np.sin(ph) * env + click) * 1.6)


def clap():
    t = tt(0.3)
    n = filt(rng.standard_normal(len(t)), 'bandpass', [900, 4000])
    env = np.zeros(len(t))
    for d in (0, 0.011, 0.022):
        i = int(d * SR)
        env[i:] += np.exp(-(t[: len(t) - i]) * 38)
    return n * env * 0.55


def hat(open_=False):
    t = tt(0.22 if open_ else 0.06)
    n = filt(rng.standard_normal(len(t)), 'highpass', 7000)
    return n * np.exp(-t * (18 if open_ else 70)) * 0.35


def boom():  # impacto grave + ruído
    t = tt(2.2)
    f = 30 + 70 * np.exp(-t * 6)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 1.6)
    n = filt(rng.standard_normal(len(t)), 'lowpass', 3500) * np.exp(-t * 4) * 0.5
    return np.tanh((s + n) * 1.8) * 0.9


def crash():
    t = tt(2.0)
    n = filt(rng.standard_normal(len(t)), 'highpass', 4000)
    return n * np.exp(-t * 2.2) * 0.35


def riser(d):
    t = tt(d)
    k = t / d
    n = rng.standard_normal(len(t))
    out = np.zeros(len(t))
    seg = 1200
    for i in range(0, len(t), seg):  # filtro passa-faixa subindo
        fc = 300 + 7000 * k[i] ** 2
        out[i:i + seg] = filt(n[i:i + seg], 'bandpass', [fc * 0.7, min(fc * 1.4, 20000)], 1)
    tone = np.sin(2 * np.pi * np.cumsum(200 + 900 * k ** 2) / SR) * 0.25
    return (out * 0.7 + tone) * k ** 1.5


def whoosh(d=0.45):
    t = tt(d)
    k = t / d
    n = rng.standard_normal(len(t))
    out = np.zeros(len(t))
    seg = 600
    for i in range(0, len(t), seg):
        fc = 400 + 5000 * np.sin(np.pi * k[i]) ** 2
        out[i:i + seg] = filt(n[i:i + seg], 'bandpass', [fc * 0.6, min(fc * 1.6, 20000)], 1)
    return out * np.sin(np.pi * k) ** 2 * 0.9


def blip(f=1800, d=0.07):
    t = tt(d)
    return np.sin(2 * np.pi * f * t) * np.exp(-t * 60) * 0.5


def mouse_click():
    t = tt(0.05)
    return filt(rng.standard_normal(len(t)), 'bandpass', [2000, 6000]) * np.exp(-t * 180) * 0.9


def pop():
    t = tt(0.18)
    f = 300 + 900 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 22) * 0.6


def chime(notes, d=1.6):
    t = tt(d)
    s = sum(np.sin(2 * np.pi * hz(n) * t) * np.exp(-t * (2.5 + i)) for i, n in enumerate(notes))
    return s * 0.25


def glitch(d=0.25):
    t = tt(d)
    sq = np.sign(np.sin(2 * np.pi * 110 * t)) * (np.floor(t * 60) % 2)
    return filt(sq + rng.standard_normal(len(t)) * 0.3, 'bandpass', [300, 3000]) * 0.35


def saw(f, t, det=(-0.12, -0.05, 0, 0.05, 0.12)):
    out = np.zeros(len(t))
    for d in det:
        ff = f * 2 ** (d / 12)
        ph = (t * ff + rng.random()) % 1
        out += 2 * ph - 1
    return out / len(det)


def pad(notes, d, cutoff=2400):
    t = tt(d)
    s = sum(saw(hz(n), t) for n in notes) / len(notes)
    env = np.minimum(1, t / 0.02) * np.minimum(1, (d - t) / 0.08)
    return filt(s, 'lowpass', cutoff) * env


def bass(note, d):
    t = tt(d)
    f = hz(note)
    s = np.sin(2 * np.pi * f * t) + 0.35 * np.tanh(3 * np.sin(2 * np.pi * f * 2 * t))
    env = np.minimum(1, t / 0.005) * np.minimum(1, (d - t) / 0.03)
    return s * env


def pluck(note, d=0.22):
    t = tt(d)
    s = saw(hz(note), t, (-0.06, 0, 0.06))
    return filt(s, 'lowpass', 3800) * np.exp(-t * 14)


# ---------- arranjo ----------
CHORDS = [  # F#m - D - A - E  (baixo, acorde)
    (42, [66, 69, 73]), (38, [62, 66, 69]), (45, [64, 69, 73]), (40, [64, 68, 71])]
music_bus = np.zeros(N)  # recebe sidechain
kicks = []

# Gancho (compassos 0-1): impactos nas frases + tique tenso
add(boom(), 0.0, 0.9)
add(glitch(), 0.0, 0.6)
add(kick(True), BEAT * 1, 1.0)
add(glitch(0.3), BEAT * 1, 0.5)
for i in range(int(BAR * 2 / (BEAT / 4))):
    t0 = i * BEAT / 4
    add(hat(), t0, 0.35 if i % 4 else 0.55, pan=0.3 if i % 2 else -0.3)
for b in range(3, 8):
    add(pop(), BEAT * b, 0.35)
music_bus_start = 0

# baixo grave pulsando no gancho
for b in range(8):
    seg = bass(42 - 12, BEAT * 0.9)
    i = int(b * BEAT * SR)
    music_bus[i:i + len(seg)] += seg[: N - i] * 0.5

# Problema (compassos 2-3): batida entra pela metade
for b in range(8, 16):
    kicks.append(b * BEAT)
    if b % 2:
        add(clap(), b * BEAT, 0.7)
    add(hat(), b * BEAT + BEAT / 2, 0.45)
    seg = bass(42 - 12, BEAT * 0.45)
    i = int((b * BEAT + BEAT / 2) * SR)
    music_bus[i:i + len(seg)] += seg * 0.55
add(boom(), BAR * 2 + BEAT * 1.5, 0.55)
for i in range(4):
    add(whoosh(0.3), BAR * 2 + BEAT * (3 + i) - 0.05, 0.35, pan=0.6)
    add(blip(900, 0.12), BAR * 2 + BEAT * (3 + i), 0.35)
# virada de caixa acelerando + riser até a revelação
add(riser(BAR), BAR * 3, 0.6)
for k in range(16):
    t0 = BAR * 3 + BAR * (1 - (1 - k / 16) ** 1.3)
    add(clap(), t0, 0.25 + 0.4 * k / 16)

# DROP (compasso 4 em diante)
drop = BAR * 4
add(boom(), drop, 1.0)
add(crash(), drop, 0.8)
end_bar = 17
for b in range(16, end_bar * 4):
    t0 = b * BEAT
    kicks.append(t0)
    if b % 2:
        add(clap(), t0, 0.65)
    add(hat(True), t0 + BEAT / 2, 0.35, pan=0.2)
    add(hat(), t0 + BEAT / 4, 0.18, pan=-0.4)
    add(hat(), t0 + 3 * BEAT / 4, 0.18, pan=0.4)
for bar in range(4, end_bar):
    root, ch = CHORDS[bar % 4]
    p = pad([n - 12 for n in ch] + ch, BAR, 2600 if bar >= 5 else 1600)
    i = int(bar * BAR * SR)
    music_bus[i:i + len(p)] += p[: N - i] * 0.55
    for s in range(8):  # baixo em colcheias
        bs = bass(root - 12 if s % 2 == 0 else root, BEAT / 2 * 0.95)
        j = int((bar * BAR + s * BEAT / 2) * SR)
        music_bus[j:j + len(bs)] += bs[: N - j] * 0.5
    if bar >= 5:  # arpejo
        arp = ch + [ch[0] + 12]
        for s in range(16):
            n = arp[[0, 1, 2, 3, 2, 1, 2, 3][s % 8]] + 12
            pl = pluck(n)
            j = int((bar * BAR + s * BEAT / 4) * SR)
            if j < N:
                seg = pl[: N - j]
                L[j:j + len(seg)] += seg * 0.12 * (0.7 if s % 2 else 1)
                R[j:j + len(seg)] += seg * 0.12 * (1 if s % 2 else 0.7)
for t0 in kicks:
    add(kick(), t0, 0.95)

# Sidechain no bus musical
env = np.ones(N)
for t0 in kicks:
    i = int(t0 * SR)
    d = int(0.22 * SR)
    seg = 1 - 0.8 * (1 - np.linspace(0, 1, d)) ** 2
    env[i:i + d] = np.minimum(env[i:i + d], seg[: max(0, min(d, N - i))])
music_bus *= env
L += music_bus * 0.8
R += music_bus * 0.8

# ---------- efeitos sincronizados com as cenas ----------
for tr in (BAR * 2, BAR * 7, BAR * 9, BAR * 11, BAR * 13, BAR * 15):
    add(whoosh(0.5), tr - 0.38, 0.6)
add(chime([78, 85, 90]), BAR * 4 + BEAT * 1.5, 0.4)          # tagline
c1, c2 = BAR * 5 + BEAT * 5, BAR * 5 + BEAT * 7               # cliques no app
for c in (c1, c2):
    add(mouse_click(), c, 0.9)
    add(blip(2400, 0.1), c, 0.35)
add(boom(), c2, 0.45)
for i in range(9):                                            # etapas do BOOST
    add(blip(1500 + i * 90, 0.06), BAR * 7 + i * BEAT * 0.85, 0.3, pan=0.3)
add(chime([73, 78, 81, 85, 90], 2.2), BAR * 9, 0.6)           # PRONTO
add(crash(), BAR * 9, 0.5)
add(chime([90, 94, 97], 1.6), BAR * 9 + BEAT * 7, 0.5)        # nota 97
for i in range(5):                                            # benefícios
    add(pop(), BAR * 11 + BEAT * (1 + i * 1.25), 0.6, pan=-0.3 if i % 2 else 0.3)
for i in range(4):                                            # checks
    add(blip(1200, 0.09), BAR * 13 + BEAT * (1 + i * 1.6), 0.5)
    add(pop(), BAR * 13 + BEAT * (1 + i * 1.6), 0.4)
add(boom(), BAR * 15, 0.8)                                    # CTA
add(crash(), BAR * 15, 0.6)
add(chime([66, 73, 78, 85], 2.5), BAR * 15 + BEAT * 2.5, 0.5)

# ---------- master ----------
mix = np.stack([L, R], 1)
mix = filt(mix.T, 'highpass', 25).T
fade = np.ones(N)
fn = int(0.4 * SR)
fade[-fn:] = np.linspace(1, 0, fn)
mix *= fade[:, None]
mix = np.tanh(mix / np.max(np.abs(mix)) * 1.6) / np.tanh(1.6)
mix *= 0.89
wavfile.write(sys.argv[1], SR, (mix * 32767).astype(np.int16))
print('ok', DUR)
