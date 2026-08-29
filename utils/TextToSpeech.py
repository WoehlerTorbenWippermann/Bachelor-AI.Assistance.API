import pathlib
import re

try:
    from gtts import gTTS
except ImportError:
    raise ImportError("gTTS is not installed. Run: pip install gtts")


def clean_for_speech(text):
    """Strip Markdown formatting so the spoken text sounds natural
    (e.g. '**WARNING:** unplug the cable' -> 'WARNING: unplug the cable')."""
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)   # **bold** -> bold
    text = re.sub(r'\*(.*?)\*',     r'\1', text)   # *italic* -> italic
    text = re.sub(r'^[\*\-]\s+',    '',    text, flags=re.MULTILINE)  # bullet points
    text = re.sub(r'\n{2,}',        ' ',   text)   # blank lines
    text = re.sub(r'\n',            ' ',   text)   # single line breaks
    text = re.sub(r'\s{2,}',        ' ',   text)   # repeated spaces
    return text.strip()


def text_to_mp3(text, output_path, lang="en"):
    """Convert text (may contain Markdown) into an MP3 file at output_path.
    Returns the output path, or None if there is nothing to speak."""
    clean_text = clean_for_speech(text)
    if not clean_text:
        print("[TTS] Nothing to speak.")
        return None

    output_path = pathlib.Path(output_path)
    tts = gTTS(text=clean_text, lang=lang, slow=False)
    tts.save(str(output_path))

    print(f"[TTS] Saved: {output_path}")
    return output_path
