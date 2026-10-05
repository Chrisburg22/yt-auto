# yt-auto — canal infantil: 1 video largo + 1 Short diario, 100% automático

> **Nicho:** educativo para niños de 6 a 12 años. Todo se sube como `selfDeclaredMadeForKids: true`.
> Consecuencias de "made for kids": sin comentarios, sin anuncios personalizados (menor RPM), sin tarjetas ni pantallas finales, sin campana de notificaciones. Es obligatorio por COPPA; no lo apagues.
> Cada guion pasa por un **revisor de seguridad infantil** (segunda llamada a Claude). Si lo rechaza 3 veces, ese día **no se sube nada** y el job falla en rojo para que te enteres.

```
cron (GitHub Actions, 09:00 GDL)
  → Claude API: guion largo (tema nuevo, formato rotativo)
  → Claude revisor: seguridad infantil + datos (si rechaza → regenera con feedback, máx 3)
  → Claude API: Short con ángulo distinto del mismo tema (+ revisión)
  → edge-tts (voz gratis) por oración
  → Pillow frames + ffmpeg → long.mp4 (1920x1080) + short.mp4 (1080x1920)
  → YouTube Data API: sube largo (público) + miniatura
  → sube Short (programado +4h, con link al largo)
  → commit de state/history.json (evita temas repetidos y doble subida)
```

## Setup (una sola vez)

### 1. Repo
- Crea un repo en GitHub y sube esta carpeta.
- **Público = minutos de Actions ilimitados.** Privado = 2,000 min/mes gratis (este job usa ~10-20 min/día → cabe).
- Edita `config.yaml` → `channel.name` (el nicho ya viene configurado).

### 2. Google Cloud + YouTube
1. console.cloud.google.com → proyecto nuevo → habilita **YouTube Data API v3**.
2. **Pantalla de consentimiento OAuth** → tipo Externo → agrégate como test user → **"Publicar app" (In production)**.
   ⚠️ Si la dejas en "Testing", el refresh token **caduca a los 7 días** y el cron muere en silencio.
3. Credenciales → OAuth client ID → tipo **Desktop app** → descarga `client_secret.json`.
4. Local:
   ```bash
   pip install google-auth-oauthlib
   python scripts/get_refresh_token.py client_secret.json
   ```
   Inicia sesión con la cuenta **dueña del canal**.
5. **Pide la auditoría** (formulario "YouTube API Services – Audit and Quota Extension"). Sin ella, TODO lo que suba la API queda privado para siempre. Mientras tanto, prueba con `publish.privacy: private`.
6. Verifica tu canal por teléfono (youtube.com/verify) para que funcione `thumbnails.set`.

### 3. Secrets en GitHub (Settings → Secrets and variables → Actions)
| Secret | Valor |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `YT_CLIENT_ID` | de `client_secret.json` |
| `YT_CLIENT_SECRET` | de `client_secret.json` |
| `YT_REFRESH_TOKEN` | salida del paso 2.4 |

### 4. Aprobación antes de publicar
Settings → Environments → **New environment** `produccion` → **Required reviewers**: tú → Save.
(Gratis en repos públicos.) Cada día el job **generar** deja los videos en el artifact `videos`
y la letra en el resumen del run; te llega un aviso y el job **publicar** espera a que apruebes.
Si rechazas, ese día no se sube nada.

### 5. Probar
- Actions → "Video diario" → Run workflow → `dry_run: true` → descarga el artifact y revisa los MP4.
- Luego corre con `dry_run: false` y `privacy: private` para el primer real.

## Local
```bash
sudo apt install ffmpeg fonts-dejavu-core   # macOS: brew install ffmpeg (y ajusta FONT_BOLD/FONT_REG)
pip install -r requirements.txt
DRY_RUN=1 python -m src.main                # sin API, audio en silencio
```

## Costos
- GitHub Actions, edge-tts, ffmpeg, YouTube API: $0.
- Claude API: 4-8 llamadas/día (guion + revisión, largo y Short). Revisa precio vigente del modelo en `config.yaml`.

## Notas
- `edge-tts` usa el servicio de voz de Microsoft Edge (no oficial). Si un día falla, el job reintenta 4 veces y luego falla sin subir nada. Para producción seria, cambia `src/tts.py` por ElevenLabs/OpenAI TTS.
- Idempotente: si el largo se subió y el Short falló, reintentar solo sube el Short.
- Cada video se marca `containsSyntheticMedia: true` (voz IA).
- Scheduled workflows solo corren en la rama default.
