"""Texto a voz gratis con edge-tts. En DRY_RUN genera silencio con ffmpeg."""
import asyncio
import json
import re
import subprocess
import time


def split_sentences(text, min_len=25):
    parts = [p.strip() for p in re.split(r"(?<=[.!?…])\s+", text.strip()) if p.strip()]
    merged = []
    for p in parts:
        if merged and len(merged[-1]) < min_len:
            merged[-1] = f"{merged[-1]} {p}"
        else:
            merged.append(p)
    return merged


def duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(json.loads(out)["format"]["duration"])


async def _edge(text, voice, rate, pitch, out):
    import edge_tts

    await edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(out)


def synth(text, voice, out, rate="+0%", dry=False, pitch="+0Hz"):
    if dry:
        secs = max(1.5, len(text.split()) / 2.6)
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
             "anullsrc=r=24000:cl=mono", "-t", f"{secs:.2f}", "-c:a", "libmp3lame", out],
            check=True,
        )
        return duration(out)
    for i in range(4):
        try:
            asyncio.run(_edge(text, voice, rate, pitch, out))
            return duration(out)
        except Exception as e:
            print(f"[tts] intento {i + 1} falló: {e}")
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"TTS falló para: {text[:60]}...")
