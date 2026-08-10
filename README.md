# Road Friend — Personal AI Companion

Road Friend is a local-first voice + text personal companion for your Mac. It can search the public web, summarize results conversationally, use your live location, open Google/Google Maps/YouTube/Prime Video with permission, read files you explicitly choose, connect to Gmail, and use optional local AI through Ollama.

## How it behaves

You can talk naturally:

```text
You: What's happening with Nvidia today?
Road Friend: I checked the web. The main things I'm seeing are ...

You: Find coffee near me.
Road Friend: [uses structured Google Places if configured; otherwise asks to open Google Maps at your location]

You: Play Interstellar trailer on YouTube.
Road Friend: I can open YouTube and search for that. Want me to open it?
You: Yes.
Road Friend: Opening YouTube.

You: Find The Boys on Prime.
Road Friend: Want me to open Prime Video and search for it?
```

External browser actions require approval. Private data access requires permission. Sending email or Messages requires a separate confirmation.

## No Google Cloud required for normal questions

Normal public-web questions use a key-free web-search backend. Google Cloud is not required for that.

For natural AI summarization you have two choices:

### Option A — fully local conversation with Ollama

Install Ollama on your Mac, then run a local model such as Llama:

```bash
ollama pull llama3.2
ollama serve
```

Add to `.env`:

```text
OLLAMA_MODEL=llama3.2
```

Road Friend will search the web and give the search results to the local model to produce a natural spoken summary.

### Option B — Gemini API

You can still use Gemini if you want:

```text
GEMINI_API_KEY=...
```

Gemini is optional.

## Google Maps behavior

Two modes are supported:

1. **No Maps API key:** Road Friend asks permission and opens real Google Maps in your browser using your query/location.
2. **Maps API key configured:** Road Friend can directly read structured place names, ratings, review counts, coordinates, routes and traffic-aware ETAs.

Optional:

```text
GOOGLE_MAPS_API_KEY=...
```

## Browser tools

Road Friend can prepare and open, after approval:

- Google Search
- Google Maps
- YouTube search
- Prime Video search

Examples:

```text
search Google for latest AI news
open Google Maps for sushi near me
play Telugu songs on YouTube
open Oppenheimer on Prime Video
```

Road Friend opens normal browser pages. It does not bypass logins, subscriptions, DRM, or paywalls. If YouTube/Prime requires your account, you use your normal signed-in browser session.

## Local files

Road Friend never crawls your Mac. When you ask it to read a document, it asks permission and opens a file picker. Only the file you select is sent to the local Road Friend process.

Supported types include PDF, DOCX, XLSX, PPTX, CSV, text, Markdown and JSON.

## Run on Mac

```bash
git clone https://github.com/Jashwanth248/Road_Friend.git
cd Road_Friend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8080
```

Open Chrome:

```text
http://localhost:8080
```

Then use **Talk** or **Hands Free**.

## Optional `.env`

Road Friend can start without Google API keys. Example:

```text
# Best local/no-cloud conversational mode
OLLAMA_MODEL=llama3.2
OLLAMA_BASE_URL=http://127.0.0.1:11434

# Optional cloud AI
# GEMINI_API_KEY=...

# Optional structured Maps ratings/routes/traffic
# GOOGLE_MAPS_API_KEY=...

# Optional macOS Messages sending
ALLOW_MACOS_MESSAGES=false
```

## Permission model

| Capability | Rule |
|---|---|
| Public web search | Allowed |
| Open Google/Maps/YouTube/Prime | Ask before opening |
| Location | Browser permission |
| Local files | Ask + user file picker |
| Gmail reading | Ask + OAuth |
| Gmail sending | Confirm every send |
| macOS Messages | Confirm every send |
| Camera | Off by default |
| Driving perception | Advisory only |

## Important limits

Road Friend can open YouTube or Prime Video searches in your browser, but it does not bypass account authentication or streaming protections. Directly scraping Google Search/Google Maps pages in the background is intentionally avoided because it is brittle; structured Maps details require the official Maps API, while normal web answers use the independent key-free search backend.
