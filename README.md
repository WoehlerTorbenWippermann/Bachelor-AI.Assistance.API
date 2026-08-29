# AI.Assistance.API

> ℹ️ **This README was created with the support of AI** (Claude, based on the actual source code) — not exclusively AI-generated — and was reviewed by the author. Verify commands, versions, and paths in your own environment before relying on them.

REST API for an **AR repair assistant**. A technician (e.g. via a HoloLens 2)
sends a question together with a camera image to the API; it answers the question
briefly based on a repair manual, marks the relevant spot in the image with
bounding boxes, and additionally returns the answer as speech (MP3).

Under the hood it runs **Google Gemini** with a pre-built **context cache** (the
manual knowledge), so every request is cheap and fast. The server framework is
**FastAPI** (uvicorn).

---

## Requirements

- **Windows** – the project was developed and tested on Windows
  (the commands in this guide are PowerShell)
- **Python 3.11+** (tested with 3.14)
- A **Google Gemini API key** – available for free from the
  [Google AI Studio](https://aistudio.google.com/app/apikey)
- Internet access (the API calls the Gemini servers)

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/WoehlerTorbenWippermann/AI.Assistance.API
cd AI.Assistance.API
```

### 2. Create a virtual environment (optional, recommended)

```bash
python -m venv .venv
```

```bash
.venv\Scripts\Activate.ps1
```

### 3. Install the dependencies

```bash
pip install -r requirements.txt
```

Installs: `fastapi`, `uvicorn`, `python-multipart` (for file uploads),
`google-genai`, `pillow` (image processing) and `gTTS` (text-to-speech).

### 4. Set the API key

The Gemini key is set in [`config.py`](config.py):

```python
# config.py
API_KEY = "YOUR_GEMINI_API_KEY"
```

> **Important:** enter your **own** key here. The key is required for the Gemini
> calls – without it the server does not start (the cache cannot be built).

---

## Running

```bash
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

On the first start the API loads the manual knowledge into a Gemini cache – you
will see `[Cache] …` messages in the terminal. Once `Application startup complete`
appears, the server runs on **http://localhost:8000**.

> `--reload` restarts the server automatically on code changes (handy during
> development). For **debugging**, drop `--reload` – see below.

---

## 💡 The `/docs` trick: try the endpoints in the browser

FastAPI automatically generates **interactive API documentation**. Just open it in
the browser:

```
http://localhost:8000/docs
```

All endpoints are listed there. You can call each one via **"Try it out"**: fill in
the fields (enter a question, optionally upload an image), click **"Execute"**, and
immediately see the JSON response, the matching `curl` command and the response
codes. Ideal for testing and understanding the API without Unity/HoloLens.

(An alternative documentation view is available at `http://localhost:8000/redoc`.)

---

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/ask` | Core endpoint: question (+ optional image) → answer, annotated image, audio, boxes |
| `GET`  | `/health` | Status check (active sessions, stored files) |
| `DELETE` | `/session/{session_id}` | Delete a conversation session |
| `GET` | `/download/image/{file_id}` | Retrieve the annotated image (**once** – deleted afterwards) |
| `GET` | `/download/audio/{file_id}` | Retrieve the speech audio (MP3) (**once** – deleted afterwards) |

### `/ask` – parameters (form data)

| Field | Type | Required | Description |
|---|---|---|---|
| `question` | text | yes | The technician's question |
| `session_id` | text | no | For follow-up questions in the same conversation; empty = new session |
| `language` | text | no | `german` (default) or `english` |
| `image` | file | no | Camera image (JPEG/PNG/WebP) |

**Response (JSON):**
```json
{
  "session_id": "…",
  "answer": "Short answer in 1-2 sentences.",
  "image_url": "http://localhost:8000/download/image/…",
  "audio_url": "http://localhost:8000/download/audio/…",
  "boxes": [{ "label": "…", "box_2d": [y_min, x_min, y_max, x_max] }]
}
```

The `box_2d` coordinates are normalised to **0–1000** (not pixels):
`y=0` top, `y=1000` bottom, `x=0` left, `x=1000` right.

### Example with `curl`

```bash
curl -X POST http://localhost:8000/ask -F "question=What do you see here?" -F "language=english" -F "image=@myimage.jpg"
```

---

## Adjusting the knowledge base

The manual knowledge lives as Markdown files and is listed in
[`config.py`](config.py) under `KNOWLEDGE_FILES`:

```python
KNOWLEDGE_FILES = [
    os.path.join(_BASE_DIR, "Woehler_SC_602_Smart_Connect.md"),
    os.path.join(_BASE_DIR, "Anleitung_SC602.md"),
]
```

Just add more `.md` files to the list – they are loaded into the cache
automatically on the next start (missing files are skipped with a warning). When
the content changes, the API builds a new cache automatically (detected via a
content hash).

The assistant's behaviour (answer style, rules) is controlled by the
`SYSTEM_INSTRUCTION` in `config.py`.

---

## Debugging in VS Code

A configuration is already provided for debugging
([`.vscode/launch.json`](.vscode/launch.json)):

1. Install the Microsoft **Python extension**.
2. Open the Run and Debug tab (`Ctrl+Shift+D`), select the
   **"FastAPI: debug /ask"** configuration and press **F5**.
3. Set breakpoints to the left of the line numbers in [`api.py`](api.py).
4. Trigger requests via `http://localhost:8000/docs` – the debugger stops.

> Breakpoints only work **without** `--reload` (reload mode runs in a subprocess).
> The debug configuration therefore starts uvicorn without reload.

---

## Project structure

```
api.py                  FastAPI app + endpoints (entry point)
config.py               Central configuration (API key, model, prompts, knowledge)
requirements.txt        Python dependencies
query/
  AnnotateImage.py      Draw bounding boxes onto the image (draw_boxes)
utils/
  CacheHelper.py        Build/reuse the Gemini context cache
  ImageHelper.py        Prepare images for Gemini
  CombinedHelper.py     Build the prompt & parse the answer/boxes JSON
  TextToSpeech.py       Answer → MP3 (gTTS)
*.md                    Manual knowledge (knowledge base)
```

---

## Flow of an `/ask` request (short version)

1. Accept the request, choose the language, find/create the session.
2. Save the optional image to a temp file and correct the EXIF orientation.
3. **One** Gemini call (with the manual cache) returns the answer text **and**
   bounding boxes as JSON.
4. Write the answer to the session history, split the JSON into text + boxes.
5. Build the annotated image (`draw_boxes`) and the speech audio (`gTTS`).
6. Return JSON with `answer`, download URLs and `boxes`; clean up the temp image.
