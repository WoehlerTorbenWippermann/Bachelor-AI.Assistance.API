import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import uuid
import shutil
import tempfile
import pathlib

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse, FileResponse
import uvicorn

from google import genai
from google.genai import types

from PIL import Image, ImageOps

from config import API_KEY, HTTP_OPTIONS, MODEL_ID, LANGUAGE_MAP, DEFAULT_LANGUAGE
from utils.CacheHelper import get_or_create_cache
from utils.ImageHelper import load_image_part
from utils.CombinedHelper import build_combined_api_prompt, parse_combined
from utils.TextToSpeech import text_to_mp3
from query.AnnotateImage import draw_boxes

# ──────────────────────────────────────────────────────────────
# Setup
# ──────────────────────────────────────────────────────────────

client = genai.Client(api_key=API_KEY, http_options=HTTP_OPTIONS)
cache  = get_or_create_cache()

app = FastAPI(
    title="AR Repair Assistant API",
    description="Answers technician questions with image annotation and text-to-speech.",
    version="1.0.0"
)

# session_id  -> {"history": [...], "last_image_path": str | None}
sessions:   dict[str, dict]         = {}

# file_id     -> pathlib.Path  (removed after download)
file_store: dict[str, pathlib.Path] = {}

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def save_upload_to_temp(upload: UploadFile) -> pathlib.Path:
    """Save an UploadFile to a temporary file and normalise its EXIF orientation,
    so the model and the later box drawing see the exact same upright pixels
    regardless of any orientation flag on the camera image. Prevents
    systematically shifted/rotated bounding boxes."""
    suffix = pathlib.Path(upload.filename).suffix or ".jpg"
    tmp    = pathlib.Path(tempfile.mktemp(suffix=suffix))
    with open(tmp, "wb") as f:
        shutil.copyfileobj(upload.file, f)
    _normalize_orientation(tmp)
    return tmp


def _normalize_orientation(path: pathlib.Path) -> None:
    """Apply the EXIF orientation and save the image back upright (without the
    orientation flag). Unreadable images are left unchanged."""
    try:
        with Image.open(path) as im:
            im.load()
            upright = ImageOps.exif_transpose(im)
        if upright.mode not in ("RGB", "L"):
            upright = upright.convert("RGB")
        # quality is ignored by PNG/WebP; 90 keeps JPEGs small (smaller upload).
        upright.save(path, quality=90)
    except Exception as e:
        print(f"[Upload] Could not normalise orientation ({path.name}): {e}")


def register_file(path: pathlib.Path) -> str:
    """Store a file in file_store and return its file_id."""
    file_id             = str(uuid.uuid4())
    file_store[file_id] = path
    return file_id


def run_turn(session_id: str, question: str, new_image_path: pathlib.Path | None, language_instruction: str = ""):
    """Run a single conversation turn."""
    session         = sessions[session_id]
    history         = session["history"]
    last_image_path = session["last_image_path"]

    if new_image_path:
        last_image_path = str(new_image_path)

    image_part = None
    if last_image_path:
        image_part, error = load_image_part(last_image_path)
        if error:
            raise HTTPException(status_code=400, detail=error)

    # One combined call: answer AND boxes in a single request. Fast (one round
    # trip) and token-cheap (standard image resolution). The cache holds the
    # manual text.
    if last_image_path:
        prompt = build_combined_api_prompt(question, language_instruction)
    else:
        prompt = f"{language_instruction}\n{question}" if language_instruction else question
    user_parts = []
    if image_part:
        user_parts.append(image_part)
    user_parts.append(types.Part.from_text(text=prompt))
    history.append({"role": "user", "parts": user_parts})

    contents = [
        types.Content(role=e["role"], parts=e["parts"])
        for e in history
    ]
    response = client.models.generate_content(
        model=MODEL_ID,
        config=types.GenerateContentConfig(cached_content=cache.name),
        contents=contents
    )

    answer, boxes = parse_combined((response.text or "").strip())
    # Only write the plain answer text (no JSON) into the history.
    history.append({"role": "model", "parts": [types.Part.from_text(text=answer)]})

    session["history"]         = history
    session["last_image_path"] = last_image_path

    return answer, boxes, last_image_path

# ──────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "active_sessions": len(sessions), "stored_files": len(file_store)}


@app.delete("/session/{session_id}")
def delete_session(session_id: str):
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    del sessions[session_id]
    return {"deleted": session_id}


@app.post("/ask")
async def ask(
    request:    Request,
    background: BackgroundTasks,
    question:   str        = Form(...),
    session_id: str        = Form(None),
    language:   str        = Form(DEFAULT_LANGUAGE),
    image:      UploadFile = File(None)
):
    lang_config          = LANGUAGE_MAP.get(language.lower(), LANGUAGE_MAP[DEFAULT_LANGUAGE])
    language_instruction = lang_config["instruction"]
    tts_lang             = lang_config["gtts"]

    # Create a session if needed
    if not session_id:
        session_id = str(uuid.uuid4())   # no id given -> generate a UUID
    if session_id not in sessions:
        sessions[session_id] = {"history": [], "last_image_path": None}  # new session

    # The image is optional and arrives as a stream; persist it to a temp file so
    # both the model call and draw_boxes can read it by path. None = no image sent.
    temp_image_path = None
    if image and image.filename:
        temp_image_path = save_upload_to_temp(image)

    try:
        answer, boxes, active_image_path = run_turn(session_id, question, temp_image_path, language_instruction)

        base_url  = str(request.base_url).rstrip("/")
        image_url = None
        audio_url = None

        # Build the annotated image and store it in file_store
        if active_image_path:
            p              = pathlib.Path(active_image_path)
            annotated_path = pathlib.Path(tempfile.mktemp(suffix=p.suffix))
            draw_boxes(active_image_path, boxes, output_path=annotated_path)
            image_id  = register_file(annotated_path)
            image_url = f"{base_url}/download/image/{image_id}"

        # Build the TTS audio and store it in file_store
        audio_path = pathlib.Path(tempfile.mktemp(suffix=".mp3"))
        result     = text_to_mp3(answer, output_path=audio_path, lang=tts_lang)
        if result:
            audio_id  = register_file(audio_path)
            audio_url = f"{base_url}/download/audio/{audio_id}"

        return JSONResponse({
            "session_id": session_id,
            "answer":     answer,
            "image_url":  image_url,
            "audio_url":  audio_url,
            "boxes":      boxes
        })

    finally:
        # Only clean up the newly uploaded image if it is NOT reused by the
        # session. It is kept as long as it is the session's last_image_path.
        session = sessions.get(session_id, {})
        kept_path = session.get("last_image_path")
        if temp_image_path and temp_image_path.exists():
            if str(temp_image_path) != kept_path:
                background.add_task(os.remove, temp_image_path)


@app.get("/download/image/{file_id}")
def download_image(file_id: str, background: BackgroundTasks):
    if file_id not in file_store:
        raise HTTPException(status_code=404, detail="File not found or already retrieved.")
    path    = file_store.pop(file_id)
    suffix  = path.suffix.lower()
    mime    = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"
    background.add_task(os.remove, path)
    return FileResponse(path=str(path), media_type=mime, filename=path.name)


@app.get("/download/audio/{file_id}")
def download_audio(file_id: str, background: BackgroundTasks):
    if file_id not in file_store:
        raise HTTPException(status_code=404, detail="File not found or already retrieved.")
    path = file_store.pop(file_id)
    background.add_task(os.remove, path)
    return FileResponse(path=str(path), media_type="audio/mpeg", filename=path.name)

# ──────────────────────────────────────────────────────────────
# Start
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)
