import re

# Evidence is a review aid; original bytes remain only in the isolated artifact store.
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?(?:-----END [^-]*PRIVATE KEY-----|$)"),
    re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,}|AKIA[A-Z0-9]{16})\b"),
    re.compile(r"(?i)(?:[\"']?(?:api[_-]?key|(?:access[_-]?)?token|(?:client[_-]?)?secret|password|authorization)[\"']?\s*[:=]\s*)[\"']?[^\s\"',;}{]{6,}[\"']?"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"https?://[^\s/:]+:[^\s/@]+@[^\s]+", re.I),
]


def redact(value: str, limit: int = 500) -> str:
    for pattern in SECRET_PATTERNS:
        value = pattern.sub("[REDACTED]", value)
    return value[:limit]


def redact_object(value):
    if isinstance(value, str):
        return redact(value, 4096)
    if isinstance(value, dict):
        return {redact(str(key), 128): redact_object(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_object(item) for item in value]
    return value
