import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
import hashlib

from google import genai
from google.genai import types
from config import (API_KEY, HTTP_OPTIONS, MODEL_ID, DISPLAY_NAME,
                    KNOWLEDGE_FILES, KNOWLEDGE_PDFS, SYSTEM_INSTRUCTION)

client = genai.Client(api_key=API_KEY, http_options=HTTP_OPTIONS)

# TTL of the Gemini context cache. Set on creation and refreshed on reuse
# (server start); Gemini does not extend the expiry automatically on use.
CACHE_TTL = "7200s"  # 2 hours


def _wait_until_active(file, timeout=60):
    """Wait until an uploaded file has been processed (ACTIVE) on the Google servers."""
    waited = 0
    while file.state.name == "PROCESSING" and waited < timeout:
        time.sleep(2)
        waited += 2
        file = client.files.get(name=file.name)
    if file.state.name != "ACTIVE":
        raise ValueError(f"File '{file.display_name}' is not ACTIVE (state: {file.state.name}).")
    return file


def get_or_upload_pdf(path, display_name):
    """Ensure the PDF is present and ACTIVE on the Google servers under
    display_name: reuse an existing active upload, otherwise upload it.
    Returns the file, or None if the local path does not exist."""
    if not os.path.exists(path):
        print(f"[Cache] WARNING: PDF not found, skipping: {path}")
        return None

    for f in client.files.list():
        if f.display_name == display_name and f.state.name == "ACTIVE":
            print(f"[Cache] PDF already uploaded: '{display_name}' ({f.name})")
            return f

    print(f"[Cache] Uploading PDF: '{os.path.basename(path)}' -> '{display_name}'")
    uploaded = client.files.upload(file=path, config={"display_name": display_name})
    uploaded = _wait_until_active(uploaded)
    print(f"[Cache] PDF active: {uploaded.name}")
    return uploaded


def load_knowledge():
    """Read all knowledge files from KNOWLEDGE_FILES and join them into one text.
    Missing files are skipped with a warning so the app still starts."""
    sections = []
    for path in KNOWLEDGE_FILES:
        if not os.path.exists(path):
            print(f"[Cache] WARNING: knowledge file not found, skipping: {path}")
            continue
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        name = os.path.basename(path)
        print(f"[Cache] Knowledge loaded: {len(content):,} chars from '{name}'")
        sections.append(f"# Source: {name}\n\n{content}")

    if not sections:
        raise FileNotFoundError(
            "No knowledge files found. Please check KNOWLEDGE_FILES in config.py."
        )

    return "\n\n---\n\n".join(sections)


def _knowledge_hash(knowledge_text):
    """Hash the text knowledge, PDF bytes, system instruction and model id so the
    cache is rebuilt automatically whenever any of these changes. The model id
    matters because a cache is bound to its model."""
    h = hashlib.sha1()
    h.update(knowledge_text.encode("utf-8"))
    h.update(SYSTEM_INSTRUCTION.encode("utf-8"))
    h.update(MODEL_ID.encode("utf-8"))
    for pdf in KNOWLEDGE_PDFS:
        path = pdf["path"]
        if os.path.exists(path):
            with open(path, "rb") as f:
                h.update(f.read())
    return h.hexdigest()[:8]


def get_or_create_cache():
    """Return an active context cache, reusing a matching one or creating a new one.
    The cache holds the text of all knowledge files, any native PDFs and the system
    instruction. Its name carries a content hash, so a new cache is created
    automatically when the knowledge changes."""
    knowledge_text = load_knowledge()
    content_hash   = _knowledge_hash(knowledge_text)
    cache_name     = f"cache_md_{DISPLAY_NAME.lower().replace(' ', '_')}_{content_hash}"

    # Reuse an existing cache with matching content
    for cache in client.caches.list():
        if cache.display_name == cache_name:
            # Refresh the TTL on start: Gemini does not extend the expiry on use.
            try:
                cache = client.caches.update(
                    name=cache.name,
                    config=types.UpdateCachedContentConfig(ttl=CACHE_TTL)
                )
                print(f"[Cache] Existing cache found, TTL refreshed: {cache.name}  (expires: {cache.expire_time})")
            except Exception as e:
                print(f"[Cache] Existing cache found: {cache.name}  (TTL refresh failed: {e})")
            return cache

    # Upload PDFs (get-or-upload) and add them as native parts
    parts = [types.Part.from_text(text=knowledge_text)]
    for pdf in KNOWLEDGE_PDFS:
        uploaded = get_or_upload_pdf(pdf["path"], pdf["display_name"])
        if uploaded:
            parts.append(types.Part.from_uri(file_uri=uploaded.uri, mime_type="application/pdf"))

    print("[Cache] No matching cache found. Creating a new cache from knowledge...")
    cache = client.caches.create(
        model=MODEL_ID,
        config=types.CreateCachedContentConfig(
            contents=[types.Content(role="user", parts=parts)],
            system_instruction=SYSTEM_INSTRUCTION,
            ttl=CACHE_TTL,
            display_name=cache_name
        )
    )
    print(f"[Cache] Cache created: {cache.name}  (expires: {cache.expire_time})")
    return cache
