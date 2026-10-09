"""Desenho de som leve e limpo (sem graves pesados): pad suave, ar, vidro, brilhos e assinatura.

Uso: python3 sound2.py eventos.sfx.json saida.wav duração
"""
import json
import sys
import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve
from scipy.io import wavfile

SR = 48000
EV = json.load(open(sys.argv[1]))
DUR = float(sys.argv[3])
N = int(DUR * SR) + SR
rng = np.random.default_rng(11)
DRY = np.zeros((2, N))
SEND = np.zeros((2, N))


def tt(d):
    return np.arange(max(1, int(d * SR))) / SR


def filt(x, kind, f, order=2):
    return sosfilt(butter(order, f, btype=kind, fs=SR, output='sos'), x)


def noise(d):
    return rng.standard_normal(max(1, int(d * SR)))


def hz(n):
    return 440 * 2 ** ((n - 69) / 12)


def env(n, a, r, c=2.0):
    t = np.arange(n) / SR
    d = n / SR
    return np.clip(np.minimum(1, t / max(a, 1e-4)) * np.minimum(1, (d - t) / max(r, 1e-4)), 0, 1) ** c


def place(sig, t0, gain=1., pan=0., rev=.3):
    i = int(round(t0 * SR))
    if sig.ndim == 1:
        sig = np.stack([sig * np.sqrt((1 - pan) / 2) * 1.414, sig * np.sqrt((1 + pan) / 2) * 1.414])
    if i < 0:
        sig = sig[:, -i:]
        i = 0
    n = min(sig.shape[1], N - i)
    if n <= 0:
        return
    DRY[:, i:i + n] += sig[:, :n] * gain
    SEND[:, i:i + n] += sig[:, :n] * gain * rev


def sweep(d, f0, f1, shape=lambda k: k, q=.5, seg=480):
    n = noise(d)
    out = np.zeros(len(n))
    for i in range(0, len(n), seg):
        fc = max(200, f0 + (f1 - f0) * shape(i / len(n)))
        out[i:i + seg] = filt(n[i:i + seg], 'bandpass', [fc * (1 - q / 2), min(fc * (1 + q), 22000)], 1)
    return out


def panned(s, p0, p1):
    p = np.linspace(p0, p1, len(s))
    return np.stack([s * np.sqrt((1 - p) / 2), s * np.sqrt((1 + p) / 2)]) * 1.414


def bell(f, d, amp=1., dec=2.5):
    t = tt(d)
    s = (np.sin(2 * np.pi * f * t) + .35 * np.sin(2 * np.pi * f * 2.0 * t) * np.exp(-t * dec * 1.5)
         + .12 * np.sin(2 * np.pi * f * 3.01 * t) * np.exp(-t * dec * 2.5) + .05 * np.sin(2 * np.pi * f * 4.2 * t) * np.exp(-t * dec * 4))
    return s * np.exp(-t * dec) * np.minimum(1, t / .004) * amp


# ======================= sons =======================
def s_pad(e):
    """cama ambiente suave e clara (acorde aberto, ataque lento)"""
    d = e['d']
    t = tt(d)
    chords = e.get('chords', [[60, 64, 67, 71, 74], [57, 64, 67, 72, 76]])
    seg = d / len(chords)
    out = np.zeros((2, len(t)))
    for ci, ch in enumerate(chords):
        a, b = int(ci * seg * SR), int(min(d, (ci + 1) * seg + 1.5) * SR)
        tl = t[: b - a]
        for j, n in enumerate(ch):
            for det, side in ((-.06, 0), (.06, 1)):
                f = hz(n) * 2 ** (det / 12)
                s = np.sin(2 * np.pi * f * tl + j) * (1 + .25 * np.sin(2 * np.pi * (.15 + .05 * j) * tl))
                out[side, a:b] += s / len(ch)
        out[:, a:b] *= env(b - a, 2.2, 1.8, 1.4)
    out = np.stack([filt(out[0], 'lowpass', 2800), filt(out[1], 'lowpass', 2800)])
    place(out * .22, e['t'], e['v'], rev=.65)


def s_whoosh(e):
    d = e.get('d', 1.0)
    k = tt(d) / d
    s = sweep(d, 900, 5200, lambda u: np.sin(np.pi * u) ** 1.4, q=.6) * np.sin(np.pi * k) ** 2.2 * .38
    place(panned(s, -.6, .6), e['t'], e['v'], rev=.4)


def s_air(e):
    d = .6
    t = tt(d)
    s = sweep(d, 3200, 6800, lambda k: k, q=.5) * np.exp(-t * 7) * np.minimum(1, t / .02) * .26
    place(s, e['t'], e['v'], pan=rng.uniform(-.4, .4), rev=.55)


def s_tick(e):
    t = tt(.25)
    s = (np.sin(2 * np.pi * 3136 * t) * .6 + np.sin(2 * np.pi * 4698 * t) * .3) * np.exp(-t * 38) * .09
    place(s, e['t'], e['v'], pan=rng.uniform(-.3, .3), rev=.45)


def s_pop(e):
    t = tt(.14)
    s = np.sin(2 * np.pi * np.cumsum(520 + 380 * np.minimum(1, t / .05)) / SR) * np.exp(-t * 30) * .22
    place(s, e['t'], e['v'], rev=.3)


def s_click(e):
    t = tt(.05)
    s = filt(noise(.05), 'bandpass', [3000, 10000]) * np.exp(-t * 300) * .35 + np.sin(2 * np.pi * 2600 * t) * np.exp(-t * 200) * .1
    place(s, e['t'], e['v'], rev=.25)


def s_riser(e):
    d = e.get('d', 1.2)
    t = tt(d)
    k = t / d
    s = sweep(d, 1500, 9000, lambda u: u ** 1.4, q=.4) * k ** 2 * .25
    sh = sum(np.sin(2 * np.pi * f * (1 + .5 * k) * t) for f in (1568, 2093, 2637)) * .018 * k ** 2
    place(s + sh, e['t'] - d, e['v'], rev=.5)


def s_bloom(e):
    """o PC acendendo: acorde brilhante que floresce + brilho"""
    d = 3.2
    out = np.zeros(int(d * SR))
    for i, n in enumerate((72, 76, 79, 83, 86, 91)):
        b = bell(hz(n), d - i * .045, .55 - i * .06, 1.3 + i * .2)
        st = int(i * .045 * SR)
        out[st:st + len(b)] += b[: len(out) - st]
    t = tt(d)
    swell = sweep(d, 4000, 9000, lambda k: k, q=.3) * np.exp(-t * 2.5) * np.minimum(1, t / .05) * .08
    place((out * .16 + swell), e['t'], e['v'], rev=.6)


def s_sparkle(e):
    d = e.get('d', 1.6)
    out = np.zeros((2, int(d * SR)))
    for _ in range(int(d * 16)):
        f = rng.choice([2093, 2349, 2637, 3136, 3520, 4186])
        g = bell(f, .6, .06, 7)
        st = int(rng.uniform(0, d - .6) * SR)
        p = rng.uniform(-1, 1)
        out[0, st:st + len(g)] += g * np.sqrt((1 - p) / 2)
        out[1, st:st + len(g)] += g * np.sqrt((1 + p) / 2)
    place(out * env(out.shape[1], .1, .6, 1), e['t'], e['v'], rev=.65)


def s_chime(e):
    out = np.zeros(int(2.6 * SR))
    for i, n in enumerate((84, 88, 91)):
        b = bell(hz(n), 2.6 - i * .08, .5, 1.8)
        st = int(i * .08 * SR)
        out[st:st + len(b)] += b[: len(out) - st]
    place(out * .14, e['t'], e['v'], rev=.6)


def s_tone(e):
    """assinatura sonora do logo"""
    out = np.zeros(int(3.4 * SR))
    for i, (n, a) in enumerate(((76, .5), (83, .38), (88, .3), (95, .12))):
        b = bell(hz(n), 3.4 - i * .06, a, 1.2 + i * .3)
        st = int(i * .06 * SR)
        out[st:st + len(b)] += b[: len(out) - st]
    place(out * .2, e['t'], e['v'], rev=.65)


def s_suck(e):
    d = e.get('d', 2.4)
    t = tt(d)
    k = t / d
    s = sweep(d, 6000, 1200, lambda u: u ** .8, q=.6) * k ** 1.3 * np.exp(-np.maximum(t - d * .85, 0) * 18) * .3
    place(panned(s, .7, -.8), e['t'], e['v'], rev=.45)


def s_scan(e):
    d = e.get('d', 2.6)
    t = tt(d)
    s = sweep(d, 7000, 2500, lambda k: k, q=.25) * env(len(t), .3, .5, 1) * .14
    sh = sum(np.sin(2 * np.pi * f * t + 3 * np.sin(2 * np.pi * 5 * t)) for f in (2637, 3951)) * .012 * env(len(t), .4, .6, 1)
    place(panned(s + sh, .6, -.6), e['t'], e['v'], rev=.45)


def s_grains(e):
    d = e.get('d', 3.0)
    n = int(d * SR)
    out = np.zeros((2, n))
    for _ in range(int(d * e.get('rate', 40))):
        st = int(rng.uniform(0, d - .03) * SR)
        g = tt(.01 + .015 * rng.random())
        gr = np.sin(2 * np.pi * rng.uniform(3500, 9000) * g) * np.exp(-g * 350) * rng.uniform(.2, 1) * .035
        p = rng.uniform(-1, 1)
        out[0, st:st + len(g)] += gr * np.sqrt((1 - p) / 2)
        out[1, st:st + len(g)] += gr * np.sqrt((1 + p) / 2)
    place(out * np.linspace(e.get('a0', .5), e.get('a1', 1), n), e['t'], e['v'], rev=.5)


def s_count(e):
    """contador subindo: ticks cada vez mais rápidos"""
    d = e.get('d', 1.0)
    k = 0.0
    while k < d:
        place(np.sin(2 * np.pi * (2400 + 1200 * k / d) * tt(.03)) * np.exp(-tt(.03) * 160) * .05, e['t'] + k, e['v'], rev=.3)
        k += .09 * (1 - .6 * k / d)


FX = {k[2:]: f for k, f in globals().items() if k.startswith('s_')}
for e in EV:
    FX[e['kind']](e)


def make_ir(d=2.0):
    t = tt(d)
    ir = []
    for ch in range(2):
        n = rng.standard_normal(len(t)) * np.exp(-t * 3.4)
        out = np.zeros(len(t))
        for i in range(0, len(t), 2400):
            out[i:i + 2400] = filt(n[i:i + 2400], 'lowpass', 11000 * np.exp(-i / SR * 1.2) + 1500, 1)
        out = np.concatenate([np.zeros(int(.018 * SR)), out])[:len(t)]
        ir.append(out / np.sqrt(np.sum(out ** 2)))
    return ir


IR = make_ir()
WET = np.stack([fftconvolve(SEND[0], IR[0])[:N], fftconvolve(SEND[1], IR[1])[:N]])
mix = DRY + WET * .8
mix = filt(mix, 'highpass', 110)              # nada de grave pesado
mix = mix[:, :int(DUR * SR)]
fn = int(.6 * SR)
mix[:, -fn:] *= np.linspace(1, 0, fn) ** 2
mix = np.tanh(mix / (np.max(np.abs(mix)) + 1e-9) * 1.05) / np.tanh(1.05) * .9
wavfile.write(sys.argv[2], SR, (mix.T * 32767).astype(np.int16))
print('ok', DUR, len(EV), 'eventos')
