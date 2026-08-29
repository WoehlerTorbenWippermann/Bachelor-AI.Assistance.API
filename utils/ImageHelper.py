import pathlib
from google.genai import types


def load_image_part(image_path):
    """Load an image as a types.Part. Returns (part, None) on success or
    (None, error_message) if the file does not exist."""

    path = pathlib.Path(image_path)
    if not path.exists():
        return None, f"Image not found: {image_path}"
    
    mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",  ".webp": "image/webp"}
    mime_type = mime_map.get(path.suffix.lower(), "image/jpeg")

    return types.Part.from_bytes(data=path.read_bytes(), mime_type=mime_type), None
