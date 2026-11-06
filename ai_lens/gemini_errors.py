"""Preserve provider error evidence; do not equate access errors with quota."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import math
import re


def error_details(body):
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return {"message": str(body)}
    if not isinstance(data, dict):
        return {"message": str(body)}
    error = data.get("error", data)
    if not isinstance(error, dict):
        return {"message": str(error)}
    return error


def retry_delay(body, header=None):
    """Honor RetryInfo/header; never shorten a provider's delay to 35 seconds."""
    values = []
    if header:
        try:
            values.append(float(header))
        except (ValueError, TypeError):
            try:
                when = parsedate_to_datetime(header)
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                values.append((when - datetime.now(timezone.utc)).total_seconds())
            except (ValueError, TypeError, OverflowError):
                pass
    error = error_details(body)
    if isinstance(error.get("retry_after"), (str, int, float)):
        try:
            values.append(float(error["retry_after"]))
        except (ValueError, OverflowError):
            pass
    details = error.get("details", [])
    if isinstance(details, list):
        for item in details:
            if isinstance(item, dict):
                match = re.fullmatch(r"(\d+(?:\.\d+)?)s", str(item.get("retryDelay", "")))
                if match:
                    values.append(float(match[1]))
    for match in re.finditer(r"retry\s+in\s+(\d+(?:\.\d+)?)\s*s", str(body), re.I):
        values.append(float(match[1]))
    values = [v for v in values if math.isfinite(v) and v >= 0]
    return max(values) if values else None


def retain_error(raw_body, retry_after=None):
    """Keep structured details when crossing the existing string-based API boundary."""
    error = error_details(raw_body)
    delay = retry_delay(raw_body, retry_after)
    if delay is not None:
        error = {**error, "retry_after": delay}
    return json.dumps({"error": error}, ensure_ascii=False)


def format_error(status, body, model, language="cs"):
    cs = language in ("cs", "sk")
    error = error_details(body)
    detail = str(error.get("message", body))[:450]
    # Some codes describe a local incomplete stream/deadline rather than
    # an HTTP response. Do not fabricate an HTTP status in the UI.
    lead = f"Gemini · {model} · {'kód' if cs else 'code'} {status}"
    if status == 429 and error.get("local_cooldown") is True:
        delay = math.ceil(retry_delay(body) or 0)
        text = (f"Lokální ochranná pauza po předchozí chybě 429: ještě {delay} s. Nový API požadavek nebyl odeslán."
                if cs else f"Local cooldown after a previous 429: {delay} s remaining. No new API request sent.")
    elif status == 429:
        delay = retry_delay(body)
        text = ("API omezilo tento požadavek (kvóta nebo rychlost). Nebyl automaticky opakován."
                if cs else "API quota/rate limit for this request. It was not automatically retried.")
        if delay is not None:
            text += (f" API uvádí opakování nejdříve za {math.ceil(delay)} s."
                     if cs else f" API suggests retrying no earlier than {math.ceil(delay)} s.")
        else:
            text += (" Čas obnovení nebyl uveden; zkontroluj limit projektu v AI Studio."
                     if cs else "No retry time supplied; check the project's limits in AI Studio.")
    elif status in (401, 403) or any(
            phrase in detail.lower() for phrase in ("api_key_invalid", "api key not valid", "invalid api key")):
        text = ("Chyba autentizace nebo oprávnění. Není to potvrzení vyčerpané kvóty."
                if cs else "Authentication/permission error, not proof of exhausted quota.")
    elif status == 404:
        text = "Vybraný endpoint/model nebyl nalezen." if cs else "Selected endpoint/model was not found."
    elif status == 400:
        text = ("API odmítlo parametry požadavku; High nebylo sníženo."
                if cs else "API rejected request parameters; High was not downgraded.")
    elif status in (204, 206):
        text = ("Model nevrátil dokončenou odpověď. Další generování nebylo automaticky spuštěno."
                if cs else "No complete answer returned. Another generation was not automatically started.")
    elif status == 408:
        text = "Vypršel časový limit." if cs else "Request timed out."
    elif status == 422:
        text = "Výpočetní odpověď nebyla dokončena nebo ověřena." if cs else "Calculation did not complete or pass checks."
    else:
        text = ("Požadavek selhal; nebyly spuštěny další pokusy na jiných modelech."
                if cs else "Request failed; no additional attempts on other models were made.")
    return f"{lead}\n{text}\n{detail}"
