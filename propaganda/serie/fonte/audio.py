"""Trilhas e efeitos sintetizados para a série de propagandas do AZOR.

Uso: python3 audio.py eventos.sfx.json saida.wav duração
Os eventos vêm do HTML de cada vídeo: {t, kind, v} para efeitos e {t, kind:'music', style, end} para trilha.
"""
import json
import sys
import numpy as np
from scipy.signal import butter, sosfilt
from scipy.io import wavfile

SR = 48000
EVENTS = json.load(open(sys.argv[1]))
DUR = float(sys.argv[3])
N = int(DUR * SR)
rng = np.random.default_rng(5)
L = np.zeros(N)
R = np.zeros(N)
MUS = np.zeros(N)     # bus da música (recebe sidechain do bumbo)
KICKS = []


def tt(d):
    return np.arange(max(1, int(d * SR))) / SR


def filt(x, kind, f, order=2):
    return sosfilt(butter(order, f, btype=kind, fs=SR, output='sos'), x)


def hz(n):
    return 440 * 2 ** ((n - 69) / 12)


def noise(d):
    return rng.standard_normal(max(1, int(d * SR)))


def add(sig, t0, gain=1.0, pan=0.0, bus=None):
    i = int(round(t0 * SR))
    if i >= N:
        return
    if i < 0:
        sig = sig[-i:]
        i = 0
    sig = sig[: N - i]
    if bus is not None:
        bus[i:i + len(sig)] += sig * gain
        return
    L[i:i + len(sig)] += sig * gain * np.sqrt(1 - pan)
    R[i:i + len(sig)] += sig * gain * np.sqrt(1 + pan)


def sweep(d, f0, f1, shape=lambda k: k, q=0.6, seg=600):
    n = noise(d)
    out = np.zeros(len(n))
    for i in range(0, len(n), seg):
        fc = max(60, f0 + (f1 - f0) * shape(i / len(n)))
        out[i:i + seg] = filt(n[i:i + seg], 'bandpass', [fc * (1 - q / 2), min(fc * (1 + q), 21000)], 1)
    return out


def tone(freqs, t):
    ph = 2 * np.pi * np.cumsum(freqs) / SR
    return np.sin(ph)


# ======================= EFEITOS =======================
def fx_pop(v):
    t = tt(.16)
    return tone(260 + 700 * np.exp(-t * 35), t) * np.exp(-t * 26) * .6


def fx_click(v):
    t = tt(.06)
    return (filt(noise(.06), 'bandpass', [2500, 8000]) * np.exp(-t * 200) + np.sin(2 * np.pi * 1400 * t) * np.exp(-t * 120) * .3) * .7


def fx_key(v):
    t = tt(.045)
    return (filt(noise(.045), 'bandpass', [1800 + 1500 * v, 7000]) * np.exp(-t * 160) + np.sin(2 * np.pi * 200 * t) * np.exp(-t * 90) * .4) * .5


def fx_whoosh(v):
    d = .55
    k = tt(d) / d
    return sweep(d, 300, 6000, lambda k: np.sin(np.pi * k / 2) ** 2) * k ** 2 * .9


def fx_swoosh(v):
    d = .7
    k = tt(d) / d
    return sweep(d, 500, 5000, lambda k: np.sin(np.pi * k)) * np.sin(np.pi * k) ** 2 * .8


def fx_hit(v):
    t = tt(1.4)
    sub = tone(40 + 90 * np.exp(-t * 14), t) * np.exp(-t * 3.2)
    n = filt(noise(1.4), 'lowpass', 3000) * np.exp(-t * 8) * .4
    return np.tanh((sub + n) * 1.6) * .85


def fx_riser(v, d=1.5):
    t = tt(d)
    k = t / d
    return (sweep(d, 300, 9000, lambda k: k ** 1.6) * .6 + tone(200 + 1200 * k ** 2, t) * .15) * k ** 1.5


def fx_boost(v):
    t = tt(1.6)
    sub = np.tanh(tone(50 + 70 * np.exp(-t * 10), t) * np.exp(-t * 2.5) * 1.4) * .7
    sh = sum(np.sin(2 * np.pi * hz(n) * t) * np.exp(-t * (3 + i)) for i, n in enumerate((84, 88, 91, 96))) * .12
    return sub + sh


def arp(notes, step, d, decay=3.0, amp=.25):
    t = tt(d)
    out = np.zeros(len(t))
    for i, n in enumerate(notes):
        st = int(i * step * SR)
        u = t[: len(t) - st]
        out[st:] += np.sin(2 * np.pi * hz(n) * u) * np.exp(-u * decay)
    return out * amp


def fx_success(v):
    return arp([76, 81, 85, 88], .07, 1.8)


def fx_chime(v):
    t = tt(2.2)
    return sum(np.sin(2 * np.pi * hz(n) * t) * np.exp(-t * (1.5 + i * .6)) for i, n in enumerate((81, 88, 93))) * .2


def fx_tick(v):
    t = tt(.04)
    return np.sin(2 * np.pi * 2600 * t) * np.exp(-t * 140) * .35


def fx_msg_in(v):  # "plim" de mensagem recebida
    t = tt(.35)
    a = np.sin(2 * np.pi * 1318 * t) * np.exp(-t * 18)
    b = np.sin(2 * np.pi * 1760 * t) * np.exp(-np.maximum(t - .07, 0) * 16) * (t > .07)
    return (a + b) * .28


def fx_msg_out(v):  # "fuup" de mensagem enviada
    t = tt(.18)
    return tone(500 + 900 * (t / .18), t) * np.exp(-t * 14) * .3


def fx_typing(v):  # alguns toques de teclado de celular
    out = np.zeros(int(.6 * SR))
    for i in range(6):
        k = fx_key(rng.random()) * .5
        st = int((i * .09 + rng.random() * .03) * SR)
        out[st:st + len(k)] += k[: len(out) - st]
    return out


def fx_notif(v):
    return arp([88, 95], .09, .8, 5, .3)


def fx_buzz(v):  # erro
    t = tt(.35)
    sq = np.sign(np.sin(2 * np.pi * 110 * t)) + .5 * np.sign(np.sin(2 * np.pi * 116 * t))
    return filt(sq, 'lowpass', 1800) * np.minimum(1, (0.35 - t) / .05) * .25


def fx_glitch(v):
    d = .3
    t = tt(d)
    sq = np.sign(np.sin(2 * np.pi * (90 + 400 * (np.floor(t * 40) % 3)) * t)) * (np.floor(t * 70) % 2)
    return filt(sq + noise(d) * .4, 'bandpass', [200, 4000]) * .35


def fx_rec(v):  # bipe de gravação
    t = tt(.25)
    return np.sin(2 * np.pi * 1000 * t) * (t < .12) * .3


def fx_crunch(v):  # esfarelar/desintegrar
    d = .22
    t = tt(d)
    n = filt(noise(d), 'bandpass', [1500 + 2500 * v, 9000]) * np.exp(-t * 18)
    grains = (rng.random(len(t)) > .985) * rng.standard_normal(len(t)) * 2
    return (n + filt(grains, 'highpass', 2000) * np.exp(-t * 10)) * .45


def fx_laser(v, d=2.0):  # zumbido do scanner
    t = tt(d)
    hum = np.sin(2 * np.pi * 110 * t) * .4 + np.sin(2 * np.pi * 220.7 * t) * .25 + np.sin(2 * np.pi * 440 * t + 3 * np.sin(2 * np.pi * 6 * t)) * .15
    env = np.minimum(1, t / .2) * np.minimum(1, (d - t) / .3)
    return hum * env * .25


def fx_vacuum(v, d=1.5):
    t = tt(d)
    return sweep(d, 1200, 300, lambda k: k) * np.minimum(1, t / .1) * np.exp(-t * 1.2) * .6


def fx_cash(v):  # caixa registradora
    bell = arp([93, 100], .06, 1.0, 4, .35)
    t = tt(.12)
    clk = filt(noise(.12), 'bandpass', [2000, 6000]) * np.exp(-t * 60) * .5
    bell[:len(clk)] += clk
    return bell


def fx_stamp(v):
    t = tt(.5)
    thud = tone(80 + 120 * np.exp(-t * 40), t) * np.exp(-t * 14)
    return np.tanh((thud + filt(noise(.5), 'lowpass', 1500) * np.exp(-t * 30) * .6) * 2) * .7


def fx_sparkle(v):
    t = tt(1.2)
    out = np.zeros(len(t))
    for i in range(10):
        st = int(i * .045 * SR)
        u = t[: len(t) - st]
        out[st:] += np.sin(2 * np.pi * hz(88 + int(rng.integers(0, 12))) * u) * np.exp(-u * 9)
    return out * .12


def fx_burst(v):
    out = np.zeros(int(1.0 * SR))
    for i in range(9):
        p = fx_pop(1) * (.6 + .4 * rng.random())
        st = int(i * .05 * SR)
        out[st:st + len(p)] += p[: len(out) - st]
    return out * .6


def fx_boop(v):
    t = tt(.3)
    return tone(110 + 220 * np.exp(-t * 30), t) * np.exp(-t * 12) * .8


def fx_ding(v):
    t = tt(1.2)
    return (np.sin(2 * np.pi * 1568 * t) + .4 * np.sin(2 * np.pi * 3136 * t)) * np.exp(-t * 4) * .25


def fx_alarm(v):
    t = tt(.9)
    f = np.where((t * 4) % 1 < .5, 880, 660)
    return filt(np.sign(np.sin(2 * np.pi * np.cumsum(f) / SR)), 'lowpass', 2500) * .18


def fx_scratch(v):  # "record scratch" de meme
    d = .45
    t = tt(d)
    f = 300 + 1500 * np.abs(np.sin(2 * np.pi * 3.3 * t))
    return filt(noise(d) * .6 + tone(f, t) * .5, 'bandpass', [300, 5000]) * np.exp(-t * 3) * .7


def fx_drop(v):  # 808 grave descendo
    t = tt(1.6)
    return np.tanh(tone(30 + 90 * np.exp(-t * 3), t) * np.exp(-t * 1.6) * 2.5) * .7


def fx_swipe(v):
    d = .25
    k = tt(d) / d
    return sweep(d, 2000, 6000, lambda k: k) * np.sin(np.pi * k) * .5


def fx_heart(v):
    out = np.zeros(int(.7 * SR))
    for st in (0, .18):
        t = tt(.25)
        b = tone(55 + 30 * np.exp(-t * 30), t) * np.exp(-t * 18)
        i = int(st * SR)
        out[i:i + len(b)] += b
    return np.tanh(out * 2) * .7


FX = {k[3:]: f for k, f in globals().items() if k.startswith('fx_')}


# ======================= MÚSICA =======================
def saw(f, t, det=(-.1, 0, .1)):
    return sum(2 * ((t * f * 2 ** (d / 12) + rng.random()) % 1) - 1 for d in det) / len(det)


def kick(hard=1.0):
    t = tt(.35)
    return np.tanh(tone(45 + 110 * np.exp(-t * 30), t) * np.exp(-t * 8) * 1.6 * hard)


def snare(bright=6000):
    t = tt(.22)
    return (filt(noise(.22), 'bandpass', [1200, bright]) * np.exp(-t * 22) * .7 + np.sin(2 * np.pi * 190 * t) * np.exp(-t * 30) * .4)


def clap():
    t = tt(.3)
    env = sum(np.exp(-np.maximum(t - d, 0) * 38) * (t >= d) for d in (0, .011, .022))
    return filt(noise(.3), 'bandpass', [900, 4000]) * env * .55


def hat(open_=False, d=None):
    d = d or (.22 if open_ else .05)
    t = tt(d)
    return filt(noise(d), 'highpass', 7000) * np.exp(-t * (16 if open_ else 80)) * .3


def b808(note, d, glide_from=None):
    t = tt(d)
    f0 = hz(note)
    f = f0 if glide_from is None else hz(glide_from) + (f0 - hz(glide_from)) * np.minimum(1, t / .08)
    s = tone(np.full(len(t), f) if np.isscalar(f) else f, t)
    env = np.minimum(1, t / .004) * np.exp(-t * .9) * np.minimum(1, (d - t) / .03)
    return np.tanh(s * env * 2.2) * .8


def cowbell(note, d=.22):
    t = tt(d)
    f = hz(note)
    s = np.sign(np.sin(2 * np.pi * f * t)) + np.sign(np.sin(2 * np.pi * f * 1.48 * t))
    return filt(s, 'bandpass', [f * .9, f * 4]) * np.exp(-t * 11) * .3


def rhodes(notes, d):
    t = tt(d)
    s = sum(np.sin(2 * np.pi * hz(n) * t + .8 * np.sin(2 * np.pi * hz(n) * 2 * t) * np.exp(-t * 3)) for n in notes) / len(notes)
    return s * np.exp(-t * .7) * np.minimum(1, t / .01) * (1 + .15 * np.sin(2 * np.pi * 4.5 * t))


def pad(notes, d, cut):
    t = tt(d)
    s = sum(saw(hz(n), t) for n in notes) / len(notes)
    return filt(s, 'lowpass', cut) * np.minimum(1, t / .3) * np.minimum(1, (d - t) / .3)


def pluck(n, d=.3, cut=3500):
    t = tt(d)
    return filt(saw(hz(n), t, (-.05, .05)), 'lowpass', cut) * np.exp(-t * 11)


def bell(n, d=.6):
    t = tt(d)
    return (np.sin(2 * np.pi * hz(n) * t) + .5 * np.sin(2 * np.pi * hz(n) * 2.76 * t) * np.exp(-t * 6)) * np.exp(-t * 3) * .3


def kick_at(t0, g=1.0, hard=1.0):
    KICKS.append(t0)
    add(kick(hard), t0, g)


def style_phonk(t0, t1, e):
    bpm = e.get('bpm', 130)
    b = 60 / bpm
    prog_ = [(42, [66, 69, 73, 71, 69, 66, 64, 66]), (38, [62, 66, 69, 68, 66, 64, 62, 61]),
             (40, [64, 68, 71, 69, 68, 66, 64, 63]), (37, [61, 65, 68, 66, 65, 63, 61, 60])]
    bar = 0
    t = t0
    while t < t1 - .01:
        root, mel = prog_[bar % 4]
        for s in range(8):  # cowbell em colcheias
            ts = t + s * b / 2
            if ts < t1:
                add(cowbell(mel[s] + 12), ts, .55, pan=.25 if s % 2 else -.25)
        for beat in range(4):
            tb = t + beat * b
            if tb >= t1:
                break
            if beat in (0,) or (beat == 2 and bar % 2 == 1):
                kick_at(tb, .9)
            if beat == 1 and bar % 2 == 0:
                kick_at(tb + b / 2, .7)
            if beat == 2:
                add(clap(), tb, .7)
                add(snare(), tb, .35)
            for h in range(2 if beat != 3 or bar % 2 == 0 else 6):  # rolinhos de hat
                step = b / (2 if beat != 3 or bar % 2 == 0 else 6)
                add(hat(), tb + h * step, .5 if h == 0 else .35, pan=.3)
        add(b808(root - 12, min(b * 2.8, t1 - t)), t, .75, bus=MUS)
        add(b808(root - 12, b * 1.1, glide_from=root - 7), t + b * 3, .6, bus=MUS)
        bar += 1
        t += b * 4


def style_trap(t0, t1, e):
    bpm = e.get('bpm', 140)
    b = 60 / bpm
    roots = [45, 45, 41, 43]
    mel = [[81, 84, 88, 84], [81, 84, 86, 84], [77, 81, 84, 81], [79, 83, 86, 83]]
    bar = 0
    t = t0
    while t < t1 - .01:
        r = roots[bar % 4]
        for s in range(4):
            add(bell(mel[bar % 4][s]), t + s * b, .5, pan=-.2 + .13 * s)
        kick_at(t, .9)
        kick_at(t + b * 1.5, .7)
        if bar % 2:
            kick_at(t + b * 2.75, .6)
        add(clap(), t + b * 2, .75)
        n = 0
        while n < 16:
            roll = (n in (12, 13) and bar % 2 == 1)
            if roll:
                for k in range(4):
                    add(hat(), t + n * b / 4 + k * b / 8, .3, pan=.35)
                n += 2
                continue
            add(hat(), t + n * b / 4, .38 if n % 2 == 0 else .22, pan=.35)
            n += 1
        add(b808(r - 12, min(b * 3.6, t1 - t)), t, .8, bus=MUS)
        add(pad([r + 12, r + 15, r + 19], min(b * 4, t1 - t), 1200), t, .18, bus=MUS)
        bar += 1
        t += b * 4


def style_lofi(t0, t1, e):
    bpm = e.get('bpm', 84)
    b = 60 / bpm
    chords = [(48, [64, 67, 71, 74]), (45, [60, 64, 67, 71]), (50, [65, 69, 72, 76]), (43, [65, 69, 71, 74])]
    bar = 0
    t = t0
    while t < t1 - .01:
        r, ch = chords[bar % 4]
        d = min(b * 4, t1 - t)
        add(rhodes(ch, d + .3), t, .32, bus=MUS)
        add(np.sin(2 * np.pi * hz(r - 12) * tt(d)) * np.minimum(1, (d - tt(d)) / .05) * .5, t, .45, bus=MUS)
        for kt in (0, b * 2.5):
            if t + kt < t1:
                kick_at(t + kt, .6, .8)
        for st in (b, b * 3):
            if t + st < t1:
                add(filt(snare(4000), 'lowpass', 3500), t + st, .4)
        for h in range(8):
            if t + h * b / 2 < t1:
                add(hat(), t + h * b / 2 + (.02 if h % 2 else 0), .18, pan=.3)
        bar += 1
        t += b * 4
    d = t1 - t0
    crackle = (rng.random(int(d * SR)) > .9993) * rng.standard_normal(int(d * SR)) * .6 + filt(noise(d), 'bandpass', [800, 3000]) * .015
    add(crackle, t0, .5)


def style_edm(t0, t1, e):
    bpm = e.get('bpm', 128)
    b = 60 / bpm
    CH = [(42, [66, 69, 73]), (38, [62, 66, 69]), (45, [64, 69, 73]), (40, [64, 68, 71])]
    bar = 0
    t = t0
    while t < t1 - .01:
        r, ch = CH[bar % 4]
        d = min(b * 4, t1 - t)
        add(pad([n - 12 for n in ch] + ch, d, 2600), t, .45, bus=MUS)
        for s in range(8):
            if t + s * b / 2 < t1:
                add(np.sin(2 * np.pi * hz(r - 12 if s % 2 == 0 else r) * tt(b / 2 * .95)) * .5, t + s * b / 2, .5, bus=MUS)
        arp_ = ch + [ch[0] + 12]
        for s in range(16):
            if t + s * b / 4 < t1:
                add(pluck(arp_[[0, 1, 2, 3, 2, 1, 2, 3][s % 8]] + 12), t + s * b / 4, .1, pan=.4 if s % 2 else -.4)
        for beat in range(4):
            tb = t + beat * b
            if tb < t1:
                kick_at(tb, .9)
                if beat % 2:
                    add(clap(), tb, .6)
                add(hat(True), tb + b / 2, .3)
        bar += 1
        t += b * 4


def style_tension(t0, t1, e):
    d = t1 - t0
    t = tt(d)
    drone = (saw(hz(30), t) * .5 + np.sin(2 * np.pi * hz(42) * t) * .5) * np.minimum(1, t / .3) * np.minimum(1, (d - t) / .2)
    add(filt(drone, 'lowpass', 400), t0, .5, bus=MUS)
    bpm = e.get('bpm', 120)
    k = t0
    i = 0
    while k < t1:
        add(fx_tick(1) * (1.2 if i % 2 == 0 else .7), k, .6)
        if i % 4 == 0:
            add(fx_heart(1), k, .7)
        k += 60 / bpm / 2
        i += 1


def style_ambient(t0, t1, e):
    d = t1 - t0
    chords = [[60, 64, 67, 71, 74], [57, 60, 64, 67, 71]]
    seg = d / 2
    for i, ch in enumerate(chords):
        add(pad(ch, seg + .5, 1400), t0 + i * seg, .3, bus=MUS)
    add(filt(noise(d), 'lowpass', 600) * .03, t0, 1)


STYLES = {'phonk': style_phonk, 'trap': style_trap, 'lofi': style_lofi, 'edm': style_edm, 'tension': style_tension, 'ambient': style_ambient}

for e in EVENTS:
    if e['kind'] == 'music':
        STYLES[e['style']](e['t'], min(e['end'], DUR), e)
for e in EVENTS:
    k = e['kind']
    if k == 'music':
        continue
    if k in ('riser', 'laser', 'vacuum') and 'd' in e:
        s = FX[k](e['v'], e['d'])
    else:
        s = FX[k](e['v'])
    pan = (rng.random() - .5) * .4 if k in ('key', 'pop', 'tick', 'crunch', 'typing') else 0
    off = -.5 if k == 'whoosh' else (-e.get('d', 1.5) if k == 'riser' else 0)
    add(s, e['t'] + off, .95 * e['v'], pan)

# sidechain da música pelo bumbo
env = np.ones(N)
for k in KICKS:
    i, d = int(k * SR), int(.2 * SR)
    seg = 1 - .65 * (1 - np.linspace(0, 1, d)) ** 2
    env[i:i + d] = np.minimum(env[i:i + d], seg[: max(0, min(d, N - i))])
L += MUS * env
R += MUS * env

mix = filt(np.stack([L, R]), 'highpass', 25)
fn = int(.4 * SR)
mix[:, -fn:] *= np.linspace(1, 0, fn)
mix = np.tanh(mix / (np.max(np.abs(mix)) + 1e-9) * 1.5) / np.tanh(1.5) * .89
wavfile.write(sys.argv[2], SR, (mix.T * 32767).astype(np.int16))
print('ok', DUR, len(EVENTS), 'eventos')
