"""
Receipt OCR — core extraction logic.

Usage:
    python main.py path/to/receipt.jpg
"""

import base64
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ---------------------------------------------------------------------------
# OpenRouter client
# ---------------------------------------------------------------------------

_api_key = os.getenv("OPENROUTER_API_KEY")
if not _api_key:
    raise EnvironmentError("OPENROUTER_API_KEY is not set in the environment / .env file.")

_client = OpenAI(
    api_key=_api_key,
    base_url="https://openrouter.ai/api/v1",
)
MODEL = "qwen/qwen2.5-vl-72b-instruct"

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """\
You are an expert at reading receipts written in any language, including Japanese (日本語) and English.

Extract the following information from the receipt image and return it as a single JSON object.
Do not include any explanation, markdown fences, or extra text — only the raw JSON.

Required JSON schema:
{
  "vendor":     "<store or restaurant name>",
  "date":       "<YYYY-MM-DD, or null if not found>",
  "subtotal":   <amount BEFORE tax (税抜金額) as a number, or null>,
  "tax":        <tax amount (消費税) as a number, or null>,
  "total":      <final amount AFTER tax (税込金額 = subtotal + tax) as a number, or null>,
  "gift_card":  <gift card amount applied as a number, or null>,
  "points":     <points redeemed as payment as a number, or null>,
  "currency":   "<ISO 4217 code, e.g. JPY, USD, EUR — infer from context>",
  "line_items": [
    {"description": "<item name in original language>", "amount": <number>}
  ]
}

Rules:
- Keep all text (vendor name, item descriptions) in the original language as printed on the receipt.
- All monetary amounts must be plain numbers (no currency symbols, no commas).
- subtotal is always the amount BEFORE tax. total is always the amount AFTER tax. They must never be equal when tax is non-null and non-zero.
- If subtotal is not printed, calculate it as: subtotal = total - tax.
- If total is not printed, calculate it as: total = subtotal + tax.
- If a field cannot be determined and cannot be calculated, use null rather than an empty string or 0.
- line_items should be an empty list [] if no individual items are visible.
"""

# ---------------------------------------------------------------------------
# Supported MIME types
# ---------------------------------------------------------------------------

_MIME_MAP = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".webp": "image/webp",
    ".gif":  "image/gif",
    ".heic": "image/heic",
    ".heif": "image/heif",
}


def _image_to_base64(image_path: str) -> tuple[str, str]:
    """Read an image file and return (base64_data, mime_type)."""
    path = Path(image_path)
    suffix = path.suffix.lower()
    mime_type = _MIME_MAP.get(suffix)
    if mime_type is None:
        raise ValueError(
            f"Unsupported image format '{suffix}'. "
            f"Supported: {', '.join(_MIME_MAP)}"
        )
    b64 = base64.standard_b64encode(path.read_bytes()).decode()
    return b64, mime_type


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS = ("vendor", "date", "subtotal", "tax", "total", "gift_card", "points", "currency", "line_items")
_NUMERIC_FIELDS  = ("subtotal", "tax", "total", "gift_card", "points")


class ExtractionError(ValueError):
    """Raised when the model response cannot be parsed or fails validation."""


def _validate(data: dict) -> dict:
    """
    Check that required fields exist and numeric fields are numbers (or null).
    Returns the validated dict; raises ExtractionError on failure.
    """
    missing = [f for f in _REQUIRED_FIELDS if f not in data]
    if missing:
        raise ExtractionError(f"Response is missing required fields: {missing}")

    for field in _NUMERIC_FIELDS:
        value = data[field]
        if value is not None and not isinstance(value, (int, float)):
            raise ExtractionError(
                f"Field '{field}' must be a number or null, got {type(value).__name__}: {value!r}"
            )

    # When the receipt only prints the tax-included total, the model returns the
    # same value for both subtotal and total. Correct it by deriving the missing one.
    subtotal, tax, total = data["subtotal"], data["tax"], data["total"]
    if tax:
        if total and subtotal == total:
            data["subtotal"] = round(total - tax, 2)
        elif subtotal and not total:
            data["total"] = round(subtotal + tax, 2)

    if not isinstance(data["line_items"], list):
        raise ExtractionError("'line_items' must be a list.")

    for i, item in enumerate(data["line_items"]):
        if not isinstance(item, dict):
            raise ExtractionError(f"line_items[{i}] is not an object.")
        if "description" not in item or "amount" not in item:
            raise ExtractionError(f"line_items[{i}] missing 'description' or 'amount'.")
        if item["amount"] is not None and not isinstance(item["amount"], (int, float)):
            raise ExtractionError(
                f"line_items[{i}].amount must be a number or null, got {item['amount']!r}"
            )

    return data


# ---------------------------------------------------------------------------
# Main extraction function
# ---------------------------------------------------------------------------

def extract_receipt_data(image_path: str) -> dict:
    """
    Send a receipt image to OpenRouter and return structured data.

    Args:
        image_path: Local path to the receipt image.

    Returns:
        Validated dict matching the extraction schema.

    Raises:
        FileNotFoundError: If the image file does not exist.
        ValueError: If the image format is unsupported.
        ExtractionError: If the model response cannot be parsed or validated.
    """
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    b64_data, mime_type = _image_to_base64(image_path)

    response = _client.chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{b64_data}"},
                    },
                    {
                        "type": "text",
                        "text": EXTRACTION_PROMPT,
                    },
                ],
            }
        ],
    )

    raw_text = response.choices[0].message.content.strip()

    # Strip accidental markdown fences if the model adds them despite the prompt
    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
    raw_text = re.sub(r"\s*```$", "", raw_text)

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"Model returned non-JSON output: {exc}\n---\n{raw_text}") from exc

    return _validate(data)


# ---------------------------------------------------------------------------
# CLI / quick test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_image = sys.argv[1] if len(sys.argv) > 1 else "receipt.jpg"

    print(f"Extracting data from: {test_image}\n")
    try:
        result = extract_receipt_data(test_image)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except FileNotFoundError as e:
        print(f"[Error] {e}")
        sys.exit(1)
    except ExtractionError as e:
        print(f"[Extraction Error] {e}")
        sys.exit(1)
