"""Elenco propio animado (procedural, Pillow): rebote, parpadeo, baile y boca sincronizada con el audio.

Prototipo: 4 personajes originales. Reemplázalos por arte hecho por una persona cuando lo tengas;
la interfaz (CAST / draw_character / mouth_envelope) puede quedarse igual.
"""
import math
import subprocess
from array import array

from PIL import Image, ImageDraw

SS = 2  # supersampling para bordes suaves
CHEEK = (251, 113, 133)
INK = (30, 27, 75)

# Cada personaje tiene su forma, colores y voz. "desc" se le pasa a Claude para que elija quién canta.
CAST = {
    "pipo": {"desc": "Pipo, bolita turquesa curiosa con orejas redondas y una antena con estrella",
             "body": (45, 212, 191), "dark": (13, 148, 136), "belly": (204, 251, 241),
             "ears": "round", "top": "antenna", "voice": "es-MX-DaliaNeural", "pitch": "+15Hz"},
    "lula": {"desc": "Lula, conejita rosa cariñosa de orejas largas con un moño amarillo",
             "body": (244, 114, 182), "dark": (219, 39, 119), "belly": (252, 231, 243),
             "ears": "bunny", "top": "bow", "voice": "es-US-PalomaNeural", "pitch": "+25Hz"},
    "tito": {"desc": "Tito, gatito naranja aventurero de orejas puntiagudas con gorra azul",
             "body": (251, 146, 60), "dark": (234, 88, 12), "belly": (255, 237, 213),
             "ears": "cat", "top": "cap", "voice": "es-MX-JorgeNeural", "pitch": "+20Hz"},
    "nubi": {"desc": "Nubi, nubecita lila soñadora y tranquila con una hojita en la cabeza",
             "body": (167, 139, 250), "dark": (124, 58, 237), "belly": (237, 233, 254),
             "ears": "none", "top": "sprout", "voice": "es-CO-SalomeNeural", "pitch": "+20Hz"},
}


def mouth_envelope(audio_path, fps, dry=False):
    """Apertura de boca 0..1 por frame, a partir del volumen (RMS) del audio."""
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", audio_path, "-f", "s16le", "-ac", "1", "-ar", "8000", "-"],
        check=True, capture_output=True,
    ).stdout
    pcm = array("h")
    pcm.frombytes(raw[: len(raw) // 2 * 2])
    win = 8000 // fps
    rms = []
    for i in range(0, len(pcm), win):
        chunk = pcm[i : i + win]
        rms.append(math.sqrt(sum(s * s for s in chunk) / max(1, len(chunk))))
    peak = sorted(rms)[int(len(rms) * 0.95)] if rms else 0
    if dry or peak < 50:  # audio en silencio (DRY_RUN): boca de mentira para ver la animación
        return [0.5 + 0.5 * math.sin(i * 0.9) * math.sin(i * 0.23) for i in range(len(rms))]
    env, cur = [], 0.0
    for r in rms:
        target = min(1.0, r / peak)
        cur += (target - cur) * (0.65 if target > cur else 0.35)  # ataque rápido, caída suave
        env.append(cur)
    return env


def draw_character(t, mouth, size=560, bpm=168, look="pipo", dance=False):
    """RGBA de `size`x`size` con el personaje `look` en el instante t (s) y apertura de boca 0..1.
    Rebota una vez por tiempo de `bpm`. Con dance=True (coros) sube los dos brazos alternando."""
    c = CAST[look]
    BODY, DARK, BELLY = c["body"], c["dark"], c["belly"]
    S = size * SS
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    phase = math.pi * bpm / 60 * t
    beat = abs(math.sin(phase))                  # un rebote por tiempo
    squash = 1 - 0.06 * (1 - beat)               # se aplasta al tocar el suelo
    lift = beat * 0.07 * S
    cx = S / 2
    bh = S * 0.50 * squash
    bw = S * 0.29 * (2 - squash)
    bottom = S * 0.93 - lift - S * 0.08
    top = bottom - bh * 1.15
    sway = math.sin(2 * math.pi * 0.7 * t) * S * 0.01 + (math.sin(phase) * S * 0.025 if dance else 0)

    # sombra
    sh = 0.8 + 0.2 * (1 - beat)
    d.ellipse((cx - S * 0.28 * sh, S * 0.93, cx + S * 0.28 * sh, S * 0.99), fill=(0, 0, 0, 55))
    # pies
    for dx in (-0.16, 0.16):
        d.ellipse((cx + S * dx - S * 0.09, bottom - S * 0.04, cx + S * dx + S * 0.09, bottom + S * 0.05), fill=DARK)
    # orejas
    for side in (-1, 1):
        ex, ey = cx + S * 0.2 * side + sway, top + S * 0.02
        if c["ears"] == "round":
            d.ellipse((ex - S * 0.09, ey - S * 0.12, ex + S * 0.09, ey + S * 0.07), fill=DARK)
            d.ellipse((ex - S * 0.05, ey - S * 0.08, ex + S * 0.05, ey + S * 0.04), fill=(253, 164, 175))
        elif c["ears"] == "bunny":
            flop = math.sin(phase) * S * 0.015 * side
            ex = cx + S * 0.11 * side + sway
            d.ellipse((ex - S * 0.06 + flop, ey - S * 0.24, ex + S * 0.06 + flop, ey + S * 0.06), fill=BODY)
            d.ellipse((ex - S * 0.03 + flop, ey - S * 0.20, ex + S * 0.03 + flop, ey + S * 0.02), fill=(253, 164, 175))
        elif c["ears"] == "cat":
            ex = cx + S * 0.17 * side + sway
            d.polygon([(ex - S * 0.09, ey + S * 0.07), (ex + S * 0.09, ey + S * 0.07), (ex + S * 0.03 * side, ey - S * 0.14)], fill=DARK)
            d.polygon([(ex - S * 0.045, ey + S * 0.05), (ex + S * 0.045, ey + S * 0.05), (ex + S * 0.02 * side, ey - S * 0.07)], fill=(253, 164, 175))
    # accesorio de antena (detrás del cuerpo)
    if c["top"] == "antenna":
        ax, ay = cx + sway * 1.5, top - S * 0.01
        tip = (ax + math.sin(2 * math.pi * 1.1 * t) * S * 0.03, top - S * 0.12)
        d.line((ax, ay, *tip), fill=DARK, width=int(S * 0.012))
        d.ellipse((tip[0] - S * 0.032, tip[1] - S * 0.032, tip[0] + S * 0.032, tip[1] + S * 0.032), fill=(253, 224, 71))
    elif c["top"] == "sprout":
        ax, ay = cx + sway, top + S * 0.01
        tilt = math.sin(2 * math.pi * 0.9 * t) * S * 0.02
        d.line((ax, ay, ax + tilt, ay - S * 0.08), fill=(22, 163, 74), width=int(S * 0.014))
        d.ellipse((ax + tilt - S * 0.07, ay - S * 0.12, ax + tilt, ay - S * 0.07), fill=(74, 222, 128))
        d.ellipse((ax + tilt, ay - S * 0.13, ax + tilt + S * 0.08, ay - S * 0.075), fill=(74, 222, 128))
    # cuerpo + barriga
    if c["ears"] == "none":  # nube: tres bultitos arriba
        for dx, r in ((-0.15, 0.12), (0.0, 0.15), (0.15, 0.12)):
            x = cx + S * dx + sway
            d.ellipse((x - S * r, top - S * 0.02, x + S * r, top + S * r * 2 - S * 0.02), fill=BODY)
    d.ellipse((cx - bw + sway, top, cx + bw + sway, bottom), fill=BODY)
    d.ellipse((cx - bw * 0.62 + sway, top + bh * 0.55, cx + bw * 0.62 + sway, bottom - S * 0.02), fill=BELLY)
    if c["top"] == "bow":
        bx, by = cx + S * 0.13 + sway, top + S * 0.05
        d.polygon([(bx, by), (bx - S * 0.08, by - S * 0.05), (bx - S * 0.08, by + S * 0.05)], fill=(250, 204, 21))
        d.polygon([(bx, by), (bx + S * 0.08, by - S * 0.05), (bx + S * 0.08, by + S * 0.05)], fill=(250, 204, 21))
        d.ellipse((bx - S * 0.025, by - S * 0.025, bx + S * 0.025, by + S * 0.025), fill=(234, 179, 8))
    elif c["top"] == "cap":
        d.chord((cx - bw * 0.78 + sway, top - S * 0.02, cx + bw * 0.78 + sway, top + bh * 0.42), 180, 360, fill=(37, 99, 235))
        d.ellipse((cx + sway, top + bh * 0.15, cx + bw * 1.05 + sway, top + bh * 0.27), fill=(29, 78, 216))
    # brazos: saludo (verso) o los dos arriba alternando (coro)
    sw = math.sin(phase)
    for side in (1, -1):
        sx, sy = cx + bw * 0.92 * side + sway, top + bh * 0.62
        if dance:
            ang = -math.pi / 2 + side * 0.6 + 0.35 * sw
            hx, hy = sx + math.cos(ang) * S * 0.20, sy + math.sin(ang) * S * 0.20
        elif side == 1:
            ang = -1.0 + 0.35 * sw
            hx, hy = sx + math.cos(ang) * S * 0.20, sy + math.sin(ang) * S * 0.20
        else:
            hx, hy = sx - S * 0.10, sy + S * 0.15
        d.line((sx, sy, hx, hy), fill=DARK, width=int(S * 0.055))
        d.ellipse((hx - S * 0.04, hy - S * 0.04, hx + S * 0.04, hy + S * 0.04), fill=DARK)

    # ojos (parpadeo cada ~3.2 s)
    blink = (t % 3.2) < 0.14
    ey = top + bh * 0.36
    for dx in (-0.12, 0.12):
        ex = cx + S * dx + sway
        if blink:
            d.arc((ex - S * 0.05, ey - S * 0.02, ex + S * 0.05, ey + S * 0.05), 200, 340, fill=INK, width=int(S * 0.012))
        else:
            d.ellipse((ex - S * 0.06, ey - S * 0.07, ex + S * 0.06, ey + S * 0.07), fill=(255, 255, 255))
            d.ellipse((ex - S * 0.035, ey - S * 0.04, ex + S * 0.035, ey + S * 0.05), fill=INK)
            d.ellipse((ex - S * 0.015, ey - S * 0.035, ex + S * 0.005, ey - S * 0.015), fill=(255, 255, 255))
    # cachetes
    for dx in (-0.2, 0.2):
        ex = cx + S * dx + sway
        d.ellipse((ex - S * 0.04, ey + S * 0.07, ex + S * 0.04, ey + S * 0.115), fill=CHEEK + (170,))
    # boca
    mx, my = cx + sway, ey + S * 0.115
    mw = S * (0.055 + 0.03 * mouth)
    mh = S * (0.008 + 0.075 * mouth)
    if mouth < 0.08:
        d.arc((mx - mw, my - S * 0.03, mx + mw, my + S * 0.03), 20, 160, fill=INK, width=int(S * 0.012))
    else:
        d.ellipse((mx - mw, my - mh * 0.4, mx + mw, my + mh), fill=INK)
        if mouth > 0.35:
            d.ellipse((mx - mw * 0.6, my + mh * 0.35, mx + mw * 0.6, my + mh * 0.95), fill=(251, 113, 133))

    return img.resize((size, size), Image.LANCZOS)
