import re
from datetime import datetime

try:
    from PIL import Image, ImageOps, ImageFilter
except Exception:
    Image = None

try:
    import pytesseract
except Exception:
    pytesseract = None


def _preprocess_image(path):
    if Image is None:
        return None
    image = Image.open(path)
    image = ImageOps.exif_transpose(image)
    image = image.convert("L")
    image = image.filter(ImageFilter.MedianFilter(size=3))
    image = ImageOps.autocontrast(image)
    return image


def _extract_amounts(text):
    numbers = re.findall(r"(?:\d+[.,]\d{2})", text)
    amounts = []
    for value in numbers:
        normalized = value.replace(",", ".")
        try:
            amounts.append(float(normalized))
        except ValueError:
            continue
    amounts.sort(reverse=True)
    total = amounts[0] if amounts else None
    tax = amounts[1] if len(amounts) > 1 else None
    return total, tax


def _extract_date(text):
    patterns = [
        r"\b(\d{4}[-/]\d{2}[-/]\d{2})\b",
        r"\b(\d{2}[-/]\d{2}[-/]\d{4})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            value = match.group(1)
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"):
                try:
                    return datetime.strptime(value, fmt).date()
                except ValueError:
                    continue
    return None


def _extract_vendor(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[0][:255]


def _extract_receipt_number(text):
    match = re.search(r"(receipt|invoice|ref|no\.?)\s*[:#]?\s*([A-Za-z0-9-]+)", text, re.I)
    if match:
        return match.group(2)[:100]
    return ""


def run_ocr(path):
    if pytesseract is None or Image is None:
        return {
            "raw_text": "",
            "vendor_name": "",
            "receipt_date": None,
            "total_amount": None,
            "tax_amount": None,
            "receipt_number": "",
            "notes": "OCR engine unavailable",
        }

    image = _preprocess_image(path)
    if image is None:
        return {
            "raw_text": "",
            "vendor_name": "",
            "receipt_date": None,
            "total_amount": None,
            "tax_amount": None,
            "receipt_number": "",
            "notes": "Image processing unavailable",
        }

    raw_text = pytesseract.image_to_string(image)
    total_amount, tax_amount = _extract_amounts(raw_text)
    return {
        "raw_text": raw_text,
        "vendor_name": _extract_vendor(raw_text),
        "receipt_date": _extract_date(raw_text),
        "total_amount": total_amount,
        "tax_amount": tax_amount,
        "receipt_number": _extract_receipt_number(raw_text),
        "notes": "",
    }
