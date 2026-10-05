"""Escenarios dibujados por código (Pillow) según el tema de la canción. Variación determinista por semilla."""
import math
import random

from PIL import Image, ImageDraw

# Claude elige uno por canción; la clave va en el JSON de la letra.
SCENES = {
    "mar": "fondo del mar con burbujas, algas y peces",
    "espacio": "espacio con estrellas, planetas y luna",
    "bosque": "bosque con árboles, colinas y flores",
    "granja": "granja con granero, cerca y sol",
    "cielo": "cielo con nubes, sol y arcoíris",
    "casa": "cuarto de una casa con ventana, alfombra y repisa",
}


def _grad(W, H, top, bottom):
    img = Image.new("RGB", (W, H), top)
    mask = Image.linear_gradient("L").resize((W, H))
    img.paste(Image.new("RGB", (W, H), bottom), (0, 0), mask)
    return img


def _cloud(d, x, y, r, fill):
    for dx, dy, k in ((-1.0, 0.2, 0.7), (0, 0, 1.0), (1.0, 0.2, 0.75), (0.5, 0.35, 0.7), (-0.5, 0.35, 0.7)):
        rr = r * k
        d.ellipse((x + dx * r - rr, y + dy * r - rr, x + dx * r + rr, y + dy * r + rr), fill=fill)


def _tree(d, x, ground, h, rng):
    d.rectangle((x - h * 0.06, ground - h * 0.45, x + h * 0.06, ground), fill=(120, 72, 40))
    green = rng.choice([(34, 197, 94), (22, 163, 74), (74, 222, 128)])
    for dx, dy, r in ((0, -0.62, 0.30), (-0.2, -0.5, 0.22), (0.2, -0.5, 0.22)):
        d.ellipse((x + dx * h - r * h, ground + dy * h - r * h, x + dx * h + r * h, ground + dy * h + r * h), fill=green)


def draw_scene(theme, W, H, seed=0):
    rng = random.Random(f"{theme}-{seed}")
    u = min(W, H)

    if theme == "mar":
        img = _grad(W, H, (56, 189, 248), (3, 105, 161))
        d = ImageDraw.Draw(img, "RGBA")
        for i in range(6):  # rayos de luz
            x = rng.uniform(0, W)
            d.polygon([(x, 0), (x + u * 0.08, 0), (x + u * 0.3, H), (x + u * 0.15, H)], fill=(255, 255, 255, 18))
        d.ellipse((-W * 0.2, H * 0.86, W * 1.2, H * 1.3), fill=(253, 230, 138))
        for _ in range(9):  # algas
            x, hh = rng.uniform(0, W), rng.uniform(0.12, 0.3) * H
            pts = [(x + math.sin(k / 3) * u * 0.02, H * 0.92 - hh * k / 10) for k in range(11)]
            d.line(pts, fill=(22, 163, 74), width=int(u * 0.018), joint="curve")
        for _ in range(5):  # peces
            x, y, s = rng.uniform(0.05, 0.6) * W, rng.uniform(0.15, 0.7) * H, rng.uniform(0.03, 0.05) * u
            c = rng.choice([(251, 146, 60), (250, 204, 21), (244, 114, 182)])
            d.ellipse((x - s, y - s * 0.6, x + s, y + s * 0.6), fill=c + (200,))
            d.polygon([(x + s * 0.8, y), (x + s * 1.5, y - s * 0.5), (x + s * 1.5, y + s * 0.5)], fill=c + (200,))
        for _ in range(25):  # burbujas
            x, y, r = rng.uniform(0, W), rng.uniform(0, H * 0.85), rng.uniform(0.004, 0.015) * u
            d.ellipse((x - r, y - r, x + r, y + r), outline=(255, 255, 255, 120), width=max(2, int(r * 0.25)))

    elif theme == "espacio":
        img = _grad(W, H, (15, 23, 42), (49, 46, 129))
        d = ImageDraw.Draw(img, "RGBA")
        for _ in range(220):
            x, y, r = rng.uniform(0, W), rng.uniform(0, H), rng.choice([1, 1, 2, 3])
            d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, rng.randint(120, 255)))
        for _ in range(3):
            x, y, r = rng.uniform(0.1, 0.9) * W, rng.uniform(0.1, 0.6) * H, rng.uniform(0.04, 0.09) * u
            c = rng.choice([(251, 146, 60), (96, 165, 250), (244, 114, 182), (52, 211, 153)])
            d.ellipse((x - r, y - r, x + r, y + r), fill=c + (220,))
            if rng.random() < 0.5:
                d.ellipse((x - r * 1.8, y - r * 0.35, x + r * 1.8, y + r * 0.35), outline=(253, 224, 71, 200), width=int(r * 0.12))
        d.ellipse((-W * 0.1, H * 0.85, W * 1.1, H * 1.4), fill=(203, 213, 225))  # suelo lunar
        for _ in range(6):
            x, r = rng.uniform(0, W), rng.uniform(0.02, 0.05) * u
            d.ellipse((x - r, H * 0.93 - r * 0.3, x + r, H * 0.93 + r * 0.3), fill=(148, 163, 184))

    elif theme in ("bosque", "granja"):
        img = _grad(W, H, (125, 211, 252), (224, 242, 254))
        d = ImageDraw.Draw(img, "RGBA")
        sx, sy, sr = W * rng.uniform(0.55, 0.85), H * 0.14, u * 0.08
        d.ellipse((sx - sr, sy - sr, sx + sr, sy + sr), fill=(253, 224, 71))
        for _ in range(3):
            _cloud(d, rng.uniform(0, W), rng.uniform(0.08, 0.3) * H, u * rng.uniform(0.04, 0.06), (255, 255, 255, 230))
        d.ellipse((-W * 0.3, H * 0.55, W * 0.7, H * 1.3), fill=(74, 222, 128))
        d.ellipse((W * 0.3, H * 0.6, W * 1.4, H * 1.3), fill=(34, 197, 94))
        d.rectangle((0, H * 0.82, W, H), fill=(22, 163, 74))
        if theme == "bosque":
            for _ in range(7):
                _tree(d, rng.uniform(0, W), H * rng.uniform(0.7, 0.86), u * rng.uniform(0.25, 0.4), rng)
        else:
            bx, by, bw = W * 0.08, H * 0.82, u * 0.32
            d.rectangle((bx, by - bw * 0.7, bx + bw, by), fill=(220, 38, 38))
            d.polygon([(bx - bw * 0.08, by - bw * 0.7), (bx + bw * 1.08, by - bw * 0.7), (bx + bw / 2, by - bw * 1.05)], fill=(153, 27, 27))
            d.rectangle((bx + bw * 0.35, by - bw * 0.35, bx + bw * 0.65, by), fill=(255, 255, 255))
            for k in range(0, int(W / (u * 0.08)) + 1):  # cerca
                x = k * u * 0.08
                d.rectangle((x, H * 0.84, x + u * 0.02, H * 0.92), fill=(254, 243, 199))
            d.rectangle((0, H * 0.86, W, H * 0.875), fill=(254, 243, 199))
        for _ in range(30):  # flores
            x, y, r = rng.uniform(0, W), rng.uniform(0.86, 0.98) * H, u * 0.008
            d.ellipse((x - r, y - r, x + r, y + r), fill=rng.choice([(244, 114, 182), (250, 204, 21), (255, 255, 255)]))

    elif theme == "cielo":
        img = _grad(W, H, (56, 189, 248), (186, 230, 253))
        d = ImageDraw.Draw(img, "RGBA")
        cx, cy, r = W * 0.5, H * 1.05, max(W, H) * 0.55
        for k, c in enumerate([(239, 68, 68), (249, 115, 22), (250, 204, 21), (34, 197, 94), (59, 130, 246), (139, 92, 246)]):
            rr = r - k * u * 0.035
            d.arc((cx - rr, cy - rr, cx + rr, cy + rr), 180, 360, fill=c + (150,), width=int(u * 0.035))
        sr = u * 0.09
        d.ellipse((W * 0.1 - sr, H * 0.15 - sr, W * 0.1 + sr, H * 0.15 + sr), fill=(253, 224, 71))
        for _ in range(6):
            _cloud(d, rng.uniform(0, W), rng.uniform(0.1, 0.9) * H, u * rng.uniform(0.04, 0.08), (255, 255, 255, 235))

    else:  # casa
        wall = rng.choice([(254, 243, 199), (219, 234, 254), (252, 231, 243), (220, 252, 231)])
        img = Image.new("RGB", (W, H), wall)
        d = ImageDraw.Draw(img, "RGBA")
        for k in range(0, W, int(u * 0.06)):  # papel tapiz a rayas
            d.rectangle((k, 0, k + u * 0.025, H * 0.78), fill=(255, 255, 255, 70))
        d.rectangle((0, H * 0.78, W, H), fill=(180, 120, 70))
        for k in range(0, W, int(u * 0.15)):
            d.line((k, H * 0.78, k, H), fill=(150, 95, 55), width=3)
        wx, wy, ww = W * 0.62, H * 0.12, u * 0.3
        d.rectangle((wx, wy, wx + ww, wy + ww * 0.8), fill=(125, 211, 252), outline=(255, 255, 255), width=int(u * 0.015))
        d.line((wx + ww / 2, wy, wx + ww / 2, wy + ww * 0.8), fill=(255, 255, 255), width=int(u * 0.01))
        _cloud(d, wx + ww * 0.3, wy + ww * 0.3, ww * 0.08, (255, 255, 255, 230))
        d.rectangle((W * 0.05, H * 0.35, W * 0.3, H * 0.37), fill=(150, 95, 55))
        for k in range(4):
            x = W * 0.07 + k * u * 0.05
            d.rectangle((x, H * 0.35 - u * 0.09, x + u * 0.035, H * 0.35), fill=rng.choice([(239, 68, 68), (59, 130, 246), (34, 197, 94), (250, 204, 21)]))
        d.ellipse((W * 0.15, H * 0.86, W * 0.85, H * 1.02), fill=rng.choice([(244, 114, 182), (167, 139, 250), (45, 212, 191)]))
    return img
