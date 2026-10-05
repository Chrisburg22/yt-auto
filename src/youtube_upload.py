"""Subida resumable a YouTube Data API v3 con refresh token (OAuth offline)."""
import os
import random
import time

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
RETRY_STATUS = {500, 502, 503, 504}


def client():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        scopes=SCOPES,
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def upload(yt, path, title, description, tags, category_id, language, privacy="public", publish_at=None, made_for_kids=False):
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    status = {
        "privacyStatus": privacy,
        "selfDeclaredMadeForKids": made_for_kids,
        "containsSyntheticMedia": True,  # voz IA → etiqueta "contenido alterado o sintético"
    }
    if publish_at:  # publishAt SOLO funciona con privacyStatus=private
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
            "defaultLanguage": language,
            "defaultAudioLanguage": language,
        },
        "status": status,
    }
    media = MediaFileUpload(path, mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)

    resp, retries = None, 0
    while resp is None:
        try:
            st, resp = req.next_chunk()
            if st:
                print(f"[yt] {int(st.progress() * 100)}%")
        except HttpError as e:
            if e.resp.status in RETRY_STATUS and retries < 6:
                retries += 1
                wait = 2 ** retries + random.random()
                print(f"[yt] error {e.resp.status}, reintento en {wait:.0f}s")
                time.sleep(wait)
            else:
                raise
    vid = resp["id"]
    print(f"[yt] subido: https://youtu.be/{vid} ({status['privacyStatus']})")
    return vid


def set_thumbnail(yt, video_id, path):
    """Requiere canal verificado por teléfono. Si falla no rompe el pipeline."""
    from googleapiclient.http import MediaFileUpload

    try:
        yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(path, mimetype="image/png")).execute()
        print("[yt] miniatura lista")
    except Exception as e:
        print(f"[yt] ⚠️ miniatura falló (¿canal sin verificar?): {e}")
