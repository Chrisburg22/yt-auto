"""Genera guiones (largo + Short) con la API de Claude. Devuelve dicts validados."""
import json
import os
import re
import time

SYSTEM = (
    "Eres guionista senior de un canal de YouTube en español. "
    "Escribes para ser LEÍDO EN VOZ ALTA por una voz sintética: oraciones cortas, "
    "sin emojis, sin markdown, sin acotaciones entre paréntesis ni corchetes. "
    "Solo incluyes datos de los que estás seguro. "
    "Tu público son NIÑOS: todo debe ser apropiado, amable, positivo y educativo. "
    "Prohibido: miedo, violencia, peligro, sustancias, romance, burlas, groserías, "
    "retos o experimentos que un niño pueda imitar y lastimarse, pedir datos personales, "
    "invitar a salir de YouTube, vender o promocionar productos, y frases manipuladoras "
    "('si no ves hasta el final...', 'dale like o...'). "
    "Respondes ÚNICAMENTE con JSON válido, sin texto extra ni bloques de código."
)

JSON_SHAPE = """{
  "topic": "tema en pocas palabras",
  "title": "máx 90 caracteres, atractivo pero honesto",
  "description": "2-3 párrafos + 3-5 hashtags al final",
  "tags": ["8 a 15 tags"],
  "thumbnail_text": "máx 4 palabras",
  "scenes": [{"headline": "máx 6 palabras", "narration": "texto a narrar"}]
}"""


def _channel_block(cfg):
    ch = cfg["channel"]
    return (
        f"Canal: {ch['name']}\nNicho: {ch['niche']}\n"
        f"Audiencia: {ch['audience']}\nIdioma: {ch['language']}\n"
    )


def long_prompt(cfg, fmt, history):
    used = "\n".join(f"- {h['topic']} | {h.get('long', {}).get('title', '')}" for h in history[-60:]) or "- (ninguno)"
    return f"""{_channel_block(cfg)}
Formato de hoy: {fmt['name']} — {fmt['desc']}

Temas ya publicados (NO repitas tema ni ángulo):
{used}

Escribe el guion de un video horizontal de 4 a 6 minutos (600 a 850 palabras de narración en total).
Reglas:
- Elige UN tema nuevo, específico y concreto dentro del nicho.
- Primera escena: una pregunta o dato que despierte curiosidad. Sin "hola a todos".
- Entre 8 y 12 escenas. Cada "narration" de 50 a 100 palabras, oraciones de máx 15 palabras.
- Palabras sencillas; si usas una palabra difícil, explícala enseguida.
- Compara con cosas que el niño conoce (su casa, la escuela, juguetes, comida).
- Incluye 1 o 2 preguntas para que el niño piense ("¿Tú qué crees?") y una pausa para responder.
- Última escena: repaso de lo aprendido en 2 o 3 oraciones y una despedida cálida. Sin pedir like ni suscripción.
- "title": claro y descriptivo, sin mayúsculas exageradas ni signos de alarma.

Devuelve SOLO este JSON:
{JSON_SHAPE}"""


def short_prompt(cfg, long_script):
    return f"""{_channel_block(cfg)}
Hoy publicamos un video largo titulado "{long_script['title']}" sobre: {long_script['topic']}.

Escribe un YouTube Short vertical para niños de 40 a 55 segundos (100 a 140 palabras en total) con un ÁNGULO DISTINTO
al del video largo: un solo dato sorprendente o una sola idea, no un resumen.
Reglas:
- La primera oración es el gancho y debe funcionar sin contexto.
- Entre 4 y 6 escenas, oraciones muy cortas.
- Palabras sencillas, tono alegre.
- Cierra con: "¡Hay más en el video completo!"
- "title": máx 70 caracteres (sin #Shorts, se agrega automático).

Devuelve SOLO este JSON:
{JSON_SHAPE}"""


def _extract_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON en la respuesta")
    return json.loads(text[start : end + 1])


def _validate(s):
    for k in ("topic", "title", "description", "tags", "thumbnail_text", "scenes"):
        if k not in s:
            raise ValueError(f"Falta campo '{k}'")
    s["scenes"] = [sc for sc in s["scenes"] if sc.get("narration", "").strip()]
    if len(s["scenes"]) < 3:
        raise ValueError("Muy pocas escenas")
    return _clean_meta(s)


def _clean_meta(s):
    s["title"] = s["title"].strip()[:95]
    s["description"] = s["description"][:4800]
    # YouTube: tags suman máx ~500 caracteres
    tags, total = [], 0
    for t in s["tags"]:
        t = str(t).strip().replace("#", "")
        if t and total + len(t) + 1 < 480:
            tags.append(t)
            total += len(t) + 1
    s["tags"] = tags
    return s


def call_claude(cfg, prompt, attempts=3, validate=_validate):
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    last = None
    for i in range(attempts):
        try:
            msg = client.messages.create(
                model=cfg["llm"]["model"],
                max_tokens=8000,
                system=SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
            return validate(_extract_json(text))
        except Exception as e:  # JSON roto, rate limit, etc.
            last = e
            print(f"[claude] intento {i + 1} falló: {e}")
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"Claude falló {attempts} veces: {last}")


REVIEW_PROMPT = """Eres revisor de contenido infantil (niños de 6 a 12 años) para YouTube, con criterio de experto en desarrollo infantil.
Revisa este guion y responde SOLO JSON: {{"approved": true|false, "issues": ["..."]}}

Rechaza (approved=false) si encuentras CUALQUIERA de estas cosas:
- Datos falsos o dudosos presentados como hechos.
- Contenido que dé miedo, violento, sexual, discriminatorio o con burlas.
- Actividades que un niño pueda imitar y hacerse daño (fuego, químicos, alturas, objetos pequeños, comer cosas).
- Promoción de marcas o productos, o incitar a comprar.
- Pedir datos personales, invitar a salir de YouTube o a hablar con desconocidos.
- Título o miniatura sensacionalistas o engañosos.
- Vocabulario demasiado difícil sin explicar.

Guion:
{script}"""


def review(cfg, script):
    """Segunda opinión de Claude. Devuelve (aprobado, problemas)."""
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model=cfg["llm"]["model"],
        max_tokens=1500,
        system="Eres un revisor estricto. Respondes solo JSON válido.",
        messages=[{"role": "user", "content": REVIEW_PROMPT.format(script=json.dumps(script, ensure_ascii=False))}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    try:
        r = _extract_json(text)
        return bool(r.get("approved")), r.get("issues", [])
    except Exception as e:
        return False, [f"Revisión ilegible: {e}"]


def generate_safe(cfg, prompt, attempts=3, validate=_validate):
    """Genera y revisa. Si el revisor rechaza, regenera pasando los problemas. Si no pasa nunca, falla."""
    issues = []
    for i in range(attempts):
        extra = ("\n\nUn revisor rechazó tu versión anterior por esto, corrígelo:\n- " + "\n- ".join(issues)) if issues else ""
        script = call_claude(cfg, prompt + extra, validate=validate)
        ok, issues = review(cfg, script)
        print(f"[review] intento {i + 1}: {'✅ aprobado' if ok else '❌ ' + '; '.join(issues)}")
        if ok:
            return script
    raise RuntimeError("El guion no pasó la revisión infantil. No se sube nada hoy.")


# ---------- modo DRY_RUN (sin API) ----------
def fake_script(kind):
    n = 4 if kind == "short" else 6
    return _validate({
        "topic": "Prueba de pipeline",
        "title": f"Video de prueba ({kind})",
        "description": "Descripción de prueba.\n\n#prueba",
        "tags": ["prueba", "pipeline"],
        "thumbnail_text": "ESTO ES UNA PRUEBA",
        "scenes": [
            {
                "headline": f"Escena número {i + 1}",
                "narration": "Esta es una oración de prueba para el pipeline. "
                "Aquí va una segunda oración un poco más larga para ver cómo se acomoda el subtítulo en pantalla.",
            }
            for i in range(n)
        ],
    })
