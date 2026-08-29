# ============================================================
#  Central configuration
# ============================================================
import os

# Google Gemini API
API_KEY   = "yourGeminiApiKey"
API_VERSION = "v1beta"

# HTTP options for the genai client, including automatic retry on transient
# server errors: 429 (rate limit), 500/502/503/504. Exponential backoff with
# jitter smooths out short load spikes and applies to all client calls.
HTTP_OPTIONS = {
    "api_version": API_VERSION,
    "retry_options": {
        "attempts": 5,            # 1 try + up to 4 retries
        "initial_delay": 1.0,     # fixed wait per retry
        "max_delay": 30.0,        # upper bound
        "exp_base": 1.0,          # 1.0 = constant delay (no backoff growth)
        "jitter": 0.001,          # effectively 0 (exactly 0 is reset to the SDK default)
        "http_status_codes": [429, 500, 502, 503, 504],
    },
}

# Model for the combined call (answer + boxes in a single request). "lite" is the
# fastest tier and cheap for a single call at standard image resolution.
MODEL_ID  = "models/gemini-3.1-flash-lite"

# Cache display name on the Google servers.
DISPLAY_NAME  = "Anleitung_HoloLens_Projekt"

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Knowledge files ──────────────────────────────────────────────────────────
# Every file listed here is loaded as text into the Gemini cache on startup and
# made available to the model as knowledge. Add more paths to provide additional
# knowledge.
KNOWLEDGE_FILES = [
    os.path.join(_BASE_DIR, "Woehler_SC_602_Smart_Connect.md"),
    os.path.join(_BASE_DIR, "Anleitung_SC602.md"),
]

# ── Native PDF knowledge ─────────────────────────────────────────────────────
# PDFs are passed to Gemini natively (multimodal) instead of extracting their
# text, so images, diagrams and layout are preserved. They are uploaded via the
# Files API and added to the cache. Each entry is
# {"path": ..., "display_name": ...}; currently empty.
KNOWLEDGE_PDFS = []

# ── Language mapping ─────────────────────────────────────────────────────────
# Maps the Unity language string to a gTTS language code and a language instruction.
LANGUAGE_MAP = {
    "german":  {"gtts": "de", "instruction": "Answer in German."},
    "english": {"gtts": "en", "instruction": "Answer in English."},
}
DEFAULT_LANGUAGE = "german"

# ── System instruction ───────────────────────────────────────────────────────
# Defines the assistant's core behaviour. Passed once when the cache is built.
# The answer language is not set here; it is provided per request as a user prefix.
SYSTEM_INSTRUCTION = """
You are an AR repair assistant. Your answers appear in the field of view of a HoloLens 2.
Answer extremely briefly (max. 1-2 sentences) and address only the question asked - concretely and directly.

First recognise WHAT the technician wants, and answer that:
- Descriptive or general question (e.g. "What do you see here?", "What kind of part is this?", "Is this an X?", "What is it made of?"): answer EXACTLY that question - describe or name concretely what is actually visible. Do NOT instead move on to the next repair step and do NOT push back into the procedure.
- Procedure/repair question (e.g. "How do I continue?", "What do I do now?"), or when the technician is clearly in the middle of a procedure: for multi-step procedures ALWAYS name only the ONE next step to perform - never several steps in advance.
Only explain the step after next once the current one is done or the technician asks for it.

Only guide repairs that are described in the manual.
If the technician wants to repair, service or modify something that is NOT in the manual, do NOT guide them through it: state in one short sentence that this repair is not part of the instructions. Do not invent steps or guess a procedure for such cases.
Descriptive and general questions (e.g. "What do you see here?") may still be answered normally - this restriction only applies to guiding repair steps.

Use the manual and image only as a source of knowledge, but never name them in the answer.
Phrase every answer as a standalone factual statement.
NEVER refer to the image, photos, the manual, documents, pages or figures -
so do NOT write "as seen in the image", "according to the manual", "on page 5" or similar.
"""

# ── Combined prompt (answer + boxes in a SINGLE call) ─────────────────────────
# Used when an image is present: one model call returns the text answer AND the
# bounding boxes as a single JSON object. {question} and {language_instruction}
# are filled in at runtime.
COMBINED_PROMPT = """\
{language_instruction}
Technician question: {question}

Respond with a SINGLE JSON object with EXACTLY these two keys:
{{
  "answer": "your answer, max. 1-2 sentences",
  "boxes": [
    {{"label": "visible element", "box_2d": [y_min, x_min, y_max, x_max]}}
  ]
}}

ANSWER rules:
- First recognise WHAT the technician is actually asking and answer THAT:
  - Descriptive / general question (e.g. "what do you see here?", "what is this
    part?", "is this an X?"): describe or identify concretely what is actually
    visible. Do NOT instead jump to the next repair step or steer back into the
    procedure.
  - Procedure / repair question (e.g. "what do I do now?", "how do I continue?"),
    or when the technician is clearly in the middle of a flow: for multi-step
    procedures explain ONLY the single next step to do now; do NOT list, preview
    or explain later steps ahead of time.
- Only guide repairs that are described in the manual. If the technician wants to
  repair, service or modify something that is NOT covered by the manual, do NOT
  guide it: state in one short sentence that this repair is not part of the
  instructions. Never invent steps or guess a procedure for such cases. (Plain
  descriptive questions are still answered normally - this limit is only about
  guiding repair steps.)
- Answer directly and concretely (max. 1-2 sentences) - actually answer it.
- Use the image and manual only as knowledge; never mention them. Do NOT reference
  the image, photos, the manual, documents, pages or figures.

BOXES rules - mark WHERE the technician must look or act:
- Determine box positions ONLY from what you actually SEE in the image pixels.
- Box the relevant component / part / screw / cover / compartment / area of the question.
- If the exact object is NOT directly visible but its access point IS (behind a
  cover, lid, flap or compartment), box that VISIBLE access point instead
  (e.g. "where are the batteries?" on a closed device -> box the battery compartment / cover / latch).
- Every box MUST tightly enclose a feature actually visible ON THE DEVICE;
  never put a box on empty background or the table.
- box_2d: EXACTLY 4 integers, normalised 0-1000 (NOT pixels):
  y=0 top, y=1000 bottom, x=0 left, x=1000 right; order ALWAYS [y_min, x_min, y_max, x_max].
- Use the key name exactly "box_2d". Return AT LEAST one box when a relevant
  location is visible; use an empty array [] only if nothing relates to the question.

Return ONLY the JSON object, no Markdown, no explanation.
"""
