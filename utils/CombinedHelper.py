import json
import re
from config import COMBINED_PROMPT


def build_combined_api_prompt(question, language_instruction=""):
    """Fill COMBINED_PROMPT with the technician question and language
    instruction (single call returning both answer and boxes)."""
    return COMBINED_PROMPT.format(question=question, language_instruction=language_instruction)


def parse_combined(text):
    """Extract 'answer' and 'boxes' from the model response.
    Returns (answer, boxes); on a parse failure returns (raw_text, [])."""
    clean = re.sub(r'```(?:json)?', '', text).strip().rstrip('`').strip()

    # Attempt 1: the whole string is the JSON object
    try:
        parsed = json.loads(clean)
        if isinstance(parsed, dict):
            return parsed.get("answer", ""), [b for b in parsed.get("boxes", []) if isinstance(b, dict)]
    except json.JSONDecodeError:
        pass

    match = re.search(r'\{.*\}', clean, re.DOTALL)

    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, dict):
                return parsed.get("answer", ""), [b for b in parsed.get("boxes", []) if isinstance(b, dict)]
        except json.JSONDecodeError:
            pass

    return text.strip(), []
