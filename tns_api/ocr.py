import base64
import json
import mimetypes
import os
from datetime import datetime
import logging
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)

def _image_to_data_url(path):
    mime, _ = mimetypes.guess_type(path)
    if not mime:
        mime = "image/png"
    if not mime.startswith("image/"):
        return None
    with open(path, "rb") as handle:
        encoded = base64.b64encode(handle.read()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _parse_receipt_date(value):
    if not value:
        return None
    cleaned = str(value).strip()
    if "T" in cleaned:
        cleaned = cleaned.split("T", 1)[0]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def _extract_output_text(response):
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") in ("output_text", "text"):
                return content.get("text", "")
    return ""


def run_ocr(path):
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return {
            "raw_text": "",
            "vendor_name": "",
            "receipt_date": None,
            "total_amount": None,
            "tax_amount": None,
            "receipt_number": "",
            "notes": "OpenAI OCR not configured (missing OPENAI_API_KEY).",
        }

    image_url = _image_to_data_url(path)
    if not image_url:
        return {
            "raw_text": "",
            "vendor_name": "",
            "receipt_date": None,
            "total_amount": None,
            "tax_amount": None,
            "receipt_number": "",
            "notes": "Unsupported image format for OCR.",
        }

    model = os.getenv("OPENAI_OCR_MODEL", "gpt-4o-mini")
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "raw_text": {"type": "string"},
            "vendor_name": {"type": "string"},
            "receipt_date": {"type": ["string", "null"]},
            "total_amount": {"type": ["number", "null"]},
            "tax_amount": {"type": ["number", "null"]},
            "receipt_number": {"type": "string"},
            "notes": {"type": "string"},
        },
        "required": [
            "raw_text",
            "vendor_name",
            "receipt_date",
            "total_amount",
            "tax_amount",
            "receipt_number",
            "notes",
        ],
    }

    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "You are an OCR engine for receipts. "
                            "Extract fields from the image. If a field is missing, use null "
                            "for dates/amounts and empty string for text fields. "
                            "Use YYYY-MM-DD for receipt_date when available."
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Extract: vendor_name, receipt_date, total_amount, tax_amount, "
                            "receipt_number, raw_text, notes."
                        ),
                    },
                    {"type": "input_image", "image_url": image_url},
                ],
            },
        ],
        "text": {"format": {"type": "json_schema", "name": "receipt_ocr", "schema": schema, "strict": True}},
    }

    request = urlrequest.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        logger.info("Starting OpenAI OCR request with model=%s path=%s", model, path)
        with urlrequest.urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8")
        logger.info("OpenAI OCR request completed with status=%s path=%s", response.status, path)
    except HTTPError as error:
        logger.warning("OpenAI OCR request failed HTTP %s path=%s", error.code, path)
        return {
            "raw_text": "",
            "vendor_name": "",
            "receipt_date": None,
            "total_amount": None,
            "tax_amount": None,
            "receipt_number": "",
            "notes": f"OpenAI OCR failed: HTTP {error.code}",
        }
    except URLError:
        logger.warning("OpenAI OCR request failed network error path=%s", path)
        return {
            "raw_text": "",
            "vendor_name": "",
            "receipt_date": None,
            "total_amount": None,
            "tax_amount": None,
            "receipt_number": "",
            "notes": "OpenAI OCR failed: network error.",
        }

    try:
        data = json.loads(body)
        output_text = _extract_output_text(data)
        result = json.loads(output_text) if output_text else {}
    except (ValueError, TypeError):
        logger.warning("OpenAI OCR returned invalid response path=%s", path)
        return {
            "raw_text": "",
            "vendor_name": "",
            "receipt_date": None,
            "total_amount": None,
            "tax_amount": None,
            "receipt_number": "",
            "notes": "OpenAI OCR failed: invalid response.",
        }

    return {
        "raw_text": str(result.get("raw_text") or ""),
        "vendor_name": str(result.get("vendor_name") or ""),
        "receipt_date": _parse_receipt_date(result.get("receipt_date")),
        "total_amount": result.get("total_amount"),
        "tax_amount": result.get("tax_amount"),
        "receipt_number": str(result.get("receipt_number") or ""),
        "notes": str(result.get("notes") or ""),
    }
