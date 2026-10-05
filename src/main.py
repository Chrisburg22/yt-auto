"""Orquestador diario en dos etapas, idempotente por fecha.

STAGE=build   → guion/letra (Claude + revisor) → voz → render → out/manifest.json (no sube nada)
STAGE=publish → lee out/manifest.json → sube largo + miniatura + Short → actualiza state/history.json
STAGE=all     → las dos seguidas (por defecto; útil en local)

En GitHub Actions hay una aprobación humana entre build y publish (environment "produccion").
"""
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import yaml

from . import render, script_gen, song

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY = os.path.join(ROOT, "state", "history.json")
OUT = os.path.join(ROOT, "out")
MANIFEST = os.path.join(OUT, "manifest.json")
TZ = ZoneInfo(os.getenv("CHANNEL_TZ", "America/Mexico_City"))


def load_history():
    if not os.path.exists(HISTORY):
        return []
    with open(HISTORY, encoding="utf-8") as f:
        return json.load(f)


def save_history(h):
    with open(HISTORY, "w", encoding="utf-8") as f:
        json.dump(h, f, ensure_ascii=False, indent=2)


def _rel(path):
    return os.path.relpath(path, OUT)


# ---------------------------------------------------------------- build
def build(cfg, date, history, dry):
    entry = next((h for h in history if h["date"] == date), {})
    rng = random.Random(date)  # mismo día → mismas elecciones si se reintenta
    fmt = rng.choice(cfg["formats"])
    palette = rng.choice(cfg["palettes"])
    voice = rng.choice(cfg["tts"]["voices"])
    ch = cfg["channel"]
    others = [h for h in history if h.get("date") != date]
    mode = cfg.get("content", {}).get("mode", "narration")
    print(f"📅 {date} | modo={mode} | formato={fmt['name']} | voz={voice} | dry={dry}")

    if mode == "song":
        if entry.get("song"):
            s = entry["song"]  # reintento: misma letra que el video ya subido
            print("↩️  Reusando la letra guardada en el historial.")
        else:
            style = rng.choice(cfg["song_styles"]) if cfg.get("song_styles") else None
            if style:
                print(f"🎵 Tipo de canción: {style['name']}")
            s = song.fake_song() if dry else script_gen.generate_safe(
                cfg, song.song_prompt(cfg, others, style), validate=song.validate_song)
        print("📝 Letra:", json.dumps({k: s[k] for k in ("chorus", "verses")}, ensure_ascii=False))
        mix, voc, timeline, bpm, dur = song.build_song(s, os.path.join(OUT, "song"), cfg, dry)
        long_path, long_secs = render.render_song(s, timeline, mix, voc, bpm, dur, "long", os.path.join(OUT, "long"),
                                                  palette, ch["name"], dry)
        short_path, short_secs = render.render_song(s, timeline, mix, voc, bpm, dur, "short", os.path.join(OUT, "short"),
                                                    palette, ch["name"], dry, max_secs=58)
        long_s, short_s, link = s, s, "Canción completa"
    else:
        rate, animate = cfg["tts"]["rate"], cfg.get("character", {}).get("enabled", False)
        long_s = script_gen.fake_script("long") if dry else script_gen.generate_safe(
            cfg, script_gen.long_prompt(cfg, fmt, others))
        long_path, long_secs = render.render_video(long_s, "long", os.path.join(OUT, "long"), voice, rate, palette,
                                                   ch["name"], dry, animate)
        short_s = script_gen.fake_script("short") if dry else script_gen.generate_safe(
            cfg, script_gen.short_prompt(cfg, long_s))
        short_path, short_secs = render.render_video(short_s, "short", os.path.join(OUT, "short"), voice, rate, palette,
                                                     ch["name"], dry, animate)
        link = "Video completo"

    thumb = os.path.join(OUT, "long", "thumb.png")
    render.draw_thumbnail(thumb, long_s["thumbnail_text"], palette, ch["name"],
                          look=long_s.get("character"), scene=long_s.get("scene"), seed=long_s["topic"])
    manifest = {
        "date": date,
        "format": "song" if mode == "song" else fmt["name"],
        "topic": long_s["topic"],
        "song": long_s if mode == "song" else None,
        "long": {"path": _rel(long_path), "thumb": _rel(thumb), "title": long_s["title"],
                 "description": long_s["description"], "tags": long_s["tags"], "seconds": round(long_secs)},
        "short": {"path": _rel(short_path), "title": f"{short_s['title'][:85]} #Shorts", "link_label": link,
                  "description": short_s["description"], "tags": short_s["tags"], "seconds": round(short_secs)},
    }
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"📦 Listo para revisar: {manifest['long']['title']} ({manifest['long']['seconds']}s) "
          f"+ Short ({manifest['short']['seconds']}s) → {MANIFEST}")
    return manifest


# ---------------------------------------------------------------- publish
def publish(cfg, manifest, history):
    from . import youtube_upload as yup

    ch, pub = cfg["channel"], cfg["publish"]
    kids = ch.get("made_for_kids", False)
    date = manifest["date"]
    entry = next((h for h in history if h["date"] == date), None)
    if entry is None:
        entry = {"date": date, "long": {}, "short": {}}
        history.append(entry)
    entry.update(format=manifest["format"], topic=manifest["topic"])
    if manifest.get("song"):
        entry["song"] = manifest["song"]
    yt = yup.client()

    lg = manifest["long"]
    if entry["long"].get("id"):
        print("↩️  Largo ya subido, solo falta el Short.")
    else:
        vid = yup.upload(yt, os.path.join(OUT, lg["path"]), lg["title"], lg["description"],
                         ch["default_tags"] + lg["tags"], ch["category_id"], ch["language"], pub["privacy"],
                         made_for_kids=kids)
        yup.set_thumbnail(yt, vid, os.path.join(OUT, lg["thumb"]))
        entry["long"] = {"id": vid, "title": lg["title"], "seconds": lg["seconds"]}
        save_history(history)  # guardar ya: si el Short falla, no se re-sube el largo

    sh = manifest["short"]
    if entry["short"].get("id"):
        print("✅ Short ya subido.")
    else:
        desc = f"{sh['link_label']}: https://youtu.be/{entry['long']['id']}\n\n{sh['description']}"
        publish_at = None
        if pub.get("short_delay_hours") and pub["privacy"] == "public":
            publish_at = (datetime.now(timezone.utc) + timedelta(hours=pub["short_delay_hours"])).strftime("%Y-%m-%dT%H:%M:%SZ")
        sid = yup.upload(yt, os.path.join(OUT, sh["path"]), sh["title"], desc, ch["default_tags"] + sh["tags"],
                         ch["category_id"], ch["language"], pub["privacy"], publish_at, made_for_kids=kids)
        entry["short"] = {"id": sid, "title": sh["title"], "seconds": sh["seconds"]}
        save_history(history)
    print("🎬 Publicado:", json.dumps({k: entry[k] for k in ("date", "topic", "long", "short")}, ensure_ascii=False))


def main():
    dry = os.getenv("DRY_RUN") == "1"
    stage = os.getenv("STAGE", "all")
    with open(os.path.join(ROOT, "config.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if "CAMBIA ESTO" in cfg["channel"]["niche"] and not dry:
        sys.exit("❌ Edita channel.niche en config.yaml antes de publicar.")
    history = load_history()

    if stage in ("build", "all"):
        date = datetime.now(TZ).date().isoformat()
        done = next((h for h in history if h["date"] == date), {})
        if done.get("long", {}).get("id") and done.get("short", {}).get("id"):
            print(f"✅ {date} ya publicado. Nada que hacer.")
            if os.path.exists(MANIFEST):
                os.remove(MANIFEST)  # que publish no reciba nada viejo
            return
        manifest = build(cfg, date, history, dry)
    else:
        if not os.path.exists(MANIFEST):
            print("ℹ️  No hay out/manifest.json: nada que publicar.")
            return
        with open(MANIFEST, encoding="utf-8") as f:
            manifest = json.load(f)

    if stage in ("publish", "all"):
        if dry:
            print("🧪 DRY_RUN: no se sube nada.")
            return
        publish(cfg, manifest, history)


if __name__ == "__main__":
    main()
