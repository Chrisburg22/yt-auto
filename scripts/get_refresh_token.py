"""Corre esto UNA vez en tu compu para obtener el refresh token de YouTube.

  pip install google-auth-oauthlib
  python scripts/get_refresh_token.py client_secret.json

Copia el valor impreso al secret YT_REFRESH_TOKEN de GitHub. No lo subas al repo.
"""
import sys
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1] if len(sys.argv) > 1 else "client_secret.json", SCOPES)
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
print("\nYT_REFRESH_TOKEN =", creds.refresh_token)
