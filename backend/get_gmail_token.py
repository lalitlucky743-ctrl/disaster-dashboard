
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

flow = InstalledAppFlow.from_client_secrets_file(
    "credentials.json",
    SCOPES,
)

credentials = flow.run_local_server(
    host="localhost",
    port=8080,
    open_browser=True,
    access_type="offline",
    prompt="consent",
)

if not credentials.refresh_token:
    raise RuntimeError(
        "Refresh token nahi mila. OAuth consent dobara check karo."
    )

print("\nGMAIL_REFRESH_TOKEN (secret; ise share mat karna):")
print(credentials.refresh_token)
