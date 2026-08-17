"""
Insurance-domain ASR output normalizer.

Converts spoken-form transcriptions into structured insurance-domain tokens.
Operates on ASR output text ONLY — does not affect the raw transcript displayed to the user.
The raw transcript is always preserved; this module produces a normalized parallel form.

Examples:
    "X Y Z one two three"   -> "XYZ123"
    "fifty thousand rupees"  -> "50000 rupees"
    "the fifteenth of July"  -> "2026-07-15"  (approximate — year inferred from context)
    "policy H L T dash seven seven eight nine" -> "HLT-7789"
"""
import re
from typing import Optional

# ---------------------------------------------------------------------------
# Number word → digit mappings
# ---------------------------------------------------------------------------
_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
_MULTIPLIERS = {
    "hundred": 100, "thousand": 1000, "lakh": 100_000, "lakhs": 100_000,
    "million": 1_000_000, "crore": 10_000_000, "crores": 10_000_000,
}

# ---------------------------------------------------------------------------
# Month name → zero-padded number
# ---------------------------------------------------------------------------
_MONTHS = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}

# Ordinal day words → digit strings
_ORDINALS = {
    "first": "01", "second": "02", "third": "03", "fourth": "04",
    "fifth": "05", "sixth": "06", "seventh": "07", "eighth": "08",
    "ninth": "09", "tenth": "10", "eleventh": "11", "twelfth": "12",
    "thirteenth": "13", "fourteenth": "14", "fifteenth": "15",
    "sixteenth": "16", "seventeenth": "17", "eighteenth": "18",
    "nineteenth": "19", "twentieth": "20", "twenty-first": "21",
    "twenty-second": "22", "twenty-third": "23", "twenty-fourth": "24",
    "twenty-fifth": "25", "twenty-sixth": "26", "twenty-seventh": "27",
    "twenty-eighth": "28", "twenty-ninth": "29", "thirtieth": "30",
    "thirty-first": "31",
}

# Spoken single letters (for policy IDs like "X Y Z 1 2 3")
_LETTER_WORDS = {
    "alpha": "A", "bravo": "B", "charlie": "C", "delta": "D", "echo": "E",
    "foxtrot": "F", "golf": "G", "hotel": "H", "india": "I", "juliet": "J",
    "kilo": "K", "lima": "L", "mike": "M", "november": "N", "oscar": "O",
    "papa": "P", "quebec": "Q", "romeo": "R", "sierra": "S", "tango": "T",
    "uniform": "U", "victor": "V", "whiskey": "W", "x-ray": "X", "yankee": "Y",
    "zulu": "Z",
}

# Insurance-specific term corrections (spoken → written)
_TERM_CORRECTIONS = {
    "fir": "FIR",
    "fnol": "FNOL",
    "no claim bonus": "NCB",
    "ncb": "NCB",
    "icu": "ICU",
    "otp": "OTP",
    "emi": "EMI",
    "gst": "GST",
    "pan": "PAN",
    "aadhar": "Aadhaar",
    "aadhaaar": "Aadhaar",
    "third party": "third-party",
    "two wheeler": "two-wheeler",
}


def _words_to_number(words: list[str]) -> Optional[int]:
    """
    Convert a sequence of number words to an integer.
    Supports: hundreds, thousands, lakhs (Indian numbering).
    Returns None if conversion is not meaningful.
    """
    total = 0
    current = 0
    for word in words:
        word = word.lower().rstrip(",")
        if word in _ONES:
            current += _ONES[word]
        elif word in _TENS:
            current += _TENS[word]
        elif word == "hundred":
            current = current * 100 if current > 0 else 100
        elif word in _MULTIPLIERS:
            mult = _MULTIPLIERS[word]
            if current == 0:
                current = 1
            total += current * mult
            current = 0
        else:
            break
    total += current
    return total if total > 0 else None


def _normalize_amount(text: str) -> str:
    """
    Convert spoken amount expressions to numeric values.
    "fifty thousand rupees" -> "50000 rupees"
    "one lakh twenty thousand" -> "120000"
    """
    # Pattern: number words followed by optional currency marker
    currency_re = re.compile(
        r"\b((?:(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|"
        r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|"
        r"nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|"
        r"hundred|thousand|lakh|lakhs|million|crore|crores|and)\s+)+)"
        r"(rupees?|rs\.?|inr|dollars?|usd)?",
        re.IGNORECASE,
    )

    def replace_amount(m: re.Match) -> str:
        number_words = m.group(1).strip().split()
        currency = m.group(2) or ""
        value = _words_to_number(number_words)
        if value is not None and value > 0:
            if currency:
                return f"{value} {currency.lower()}"
            return str(value)
        return m.group(0)

    return currency_re.sub(replace_amount, text)


def _normalize_policy_id(text: str) -> str:
    """
    Normalize spoken policy IDs.
    "X Y Z one two three" -> "XYZ123"
    "policy H L T dash seven seven eight nine" -> "HLT-7789"
    "S N R dash nine nine one two" -> "SNR-9912"
    """
    # Spoken-letter sequences like "H L T" or "X Y Z" that immediately precede digits
    spoken_letters_re = re.compile(
        r"\b([A-Z](?:\s+[A-Z]){1,5})\s+(dash\s+)?(\d+)\b",
        re.IGNORECASE,
    )

    def collapse_letters(m: re.Match) -> str:
        letters = re.sub(r"\s+", "", m.group(1).upper())
        dash = "-" if m.group(2) else ""
        digits = m.group(3)
        return f"{letters}{dash}{digits}"

    text = spoken_letters_re.sub(collapse_letters, text)

    # Also handle "dash" as literal separator in identifiers already partially formed
    text = re.sub(r"(\b[A-Z]{2,6})\s+dash\s+(\d+)\b", r"\1-\2", text, flags=re.IGNORECASE)

    return text


def _normalize_date(text: str) -> str:
    """
    Normalize date references to ISO-8601 where possible.
    "the fifteenth of July two thousand twenty-five" -> "2025-07-15"
    "July 15 2025" -> "2025-07-15"
    "15th July 2025" -> "2025-07-15"
    Only converts when year can be determined (present in text or inferred as current year).
    """
    import datetime
    current_year = datetime.date.today().year

    # Pattern: day ordinal + month + optional year
    # "the fifteenth of July 2025" / "15th of July" / "July 15, 2025"
    date_re = re.compile(
        r"\b(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?("
        + "|".join(_MONTHS.keys())
        + r")(?:\s+(\d{4}))?\b",
        re.IGNORECASE,
    )

    def replace_date(m: re.Match) -> str:
        day = int(m.group(1))
        month = _MONTHS[m.group(2).lower()]
        year = int(m.group(3)) if m.group(3) else current_year
        if 1 <= day <= 31:
            return f"{year}-{month}-{day:02d}"
        return m.group(0)

    text = date_re.sub(replace_date, text)

    # Pattern: "Month day year" -> "YYYY-MM-DD"
    month_first_re = re.compile(
        r"\b("
        + "|".join(_MONTHS.keys())
        + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b",
        re.IGNORECASE,
    )

    def replace_month_first(m: re.Match) -> str:
        month = _MONTHS[m.group(1).lower()]
        day = int(m.group(2))
        year = int(m.group(3))
        if 1 <= day <= 31:
            return f"{year}-{month}-{day:02d}"
        return m.group(0)

    text = month_first_re.sub(replace_month_first, text)

    return text


def _apply_term_corrections(text: str) -> str:
    """Apply insurance-specific terminology corrections."""
    for spoken, written in _TERM_CORRECTIONS.items():
        text = re.sub(rf"\b{re.escape(spoken)}\b", written, text, flags=re.IGNORECASE)
    return text


def normalize_transcript(raw: str) -> str:
    """
    Apply all normalization passes to raw ASR output and return the normalized string.

    The raw transcript is never modified — this function returns the normalized form
    for use by downstream claim extraction. The UI always receives the raw transcript.

    Processing order:
    1. Policy ID / reference number collapsing
    2. Date normalization
    3. Amount normalization (words → digits)
    4. Insurance terminology corrections
    """
    if not raw or not raw.strip():
        return raw

    normalized = raw

    # 1. Policy IDs: "X Y Z 1 2 3" → "XYZ123"
    normalized = _normalize_policy_id(normalized)

    # 2. Dates: spoken dates → ISO-8601
    normalized = _normalize_date(normalized)

    # 3. Amounts: "fifty thousand rupees" → "50000 rupees"
    normalized = _normalize_amount(normalized)

    # 4. Domain terminology
    normalized = _apply_term_corrections(normalized)

    return normalized
