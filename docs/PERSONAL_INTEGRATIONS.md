# Personal Integrations Setup

## Gemini + Google Search

Set in `.env`:

```text
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-3.6-flash
```

Road Friend uses Gemini for open-ended conversation. Current-information questions can use Google Search grounding.

## Maps and traffic

Set:

```text
GOOGLE_MAPS_API_KEY=...
```

Enable Places API (New) and Routes API in the Google Cloud project.

## Gmail

Enable Gmail API, create a Google OAuth Desktop client, and save the downloaded client JSON as `credentials.json`.

Road Friend creates `token.json` locally after the user completes OAuth.

## Spotify

Set:

```text
SPOTIFY_ACCESS_TOKEN=...
```

A full OAuth account-linking flow is planned; the current integration uses a user-supplied local token.

## macOS Messages

Optional:

```text
ALLOW_MACOS_MESSAGES=true
```

macOS may prompt for Automation permission when Road Friend first controls Messages. Sending is still protected by a one-time conversational confirmation.
