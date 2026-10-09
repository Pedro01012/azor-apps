"""Desenho de som da campanha AZOR (sem música): ambiente, impactos, texturas e assinatura sonora.

Uso: python3 sound.py eventos.sfx.json saida.wav duração
Cada evento: {t, kind, v, d?, f?, ...}. Tudo passa por uma reverberação de sala sintetizada.
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
rng = np.random.default_rng(7)
DRY = np.zeros((2, N))
SEND = np.zeros((2, N))


def tt(d):
    return np.arange(max(1, int(d * SR))) / SR


def filt(x, kind, f, order=2):
    return sosfilt(butter(order, f, btype=kind, fs=SR, output='sos'), x)


def noise(d):
    return rng.standard_normal(max(1, int(d * SR)))


def pink(d):
    n = noise(d)
    X = np.fft.rfft(n)
    f = np.fft.rfftfreq(len(n), 1 / SR)
    X[1:] /= np.sqrt(f[1:])
    X[0] = 0
    y = np.fft.irfft(X, len(n))
    return y / (np.std(y) + 1e-9)


def env_adsr(n, a, r, curve=2.0):
    t = np.arange(n) / SR
    d = n / SR
    e = np.minimum(1, t / max(a, 1e-4)) * np.minimum(1, (d - t) / max(r, 1e-4))
    return np.clip(e, 0, 1) ** curve


def place(sig, t0, gain=1.0, pan=0.0, rev=.25, width=0.0):
    """sig mono ou estéreo (2, n); pan -1..1; rev = quanto vai para a reverberação."""
    i = int(round(t0 * SR))
    if sig.ndim == 1:
        l = sig * np.sqrt((1 - pan) / 2) * 1.414
        r = sig * np.sqrt((1 + pan) / 2) * 1.414
        sig = np.stack([l, r])
    if i < 0:
        sig = sig[:, -i:]
        i = 0
    n = min(sig.shape[1], N - i)
    if n <= 0:
        return
    DRY[:, i:i + n] += sig[:, :n] * gain
    SEND[:, i:i + n] += sig[:, :n] * gain * rev


def stereo_noise(d, kind, f):
    return np.stack([filt(noise(d), kind, f), filt(noise(d), kind, f)])


def sweep_bp(d, f0, f1, shape=lambda k: k, q=.5, seg=480):
    n = noise(d)
    out = np.zeros(len(n))
    L = len(n)
    for i in range(0, L, seg):
        fc = max(40, f0 + (f1 - f0) * shape(i / L))
        out[i:i + seg] = filt(n[i:i + seg], 'bandpass', [fc * (1 - q / 2), min(fc * (1 + q), 22000)], 1)
    return out


# ======================= sons =======================
def s_amb(e):
    d = e.get('d', DUR)
    room = np.stack([filt(pink(d), 'lowpass', 380), filt(pink(d), 'lowpass', 380)]) * .05
    air = stereo_noise(d, 'highpass', 6000) * .004
    mov = 1 + .25 * np.sin(2 * np.pi * .07 * tt(d))
    sig = (room + air) * mov * env_adsr(len(mov), 1.5, 1.5, 1)
    place(sig, e['t'], e['v'], rev=.1)


def s_drone(e):
    d, f = e['d'], e.get('f', 41)
    t = tt(d)
    bright = e.get('bright', 0)
    s = np.sin(2 * np.pi * f * t) * .55 + np.sin(2 * np.pi * f * 2.003 * t) * .18 + np.sin(2 * np.pi * f * 3.01 * t) * .05 * (1 + bright)
    saw = sum(np.sin(2 * np.pi * f * k * 1.0015 * t) / k for k in range(1, 14))
    cut = 160 + 900 * bright * np.clip(t / 3, 0, 1)
    sw = np.zeros(len(t))
    seg = 4800
    for i in range(0, len(t), seg):
        sw[i:i + seg] = filt(saw[i:i + seg], 'lowpass', float(cut[min(i, len(t) - 1)]), 1)
    sig = (s + sw * .25) * env_adsr(len(t), 2.5, 2.0, 1.5)
    st = np.stack([sig * (1 + .1 * np.sin(2 * np.pi * .11 * t)), sig * (1 + .1 * np.cos(2 * np.pi * .13 * t))])
    place(st * .5, e['t'], e['v'], rev=.35)


def s_fanidle(e):
    d = e['d']
    s = filt(pink(d), 'bandpass', [180, 900]) * .25 + np.sin(2 * np.pi * 118 * tt(d)) * .02
    place(s * env_adsr(len(s), 1.2, .8, 1), e['t'], e['v'], pan=.1, rev=.1)


def s_spinup(e):
    d = e['d']
    t = tt(d)
    k = np.clip(t / 1.9, 0, 1) ** 1.5
    whoosh = sweep_bp(d, 260, 2400, lambda u: min(1, u * d / 1.9) ** 1.4, q=.7) * (.25 + .75 * k)
    whine = np.sin(2 * np.pi * np.cumsum(180 + 820 * k) / SR) * .035 * k
    sig = (whoosh * .5 + whine) * env_adsr(len(t), .05, 1.5, 1) * (1 - .45 * np.clip((t - 2.4) / 2, 0, 1))
    place(np.stack([sig, np.roll(sig, 180)]), e['t'], e['v'], rev=.2)


def s_air(e):
    d = .55
    t = tt(d)
    s = sweep_bp(d, 2600, 5200, lambda k: k, q=.6) * np.exp(-t * 7) * np.minimum(1, t / .015)
    place(s * .35, e['t'], e['v'], pan=rng.uniform(-.4, .4), rev=.5)


def s_cut(e):
    t = tt(.35)
    s = np.sin(2 * np.pi * (58 + 30 * np.exp(-t * 30)) * t) * np.exp(-t * 14) * .5
    place(s, e['t'], e['v'], rev=.15)


def s_glint(e):
    d = 2.2
    t = tt(d)
    k = t / d
    s = sweep_bp(d, 1500, 7000, lambda u: np.sin(np.pi * u), q=.4) * np.sin(np.pi * k) ** 2 * .3
    sh = sum(np.sin(2 * np.pi * f * t) for f in (2637, 3520, 4186)) * .01 * np.sin(np.pi * k) ** 3
    sig = s + sh
    pan = np.linspace(-.7, .7, len(t))
    place(np.stack([sig * np.sqrt((1 - pan) / 2), sig * np.sqrt((1 + pan) / 2)]) * 1.4, e['t'], e['v'], rev=.45)


def s_panel(e):
    d = .9
    t = tt(d)
    w = sweep_bp(d, 900, 4500, lambda k: k ** .7, q=.5) * np.exp(-t * 5) * np.minimum(1, t / .08) * .3
    ping = (np.sin(2 * np.pi * 1318 * t) + .5 * np.sin(2 * np.pi * 2637 * t)) * np.exp(-t * 9) * .05
    place(w + ping, e['t'], e['v'], rev=.55)


def s_swell(e):
    d = e.get('d', 1.0)
    t = tt(d)
    k = t / d
    s = (filt(noise(d), 'bandpass', [400, 6000]) * .35 + np.sin(2 * np.pi * np.cumsum(90 + 300 * k ** 3) / SR) * .25) * k ** 3
    place(s, e['t'], e['v'], rev=.6)


def s_click(e):
    t = tt(.05)
    s = filt(noise(.05), 'bandpass', [2200, 9000]) * np.exp(-t * 260) * .6 + np.sin(2 * np.pi * 1900 * t) * np.exp(-t * 180) * .18
    place(s, e['t'], e['v'], rev=.25)


def s_impact(e):
    soft = e.get('soft', 0)
    d = 3.2
    t = tt(d)
    sub = np.sin(2 * np.pi * np.cumsum(36 + 46 * np.exp(-t * 7)) / SR) * np.exp(-t * (1.3 + soft))
    thud = filt(noise(d), 'bandpass', [70, 320]) * np.exp(-t * 11) * .6
    air = filt(noise(d), 'highpass', 4000) * np.exp(-t * 18) * .12 * (1 - soft * .7)
    s = np.tanh((sub + thud) * 1.4) * .8 + air
    place(s * (.6 if soft else 1), e['t'], e['v'], rev=.4)


def s_powerup(e):
    d = e.get('d', 1.8)
    t = tt(d + 1.5)
    k = np.clip(t / d, 0, 1)
    lp = sweep_bp(d + 1.5, 200, 7000, lambda u: min(1, u * (d + 1.5) / d) ** 1.3, q=.9) * .3
    shimmer = sum(np.sin(2 * np.pi * f * t + rng.uniform(0, 6)) * (.5 + .5 * np.sin(2 * np.pi * (5 + i) * t)) for i, f in enumerate((1046, 1568, 2093, 3136))) * .02
    sub = np.sin(2 * np.pi * np.cumsum(30 + 25 * k) / SR) * .3
    envl = np.minimum(1, k ** 1.6) * np.exp(-np.maximum(t - d, 0) * 2.2)
    place((lp + shimmer + sub) * envl, e['t'], e['v'], rev=.5)


def s_whoosh(e):
    d = e.get('d', 1.2)
    t = tt(d)
    k = t / d
    s = sweep_bp(d, 220, 2600, lambda u: np.sin(np.pi * u) ** 1.5, q=.7) * np.sin(np.pi * k) ** 2 * .45
    pan = np.linspace(-.6, .6, len(t))
    place(np.stack([s * np.sqrt((1 - pan) / 2), s * np.sqrt((1 + pan) / 2)]) * 1.4, e['t'], e['v'], rev=.35)


def s_shimmer(e):
    d = e.get('d', 2.0)
    out = np.zeros((2, int(d * SR)))
    for i in range(int(d * 14)):
        f = rng.choice([2093, 2637, 3136, 3520, 4186, 5274])
        g = tt(.5)
        tone = np.sin(2 * np.pi * f * g) * np.exp(-g * 9) * .012
        st = int(rng.uniform(0, d - .5) * SR)
        p = rng.uniform(-1, 1)
        out[0, st:st + len(g)] += tone * np.sqrt((1 - p) / 2)
        out[1, st:st + len(g)] += tone * np.sqrt((1 + p) / 2)
    place(out * env_adsr(out.shape[1], .5, .8, 1), e['t'], e['v'], rev=.7)


def s_tone(e):
    """assinatura sonora: acorde de sino suave, sem melodia"""
    d = e.get('d', 2.6)
    t = tt(d)
    out = np.zeros(len(t))
    for f, a, dec in ((329.6, .5, 1.6), (493.9, .32, 2.0), (659.3, .22, 2.3), (987.8, .1, 3.0), (1318.5, .05, 3.6)):
        out += np.sin(2 * np.pi * f * t) * a * np.exp(-t * dec) + np.sin(2 * np.pi * f * 2.76 * t) * a * .06 * np.exp(-t * dec * 3)
    out *= np.minimum(1, t / .012)
    pad = filt(sum(np.sin(2 * np.pi * f * 1.002 * t) for f in (164.8, 246.9, 329.6)), 'lowpass', 900) * env_adsr(len(t), .6, 1.4, 1.2) * .06
    place((out * .22 + pad), e['t'], e['v'], rev=.55)


def s_grains(e):
    """lixo/partículas: estalinhos que crescem"""
    d = e.get('d', 3.0)
    n = int(d * SR)
    out = np.zeros((2, n))
    count = int(d * e.get('rate', 60))
    for i in range(count):
        k = i / count
        st = int(rng.uniform(0, d - .05) * SR)
        g = tt(.012 + .02 * rng.random())
        f = rng.uniform(2500, 9000)
        gr = np.sin(2 * np.pi * f * g) * np.exp(-g * 300) * rng.uniform(.3, 1) * .06
        p = rng.uniform(-1, 1)
        out[0, st:st + len(g)] += gr * np.sqrt((1 - p) / 2)
        out[1, st:st + len(g)] += gr * np.sqrt((1 + p) / 2)
    ramp = np.linspace(e.get('a0', .4), e.get('a1', 1), n)
    place(out * ramp, e['t'], e['v'], rev=.4)


def s_scan(e):
    d = e.get('d', 2.8)
    t = tt(d)
    hum = (np.sin(2 * np.pi * 98 * t) * .3 + np.sin(2 * np.pi * 196.4 * t) * .15 + np.sin(2 * np.pi * 784 * t + 2 * np.sin(2 * np.pi * 7 * t)) * .03)
    air = sweep_bp(d, 3000, 1200, lambda k: k, q=.3) * .12
    s = (filt(hum, 'lowpass', 1200) + air) * env_adsr(len(t), .4, .6, 1)
    pan = np.linspace(.6, -.6, len(t))
    place(np.stack([s * np.sqrt((1 - pan) / 2), s * np.sqrt((1 + pan) / 2)]) * 1.4 * .6, e['t'], e['v'], rev=.35)


def s_suck(e):
    d = e.get('d', 2.4)
    t = tt(d)
    k = t / d
    s = sweep_bp(d, 3500, 300, lambda u: u ** .8, q=.8) * (k ** 1.2) * np.exp(-np.maximum(t - d * .85, 0) * 20) * .5
    rot = np.sin(2 * np.pi * (1 + 5 * k) * t)
    place(np.stack([s * (.5 + .5 * rot), s * (.5 - .5 * rot)]) * 1.3, e['t'], e['v'], rev=.4)


def s_toggle(e):
    t = tt(.12)
    s = filt(noise(.12), 'bandpass', [1500, 6000]) * np.exp(-t * 120) * .4 + np.sin(2 * np.pi * 880 * t) * np.exp(-t * 40) * .08
    place(s, e['t'], e['v'], rev=.3)


def s_tick(e):
    t = tt(.03)
    place(np.sin(2 * np.pi * 3000 * t) * np.exp(-t * 200) * .08, e['t'], e['v'], rev=.3)


FX = {k[2:]: f for k, f in globals().items() if k.startswith('s_')}
for e in EV:
    FX[e['kind']](e)

# ======================= reverberação + master =======================
def make_ir(d=2.4):
    t = tt(d)
    ir = []
    for ch in range(2):
        n = rng.standard_normal(len(t)) * np.exp(-t * 3.0)
        out = np.zeros(len(t))
        seg = 2400
        for i in range(0, len(t), seg):
            fc = 9000 * np.exp(-i / SR * 1.6) + 600
            out[i:i + seg] = filt(n[i:i + seg], 'lowpass', fc, 1)
        pre = int(.022 * SR)
        out = np.concatenate([np.zeros(pre), out])[:len(t)]
        for dt, g in ((.011, .5), (.019, .35), (.031, .3), (.047, .22)):
            j = int((dt + ch * .003) * SR)
            out[j] += g
        ir.append(out / np.sqrt(np.sum(out ** 2)))
    return ir


IR = make_ir()
WET = np.stack([fftconvolve(SEND[0], IR[0])[:N], fftconvolve(SEND[1], IR[1])[:N]])
mix = DRY + WET * .9
mix = filt(mix, 'highpass', 28)
mix = mix[:, :int(DUR * SR)]
fn = int(.6 * SR)
mix[:, -fn:] *= np.linspace(1, 0, fn) ** 2
peak = np.max(np.abs(mix)) + 1e-9
mix = np.tanh(mix / peak * 1.15) / np.tanh(1.15) * .9
wavfile.write(sys.argv[2], SR, (mix.T * 32767).astype(np.int16))
print('ok', DUR, len(EV), 'eventos')
