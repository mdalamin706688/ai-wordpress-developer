import re

_SECRET_PATTERNS = (
    re.compile(r"(Authorization:\s*Bearer\s+)(\S+)", re.I),
    re.compile(r"(Authorization:\s*Basic\s+)(\S+)", re.I),
    re.compile(r"(api[_-]?key[\"']?\s*[:=]\s*[\"']?)([^\s\"']+)", re.I),
    re.compile(r"(sk-[A-Za-z0-9]+)"),
)


def redact(text: str) -> str:
    if not text:
        return text
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub(lambda m: (m.group(1) if m.lastindex and m.lastindex >= 1 else "") + "[REDACTED]", out)
    return out
