"""Phase08 privacy-preserving Android smoke diagnostic summaries.

No raw logcat or dumpsys enters a downloadable CI artifact or GitHub job log.
Even lines containing legitimate WLRE readiness markers may append credentials,
so copy only known fixed marker tokens and aggregate counts. This reduces
diagnostic fidelity deliberately. Raw logs must be collected locally with
explicit consent if a deeper device investigation is later required.
"""
from collections import Counter
import re

READINESS = (
    "WLRE_ANDROID_UI_READY",
    "WLRE_ANDROID_SERVICE_CONNECTED",
    "WLRE_ANDROID_KEYSTORE_READY",
)
ERROR_MARKER = "WLRE_ANDROID_STARTUP_ERROR"
KNOWN_STAGES = frozenset(("A01", "A02", "A03", "A05", "A07"))
KNOWN_ERRORS = frozenset((
    "RuntimeError", "ValueError", "TypeError", "OSError", "KeyError",
    "ImportError", "AttributeError", "PermissionError", "TimeoutError",
))
ERROR_PATTERN = re.compile(r"\bWLRE_ANDROID_STARTUP_ERROR\s+([A-Z]\d{2})\s+([A-Za-z]+)\b")


def summarize_logcat(raw):
    if raw.startswith("[diagnostic unavailable:"):
        return "Android logcat diagnostic unavailable (ADB failure)\n"
    fallback = "full logcat unavailable" in raw.lower()
    present = [marker for marker in READINESS if marker in raw]
    warnings = Counter()
    errors = set()
    for line in raw.splitlines():
        lower = line.lower()
        if "fatal exception" in lower:
            warnings["android_fatal_exception"] += 1
        if "androidruntime" in lower:
            warnings["androidruntime_entries"] += 1
        if "traceback (most recent call last)" in lower:
            warnings["python_tracebacks"] += 1
        if "linker" in lower and ("error" in lower or "failed" in lower):
            warnings["linker_errors"] += 1
        for match in ERROR_PATTERN.finditer(line):
            stage, error = match.groups()
            # Fixed vocabulary only. Never include arbitrary log text, module
            # names, Python repr, bearer tokens, files, or device IDs.
            errors.add((stage if stage in KNOWN_STAGES else "UNKNOWN",
                        error if error in KNOWN_ERRORS else "Other"))
    lines = [
        "Android logcat sanitized diagnostic summary (raw lines omitted)",
        "fallback_last_300: " + str(fallback).lower(),
        "readiness_markers: " + (",".join(present) if present else "none"),
    ]
    for key in sorted(warnings):
        lines.append(key + ": " + str(warnings[key]))
    for stage, error in sorted(errors):
        lines.append(ERROR_MARKER + " " + stage + " " + error)
    return "\n".join(lines) + "\n"


def summarize_services(raw):
    if raw.startswith("[diagnostic unavailable:"):
        return "Android service dump diagnostic unavailable (ADB failure)\n"
    # No service names/intents/extras/UIDs are copied from dumpsys.
    return "Android service dump collected; raw contents omitted for privacy\n"
