import re

SENSITIVE_PATTERNS = [
    (r'sk-[a-zA-Z0-9]{32,}', 'OpenAI API Key'),
    (r'sk-ant-[a-zA-Z0-9_-]{32,}', 'Anthropic API Key'),
    (r'Bearer\s+[A-Za-z0-9\-._~+/]+=*', 'Bearer Token'),
    (r'-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----', 'Private Key'),
    (r'[A-Za-z0-9+/]{40,}={0,2}', 'High-Entropy String'),
]


def sanitize_for_llm(text: str) -> str:
    for pattern, label in SENSITIVE_PATTERNS:
        text = re.sub(pattern, f'[REDACTED: {label}]', text)
    return text
