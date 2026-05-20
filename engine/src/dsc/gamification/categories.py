"""Map CWE / rule-id patterns to defense categories.

The end-of-hunt stat card breaks down coverage and findings into five
defense lines: SECRETS, INJECTION, CRYPTO, CONTAINER, MISC. Each line
gets its own stat bar so the player can see at a glance which area is
the weakest and which "next quest" to tackle.

The CWE prefix is the primary signal because rule IDs change but CWE
classification is stable. Misc is the explicit fallback so adding a
new rule never silently disappears from the summary.
"""

from __future__ import annotations

from dataclasses import dataclass

from dsc.scanner.models import Finding


@dataclass(frozen=True, slots=True)
class DefenseCategory:
    key: str
    label: str
    quest_name: str
    next_quest_hint: str
    emoji: str  # single ASCII-safe glyph; Rich renders fine on Windows Terminal


SECRETS = DefenseCategory(
    key="secrets",
    label="Secrets Defense",
    quest_name="First Blood",
    next_quest_hint="Find committed credentials before attackers do.",
    emoji="*",
)
INJECTION = DefenseCategory(
    key="injection",
    label="Injection Defense",
    quest_name="Injection Hunter",
    next_quest_hint="Clear the classic web-app traps: SQLi, XSS, command and path injection.",
    emoji="+",
)
CRYPTO = DefenseCategory(
    key="crypto",
    label="Crypto Defense",
    quest_name="Crypto Clean-up",
    next_quest_hint="Retire risky primitives and unsafe channels.",
    emoji="#",
)
CONTAINER = DefenseCategory(
    key="container",
    label="Container Defense",
    quest_name="Container Guard",
    next_quest_hint="Harden Dockerfile and Kubernetes config before it ships.",
    emoji="@",
)
MISC = DefenseCategory(
    key="misc",
    label="Misc Defense",
    quest_name="Field Patrol",
    next_quest_hint="Sweep up the long tail: deserialization, race conditions, error handling.",
    emoji="~",
)

ALL_CATEGORIES: tuple[DefenseCategory, ...] = (SECRETS, INJECTION, CRYPTO, CONTAINER, MISC)


# CWE → category. Conservative buckets: when in doubt we drop into MISC
# rather than miscategorize. Order matters only in `classify_finding`'s
# fallback heuristics; this dict is just a lookup.
_CWE_TO_CATEGORY: dict[str, DefenseCategory] = {
    # Secrets / credential exposure.
    "CWE-798": SECRETS,  # hardcoded credentials
    "CWE-259": SECRETS,  # hardcoded password
    "CWE-321": SECRETS,  # hardcoded cryptographic key
    "CWE-200": SECRETS,  # information exposure
    "CWE-532": SECRETS,  # sensitive info in log
    # Injection family.
    "CWE-79": INJECTION,   # XSS
    "CWE-89": INJECTION,   # SQL injection
    "CWE-78": INJECTION,   # OS command injection
    "CWE-77": INJECTION,   # command injection (generic)
    "CWE-90": INJECTION,   # LDAP injection
    "CWE-91": INJECTION,   # XML injection
    "CWE-94": INJECTION,   # code injection
    "CWE-95": INJECTION,   # eval injection
    "CWE-22": INJECTION,   # path traversal
    "CWE-23": INJECTION,   # relative path traversal
    "CWE-36": INJECTION,   # absolute path traversal
    "CWE-117": INJECTION,  # improper output neutralization for logs
    "CWE-611": INJECTION,  # XXE
    "CWE-918": INJECTION,  # SSRF
    "CWE-643": INJECTION,  # XPath injection
    "CWE-1336": INJECTION, # template injection
    # Crypto / TLS / hashing.
    "CWE-327": CRYPTO,  # broken/risky crypto
    "CWE-328": CRYPTO,  # weak hash
    "CWE-326": CRYPTO,  # inadequate key strength
    "CWE-330": CRYPTO,  # insufficiently random values
    "CWE-338": CRYPTO,  # weak PRNG
    "CWE-310": CRYPTO,  # cryptographic issues (parent)
    "CWE-319": CRYPTO,  # cleartext transmission
    "CWE-295": CRYPTO,  # improper certificate validation
    "CWE-296": CRYPTO,  # improper following of cert chain
    "CWE-297": CRYPTO,  # improper validation of host-specific cert
    "CWE-916": CRYPTO,  # password hash without computational effort
    # Container / deployment / config.
    "CWE-250": CONTAINER,  # execution with unnecessary privileges
    "CWE-732": CONTAINER,  # incorrect permission assignment
    "CWE-276": CONTAINER,  # incorrect default permissions
    "CWE-668": CONTAINER,  # exposure of resource to wrong sphere
    "CWE-269": CONTAINER,  # improper privilege management
    "CWE-1004": CONTAINER, # sensitive cookie without httponly
}


def _normalize_cwe(raw: str) -> str:
    text = (raw or "").strip().upper()
    if not text:
        return ""
    if not text.startswith("CWE-"):
        if text.startswith("CWE"):
            text = "CWE-" + text[3:].lstrip("-")
        elif text.isdigit():
            text = "CWE-" + text
    return text


def classify_finding(finding: Finding) -> DefenseCategory:
    cwe = _normalize_cwe(finding.cwe)
    cat = _CWE_TO_CATEGORY.get(cwe)
    if cat is not None:
        return cat

    # Rule-id fallback for the curated public rulepacks. The IDs use the
    # form `deva.cwe-79.javascript-xss`, so the CWE has usually already
    # matched above. This branch catches rules whose `cwe` field is empty
    # or non-standard but whose name still telegraphs the family.
    rid = (finding.rule_id or "").lower()
    if any(token in rid for token in ("secret", "credential", "password", "apikey", "api-key", "token")):
        return SECRETS
    if any(token in rid for token in ("xss", "sqli", "sql-injection", "command-injection", "path-traversal", "ssrf", "xxe")):
        return INJECTION
    if any(token in rid for token in ("md5", "sha1", "weak-cipher", "weak-hash", "tls", "http-clear", "cleartext", "ssl-insecure")):
        return CRYPTO
    if any(token in rid for token in ("docker", "kubernetes", "k8s", "container", "privileged")):
        return CONTAINER
    return MISC
