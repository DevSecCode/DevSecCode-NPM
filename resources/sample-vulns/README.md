# Sample vulnerabilities

Six small files, each demonstrating a common vulnerability class. Open this folder, run **Deva: Scan Workspace**, and see findings appear as red squiggles on the lines marked `BAD:`.

| File | CWE | Class |
|---|---|---|
| `sql_injection.py` | [CWE-89](https://cwe.mitre.org/data/definitions/89.html) | SQL Injection |
| `dom_xss.js` | [CWE-79](https://cwe.mitre.org/data/definitions/79.html) | Cross-site Scripting |
| `command_injection.py` | [CWE-78](https://cwe.mitre.org/data/definitions/78.html) | OS Command Injection |
| `path_traversal.go` | [CWE-22](https://cwe.mitre.org/data/definitions/22.html) | Path Traversal |
| `hardcoded_secrets.py` | [CWE-798](https://cwe.mitre.org/data/definitions/798.html) | Hardcoded Credentials |
| `insecure_crypto.py` | [CWE-327](https://cwe.mitre.org/data/definitions/327.html) | Broken/Risky Crypto |

Each file pairs a vulnerable function with a safe variant so the contrast is visible. Click the lightbulb on any finding to generate an AI-assisted fix in your active LLM mode.

These files are read-only; they live inside the extension install. To experiment with fixes you can apply, copy them into a workspace of your own.
