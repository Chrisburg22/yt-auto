"""Canciones infantiles: letra (Claude) + pista instrumental sintetizada + voz TTS acomodada al compás.

Todo es gratis y original: la música se genera con numpy (sin samples ni melodías ajenas)
y la voz es edge-tts "rítmica" (dice la letra a tiempo; no canta afinado).
Para voz cantada de verdad, cambia `_vocal_line` por un proveedor de música con licencia comercial.
"""
import os
import random
import subprocess

import numpy as np

from .character import CAST
from .scenery import SCENES
from .script_gen import _clean_meta
from .tts import synth

SR = 44100

SONG_SHAPE = """{
  "topic": "tema en pocas palabras",
  "title": "máx 90 caracteres, ej: ¡Los Pulpos Tienen Tres Corazones! | Canción Infantil",
  "description": "2-3 párrafos + 3-5 hashtags al final",
  "tags": ["8 a 15 tags"],
  "thumbnail_text": "máx 4 palabras",
  "character": "clave del personaje que canta",
  "scene": "clave del escenario",
  "mood": "clave del estilo musical",
  "chorus": ["4 versos"],
  "verses": [["4 versos"], ["4 versos"]]
}"""

# Estilos musicales: Claude elige el que va con la letra; cada uno cambia ritmo, acordes e instrumento.
MOODS = {
    "alegre": "pop alegre con ukulele, para cantar y aplaudir",
    "bailable": "ritmo tropical con marimba, para bailar",
    "marcha": "marcha con metales, para marchar y moverse",
    "tranquila": "suave con piano, para calmarse o antes de dormir",
}


def _options(d):
    return "\n".join(f"  - {k}: {v}" for k, v in d.items())


def song_prompt(cfg, history, style=None):
    ch = cfg["channel"]
    used = "\n".join(f"- {h['topic']} ({h.get('song', {}).get('character', '?')}, {h.get('song', {}).get('mood', '?')})"
                     for h in history[-60:]) or "- (ninguno)"
    recent = [h.get("song", {}).get("character") for h in history[-3:]]
    style_line = f"\nTipo de canción de hoy: {style['name']} — {style['desc']}\n" if style else ""
    return f"""Canal: {ch['name']}
Nicho: {ch['niche']}
Audiencia: {ch['audience']}
Idioma: {ch['language']}

Temas ya publicados (NO repitas; entre paréntesis quién cantó y el estilo):
{used}
{style_line}
Escribe la letra ORIGINAL de una canción infantil educativa corta.

Elige quién la canta ("character"), el más adecuado al tema. Evita repetir a quien cantó en los últimos días ({", ".join(filter(None, recent)) or "nadie"}):
{_options({k: v["desc"] for k, v in CAST.items()})}

Elige el escenario ("scene") que mejor acompañe la letra:
{_options(SCENES)}

Elige el estilo musical ("mood") que vaya con la letra, variando respecto a los últimos días:
{_options(MOODS)}

Reglas:
- UN tema nuevo y concreto del nicho; la canción enseña 2 o 3 datos verdaderos sobre él.
- Coro de 4 versos, muy pegajoso y repetitivo, con alguna onomatopeya o palabra divertida.
- 2 estrofas de 4 versos; cada estrofa enseña algo distinto.
- Cada verso de 4 a 8 palabras, que rime (AABB o ABCB) y se pueda decir en unos 3 segundos.
- Palabras que entienda un niño de 5 a 7 años. Nada de miedo, peligro, burlas ni productos.
- No copies ni parodies canciones existentes. No menciones marcas ni personajes ajenos al canal.
- Sin emojis, sin markdown, sin acotaciones.

Devuelve SOLO este JSON:
{SONG_SHAPE}"""


def validate_song(s):
    for k in ("topic", "title", "description", "tags", "thumbnail_text", "chorus", "verses"):
        if k not in s:
            raise ValueError(f"Falta campo '{k}'")
    s["chorus"] = [l.strip() for l in s["chorus"] if str(l).strip()]
    s["verses"] = [[l.strip() for l in v if str(l).strip()] for v in s["verses"]]
    s["verses"] = [v for v in s["verses"] if v]
    if len(s["chorus"]) < 2 or len(s["verses"]) < 1:
        raise ValueError("Letra incompleta")
    # si Claude inventa una clave, caer en una válida en vez de fallar
    s["character"] = s.get("character") if s.get("character") in CAST else "pipo"
    s["scene"] = s.get("scene") if s.get("scene") in SCENES else "cielo"
    s["mood"] = s.get("mood") if s.get("mood") in MOODS else "alegre"
    return _clean_meta(s)


def fake_song():
    return validate_song({
        "topic": "Prueba de canción",
        "title": "Canción de prueba",
        "description": "Descripción de prueba.\n\n#prueba",
        "tags": ["prueba", "canción"],
        "thumbnail_text": "CANCIÓN DE PRUEBA",
        "character": os.getenv("SONG_CHARACTER", "lula"),
        "scene": os.getenv("SONG_SCENE", "mar"),
        "mood": os.getenv("SONG_MOOD", "bailable"),
        "chorus": ["Tres corazones, tres corazones", "tiene el pulpo, ¡qué emociones!",
                   "Bum, bum, bum, late sin parar", "el pulpito en el mar."],
        "verses": [["Vive en el fondo del océano", "y se esconde como un hermano",
                    "cambia de color en un segundo", "es el más listo de este mundo."],
                   ["Tiene ocho brazos para nadar", "con ventosas para agarrar",
                    "su tinta negra es su escudo", "y se escapa muy agudo."]],
    })


def sections(song):
    """Estructura: coro, estrofa 1, coro, estrofa 2, coro (más estrofas si las hay)."""
    out = [("Coro", song["chorus"])]
    for i, v in enumerate(song["verses"]):
        out += [(f"Estrofa {i + 1}", v), ("Coro", song["chorus"])]
    return out


# ---------------- pista instrumental ----------------
def _midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def _env(n, decay):
    return np.exp(-np.arange(n) / (decay * SR))


def _tone(freq, dur, decay, harmonics=(1.0,)):
    n = int(dur * SR)
    t = np.arange(n) / SR
    w = sum(a * np.sin(2 * np.pi * freq * (k + 1) * t) for k, a in enumerate(harmonics))
    return w * _env(n, decay)


def _add(buf, sig, at, gain=1.0):
    i = int(at * SR)
    if i >= len(buf):
        return
    sig = sig[: len(buf) - i]
    buf[i : i + len(sig)] += sig * gain


# Grados en Do mayor: (bajo, acorde). Se transportan con `key`.
CHORDS = {"I": (48, [60, 64, 67]), "ii": (50, [62, 65, 69]), "IV": (41, [60, 65, 69]),
          "V": (43, [59, 62, 67]), "vi": (45, [60, 64, 69])}

# Patrones en tiempos (0-3.x). harm = timbre (armónicos), decay = cuánto suena cada nota.
STYLES = {
    "alegre": {"bpm": (118, 128), "progs": [["I", "V", "vi", "IV"], ["I", "IV", "V", "IV"]],
               "kick": [0, 2], "snare": [1, 3], "hats": [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5],
               "chord_hits": [1, 3], "chord_harm": (1.0, 0.5, 0.25, 0.1), "chord_decay": 0.18, "strum": 0.012,
               "bass": [0, 1, 2, 3], "lead_harm": (1.0, 0.0, 0.25, 0.0, 0.1), "lead_decay": 0.3},
    "bailable": {"bpm": (98, 108), "progs": [["vi", "IV", "I", "V"], ["I", "vi", "ii", "V"]],
                 "kick": [0, 1, 2, 3], "snare": [0.75, 1.5, 2.75, 3.5], "hats": [0.5, 1.5, 2.5, 3.5],
                 "chord_hits": [0, 0.75, 1.5, 2, 2.75, 3.5], "chord_harm": (1.0, 0.0, 0.0, 0.35), "chord_decay": 0.12,
                 "strum": 0.0, "bass": [0, 0.75, 2, 2.75], "lead_harm": (1.0, 0.0, 0.0, 0.4), "lead_decay": 0.15},
    "marcha": {"bpm": (106, 116), "progs": [["I", "IV", "V", "I"], ["I", "V", "I", "V"]],
               "kick": [0, 1, 2, 3], "snare": [1, 3, 3.5, 3.75], "hats": [],
               "chord_hits": [0, 2], "chord_harm": (1.0, 0.8, 0.6, 0.45, 0.3), "chord_decay": 0.35, "strum": 0.0,
               "bass": [0, 1, 2, 3], "lead_harm": (1.0, 0.7, 0.5, 0.3), "lead_decay": 0.25},
    "tranquila": {"bpm": (82, 92), "progs": [["I", "vi", "IV", "V"], ["I", "IV", "I", "V"]],
                  "kick": [], "snare": [], "hats": [1, 3],
                  "chord_hits": [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5], "arpeggio": True, "chord_harm": (1.0, 0.4, 0.2),
                  "chord_decay": 0.8, "strum": 0.0, "bass": [0], "lead_harm": (1.0, 0.0, 0.3, 0.0, 0.15), "lead_decay": 0.6},
}


def pick_style(mood, seed):
    """Elige bpm, tonalidad y progresión dentro del estilo (determinista por canción)."""
    rng = random.Random(f"style-{seed}")
    st = STYLES.get(mood, STYLES["alegre"])
    return {"mood": mood, "bpm": rng.randint(*st["bpm"]), "key": rng.choice([-3, -2, 0, 2, 3, 5]),
            "prog": rng.choice(st["progs"])}


def backing_track(bars, bpm, seed, melody_bars=(), mood="alegre", key=0, prog=("I", "V", "vi", "IV")):
    """Pista instrumental original: batería, bajo, acordes y un motivo de melodía propio de cada canción."""
    st = STYLES.get(mood, STYLES["alegre"])
    rng = random.Random(seed)
    beat = 60 / bpm
    buf = np.zeros(int((bars * 4 * beat + 2) * SR))
    pent = [72, 74, 76, 79, 81, 84]  # pentatónica: siempre suena bien sobre estos acordes
    motif = [rng.choice(pent) for _ in range(8)]  # motivo propio por canción, se repite

    noise = np.random.default_rng(rng.randrange(2**32)).standard_normal(int(0.3 * SR))
    kick_t = np.arange(int(0.25 * SR)) / SR
    kick = np.sin(2 * np.pi * (50 * kick_t + 35 * (1 - np.exp(-kick_t * 30)))) * _env(len(kick_t), 0.09)
    clap = np.diff(noise[: int(0.15 * SR)], prepend=0) * _env(int(0.15 * SR), 0.035)
    hat = np.diff(noise[: int(0.05 * SR)], prepend=0) * _env(int(0.05 * SR), 0.012)
    soft = 0.5 if mood == "tranquila" else 1.0

    for b in range(bars):
        root, chord = CHORDS[prog[b % len(prog)]]
        root, chord = root + key, [n + key for n in chord]
        t0 = b * 4 * beat
        for k in st["kick"]:
            _add(buf, kick, t0 + k * beat, 0.9 if k in (0, 2) else 0.6)
        for k in st["snare"]:
            _add(buf, clap, t0 + k * beat, 0.35 if k in (1, 3) else 0.22)
        for k in st["hats"]:
            _add(buf, hat, t0 + k * beat, 0.1 * soft)
        for j, k in enumerate(st["bass"]):
            note = root if (mood != "marcha" or j % 2 == 0) else root + 7  # marcha: bajo "um-pa"
            _add(buf, _tone(_midi(note), beat * 0.9, 0.25 if mood != "tranquila" else 1.2, (1.0, 0.35, 0.1)), t0 + k * beat, 0.32 * soft)
        for j, k in enumerate(st["chord_hits"]):
            notes = [chord[j % len(chord)]] if st.get("arpeggio") else chord
            for m, n in enumerate(notes):
                _add(buf, _tone(_midi(n), beat * 1.5, st["chord_decay"], st["chord_harm"]),
                     t0 + k * beat + m * st["strum"], (0.16 if st.get("arpeggio") else 0.09))
        if b in melody_bars:
            for k, n in enumerate(motif):
                _add(buf, _tone(_midi(n + key), beat, st["lead_decay"], st["lead_harm"]), t0 + k * beat / 2, 0.16)
    return buf


# ---------------- voz ----------------
def _load(path, tempo=1.0):
    af = []
    t = tempo
    while t > 2.0:
        af.append("atempo=2.0"); t /= 2.0
    af.append(f"atempo={t:.4f}")
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", path, "-af", ",".join(af), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"],
        check=True, capture_output=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def _trim_silence(x, thr=0.02):
    idx = np.where(np.abs(x) > thr)[0]
    return x[idx[0] : idx[-1] + 1] if len(idx) else x


def _vocal_line(text, singers, workdir, i, rate, dry):
    """Voz de un verso. `singers` = [(voz, pitch)]; en el coro canta un amigo junto al protagonista."""
    parts = []
    for j, (v, pitch) in enumerate(singers):
        p = os.path.join(workdir, f"v{i:03d}_{j}.mp3")
        synth(text, v, p, rate=rate, dry=dry, pitch=pitch)
        parts.append(p)
    return parts


def build_song(song, workdir, cfg, dry=False):
    """Devuelve (mix_wav, vocals_wav, timeline, bpm, dur). timeline = [{start,end,section,part,text}]."""
    os.makedirs(workdir, exist_ok=True)
    scfg = cfg.get("song", {})
    style = pick_style(song.get("mood", "alegre"), song["topic"])
    bpm = scfg.get("bpm") or style["bpm"]
    beat = 60 / bpm
    slot = 2 * 4 * beat          # cada verso dura 2 compases
    rate = scfg.get("rate", "+0%")
    lead = song.get("character", "pipo")
    friend = random.Random(song["topic"]).choice([k for k in CAST if k != lead])
    solo = [(CAST[lead]["voice"], CAST[lead]["pitch"])]
    group = solo + [(CAST[friend]["voice"], CAST[friend]["pitch"])]
    intro_bars = 2

    lines = [(name, l, k) for k, (name, ls) in enumerate(sections(song)) for l in ls]
    vocals_clips, timeline = [], []
    bar = intro_bars
    for i, (name, text, part) in enumerate(lines):
        paths = _vocal_line(text, group if name == "Coro" else solo, workdir, i, rate, dry)
        raw_len = max(len(_trim_silence(_load(p))) for p in paths) / SR
        # cabe en 2 compases (acelerando hasta 1.25x); si no, usa 4 compases
        tempo = min(1.25, max(1.0, raw_len / (slot * 0.92)))
        nbars = 2 if raw_len / tempo <= slot * 0.95 else 4
        clips = [_trim_silence(_load(p, tempo)) for p in paths]
        n = max(len(c) for c in clips)
        clip = np.zeros(n)
        for c in clips:
            clip[: len(c)] += c / len(clips) ** 0.5
        start = bar * 4 * beat + beat * 0.1  # entra justo después del primer tiempo
        vocals_clips.append((start, clip))
        timeline.append({"start": bar * 4 * beat, "end": (bar + nbars) * 4 * beat, "section": name, "part": part, "text": text})
        bar += nbars
    bars = bar + 2  # outro
    dur = bars * 4 * beat

    seed = song["topic"]
    music = backing_track(bars, bpm, seed, melody_bars=set(range(intro_bars)) | {bars - 2, bars - 1},
                          mood=style["mood"], key=style["key"], prog=style["prog"])
    vocals = np.zeros_like(music)
    for start, clip in vocals_clips:
        _add(vocals, clip, start)

    def write(path, x):
        x = x[: int(dur * SR)]
        x = np.clip(x / max(1e-9, np.abs(x).max()) * 0.9, -1, 1)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "f64le", "-ar", str(SR), "-ac", "1", "-i", "-",
                        "-af", f"afade=t=out:st={dur - 2:.2f}:d=2", path],
                       input=x.astype("<f8").tobytes(), check=True)

    mix_wav, voc_wav = os.path.join(workdir, "song.wav"), os.path.join(workdir, "vocals.wav")
    voc_peak = max(1e-9, np.abs(vocals).max())
    write(mix_wav, music / max(1e-9, np.abs(music).max()) * 0.45 + vocals / voc_peak)
    write(voc_wav, vocals)
    print(f"[song] {lead} (+{friend} en coros) | {style['mood']} {bpm} bpm, tono {style['key']:+d}, "
          f"{'-'.join(style['prog'])} | {len(lines)} versos → {dur:.1f}s")
    return mix_wav, voc_wav, timeline, bpm, dur
