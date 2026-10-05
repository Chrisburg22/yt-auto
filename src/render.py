"""Render: cada oración = 1 frame (titular + subtítulo) + su audio. Se concatenan con ffmpeg."""
import os
import subprocess
from PIL import Image, ImageDraw, ImageFont

from functools import lru_cache

from . import character, scenery
from .tts import split_sentences, synth

FONT_BOLD = os.getenv("FONT_BOLD", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
FONT_REG = os.getenv("FONT_REG", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
FPS = 30
SIZES = {"long": (1920, 1080), "short": (1080, 1920)}


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def _gradient(size, c1, c2):
    base = Image.new("RGB", size, _rgb(c1))
    top = Image.new("RGB", size, _rgb(c2))
    # gradiente diagonal: promedio de gradiente vertical y horizontal
    v = Image.linear_gradient("L").resize(size)
    hgrad = Image.linear_gradient("L").rotate(90).resize(size)
    mask = Image.blend(v, hgrad, 0.5)
    base.paste(top, (0, 0), mask)
    return base


def _wrap(draw, text, font, max_w):
    lines, cur = [], ""
    for w in text.split():
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _fit(draw, text, path, max_w, max_h, start, min_size, spacing=1.18):
    size = start
    while size >= min_size:
        font = ImageFont.truetype(path, size)
        lines = _wrap(draw, text, font, max_w)
        fits_w = all(draw.textlength(l, font=font) <= max_w for l in lines)  # una palabra larga no se parte
        if fits_w and len(lines) * size * spacing <= max_h:
            return font, lines, int(size * spacing)
        size -= 4
    font = ImageFont.truetype(path, min_size)
    return font, _wrap(draw, text, font, max_w), int(min_size * spacing)


@lru_cache(maxsize=4)
def _scene(theme, W, H, seed):
    return scenery.draw_scene(theme, W, H, seed).convert("RGBA")


def draw_frame(out, kind, headline, caption, palette, progress, channel, animate=False, scene=None, scene_seed=0):
    W, H = SIZES[kind]
    vertical = kind == "short"
    # con personaje: long reserva columna derecha; short reserva banda inferior
    right = int(W * 0.30) if animate and not vertical else 0
    bg1, bg2, accent = palette
    img = _scene(scene, W, H, scene_seed).copy() if scene else _gradient((W, H), bg1, bg2).convert("RGBA")
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    acc = _rgb(accent)

    if not scene:  # decoración del fondo liso
        r = int(min(W, H) * 0.45)
        d.ellipse((W - r * 1.2, -r * 0.6, W + r * 0.8, r * 1.4), fill=acc + (28,))
        d.ellipse((-r * 0.7, H - r * 0.9, r * 0.9, H + r * 0.7), fill=(255, 255, 255, 14))

    m = int(W * 0.08)
    # titular
    h_top, h_max = (int(H * 0.10), int(H * 0.20)) if vertical and animate else \
        (int(H * 0.16), int(H * 0.30)) if vertical else (int(H * 0.14), int(H * 0.36))
    hf, hl, hstep = _fit(d, headline.upper(), FONT_BOLD, W - 2 * m - right, h_max,
                         start=120 if vertical else 110, min_size=48)
    if scene:  # fondo con dibujos: caja oscura para que el titular se lea
        tw = max(d.textlength(line, font=hf) for line in hl)
        d.rounded_rectangle((m - 36, h_top - 56, m + tw + 36, h_top + len(hl) * hstep + 12), radius=28, fill=(0, 0, 0, 120))
    d.rectangle((m, h_top - 28, m + int(W * 0.12), h_top - 16), fill=acc + (255,))
    y = h_top
    for line in hl:
        d.text((m, y), line, font=hf, fill=(255, 255, 255, 255))
        y += hstep

    # subtítulo en caja
    box_top = int(H * 0.34) if vertical and animate else int(H * 0.52) if vertical else int(H * 0.60)
    box_h = int(H * 0.26) if vertical and animate else int(H * 0.36) if vertical else int(H * 0.28)
    pad = int(W * 0.04)
    cf, cl, cstep = _fit(d, caption, FONT_REG, W - 2 * m - 2 * pad - right, box_h - 2 * pad,
                         start=64 if vertical else 52, min_size=30)
    text_h = len(cl) * cstep
    real_h = text_h + 2 * pad
    d.rounded_rectangle((m, box_top, W - m - right, box_top + real_h), radius=28, fill=(0, 0, 0, 150))
    y = box_top + pad
    for line in cl:
        d.text((m + pad, y), line, font=cf, fill=(255, 255, 255, 255))
        y += cstep

    # barra de progreso + nombre de canal
    bar_y = H - (int(H * 0.06) if vertical else int(H * 0.05))
    d.rounded_rectangle((m, bar_y, W - m, bar_y + 10), radius=5, fill=(255, 255, 255, 50))
    d.rounded_rectangle((m, bar_y, m + max(10, int((W - 2 * m) * progress)), bar_y + 10), radius=5, fill=acc + (255,))
    small = ImageFont.truetype(FONT_BOLD, 30 if vertical else 28)
    d.text((m, bar_y - 48), channel, font=small, fill=(255, 255, 255, 170))

    Image.alpha_composite(img, layer).convert("RGB").save(out, "PNG")


def draw_thumbnail(out, text, palette, channel, look=None, scene=None, seed=0):
    W, H = 1280, 720
    bg1, bg2, accent = palette
    img = scenery.draw_scene(scene, W, H, seed) if scene else _gradient((W, H), bg1, bg2)
    right = 0
    if look:  # el personaje grande a la derecha: las miniaturas con cara funcionan mejor
        size = int(H * 0.85)
        sprite = character.draw_character(0.5, 0.7, size, 120, look, dance=True)
        img.paste(sprite, (W - size + int(size * 0.06), H - size), sprite)
        right = int(W * 0.42)
    d = ImageDraw.Draw(img, "RGBA")
    m = 70
    d.rectangle((0, 0, 24, H), fill=_rgb(accent))
    f, lines, step = _fit(d, text.upper(), FONT_BOLD, W - 2 * m - right, H - 220, start=150, min_size=60, spacing=1.05)
    y = (H - len(lines) * step) // 2 - 20
    if scene:
        tw = max(d.textlength(line, font=f) for line in lines)
        d.rounded_rectangle((m - 30, y - 30, m + tw + 30, y + len(lines) * step + 20), radius=30, fill=(0, 0, 0, 130))
    for line in lines:
        d.text((m + 4, y + 4), line, font=f, fill=(0, 0, 0))
        d.text((m, y), line, font=f, fill=_rgb(accent) if line == lines[-1] else (255, 255, 255))
        y += step
    d.text((m, H - 80), channel, font=ImageFont.truetype(FONT_BOLD, 34), fill=(255, 255, 255))
    img.save(out, "PNG")


def _run(cmd):
    subprocess.run(cmd, check=True)


def _encode_animated(bases, aud, seg, kind, dur, dry, mouth_aud=None, bpm=168, afilter="apad=pad_dur=0.25",
                     look="pipo", dance=()):
    """Compone el personaje sobre el fondo frame a frame y lo manda a ffmpeg por stdin.
    `bases` = [(inicio_s, png)] ordenado; cada fondo se usa desde su inicio hasta el siguiente.
    `dance` = [(inicio_s, fin_s)] donde el personaje baila con los dos brazos (coros)."""
    W, H = SIZES[kind]
    bases = [(t, Image.open(p).convert("RGB")) for t, p in bases]
    n = int(round(dur * FPS))
    env = character.mouth_envelope(mouth_aud or aud, FPS, dry)
    size = int(min(W * 0.30, H * 0.62)) if kind == "long" else int(W * 0.78)
    pos = (W - size - int(W * 0.03), H - size - int(H * 0.04)) if kind == "long" else ((W - size) // 2, H - size - int(H * 0.04))
    proc = subprocess.Popen([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-i", aud, "-af", afilter, "-t", f"{dur:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", seg,
    ], stdin=subprocess.PIPE)
    b = 0
    for i in range(n):
        t = i / FPS
        while b + 1 < len(bases) and bases[b + 1][0] <= t:
            b += 1
        frame = bases[b][1].copy()
        sprite = character.draw_character(t, env[i] if i < len(env) else 0.0, size, bpm, look,
                                          any(a <= t < b for a, b in dance))
        frame.paste(sprite, pos, sprite)
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg falló al codificar el segmento animado")


def render_song(song, timeline, mix_wav, voc_wav, bpm, dur, kind, workdir, palette, channel, dry=False, max_secs=None):
    """Video musical: un fondo por verso (letra en pantalla) sobre el escenario de la canción;
    el personaje rebota al bpm, baila en los coros y mueve la boca con la voz."""
    os.makedirs(workdir, exist_ok=True)
    if max_secs and dur > max_secs:
        # cortar al final de la última sección (coro/estrofa) completa que quepa, más 1 s de cola con fade
        part_end = {}
        for e in timeline:
            part_end[e["part"]] = e["end"]
        cut = max((end for end in part_end.values() if end + 1 <= max_secs), default=max_secs - 1)
        timeline = [e for e in timeline if e["end"] <= cut]
        dur = cut + 1
    look = song.get("character", "pipo")
    name = character.CAST[look]["desc"].split(",")[0]
    events = [{"start": 0, "section": "", "text": f"¡A cantar con {name}!"}] + timeline + \
             [{"start": timeline[-1]["end"], "section": "", "text": "¡Canta otra vez conmigo!"}]
    bases = []
    for i, e in enumerate(events):
        png = os.path.join(workdir, f"{i:03d}.png")
        headline = "¡Todos al coro!" if e["section"] == "Coro" else song["topic"]
        draw_frame(png, kind, headline, e["text"], palette, min(1.0, e["start"] / dur), channel, animate=True,
                   scene=song.get("scene"), scene_seed=song["topic"])
        bases.append((e["start"], png))
    final = os.path.join(workdir, f"{kind}.mp4")
    _encode_animated(bases, mix_wav, final, kind, dur, dry, mouth_aud=voc_wav, bpm=bpm,
                     afilter=f"afade=t=out:st={max(0, dur - 1.5):.2f}:d=1.5", look=look,
                     dance=[(e["start"], e["end"]) for e in timeline if e["section"] == "Coro"])
    print(f"[render] {kind} (canción): {len(timeline)} versos, {dur:.1f}s → {final}")
    return final, dur


def render_video(script, kind, workdir, voice, rate, palette, channel, dry=False, animate=False):
    os.makedirs(workdir, exist_ok=True)
    units = [(sc["headline"], s) for sc in script["scenes"] for s in split_sentences(sc["narration"])]
    seg_paths, total = [], 0.0
    for i, (headline, sentence) in enumerate(units):
        img, aud, seg = (os.path.join(workdir, f"{i:03d}.{ext}") for ext in ("png", "mp3", "mp4"))
        dur = synth(sentence, voice, aud, rate=rate, dry=dry)
        draw_frame(img, kind, headline, sentence, palette, (i + 1) / len(units), channel, animate)
        if animate:
            _encode_animated([(0, img)], aud, seg, kind, dur + 0.25, dry)
            seg_paths.append(seg)
            total += dur + 0.25
            continue
        _run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-loop", "1", "-framerate", str(FPS), "-i", img, "-i", aud,
            "-af", "apad=pad_dur=0.25", "-t", f"{dur + 0.25:.3f}",
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage",
            "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2", seg,
        ])
        seg_paths.append(seg)
        total += dur + 0.25

    lst = os.path.join(workdir, "list.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{os.path.abspath(p)}'\n" for p in seg_paths)
    final = os.path.join(workdir, f"{kind}.mp4")
    _run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
          "-c", "copy", "-movflags", "+faststart", final])
    print(f"[render] {kind}: {len(units)} segmentos, {total:.1f}s → {final}")
    if kind == "short" and total > 178:
        print("[render] ⚠️ Short > 3 min: YouTube lo tratará como video normal")
    return final, total
