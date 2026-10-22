# Zarma Store Step 1 — Network and Python Environment Report

Date: 2026-10-19 (Asia/Karachi)

## Scope

This report covers backend dependency installation diagnostics only. No files under
`frontend/` or `n8n-workflows/` were changed, and no firewall rule or security setting was
modified.

## Result

**BLOCKED by the current Codex execution network policy.** The project has a valid Python
environment and trusted PyPI metadata is reachable through the authorized web mechanism, but
the local terminal cannot establish HTTPS connections to PyPI package hosts. FastAPI, Uvicorn,
and Pytest therefore remain unavailable in `backend/.venv`.

## Network evidence

### DNS and routing

- `pypi.org` resolves successfully to Fastly IPv4 addresses.
- `files.pythonhosted.org` resolves successfully through its Fastly CNAME.
- A default IPv4 route exists through `192.168.100.1`.
- ICMP to `pypi.org` succeeded in approximately 45 ms.

### HTTPS comparison

Local PowerShell/curl results from the same execution context:

| Host | Result |
|---|---|
| `pypi.org:443` | TCP/HTTPS timeout; curl exit 28, HTTP 000 |
| `files.pythonhosted.org:443` | TCP/HTTPS timeout; curl exit 28, HTTP 000 |
| `orhpssosozwtwynlixgj.supabase.co:443` | Connection succeeds; unauthenticated request returns HTTP 401 |
| `api.openai.com:443` | Connection succeeds; unauthenticated request returns HTTP 401 |

This demonstrates that the local context has selective egress: PyPI package hosts are unreachable,
while the existing Supabase and OpenAI endpoints are reachable. The failure is not a generic DNS
failure, TLS-certificate error, HTTP 403/404/429, or package-version-not-found response.

### Proxy, pip, and firewall

- No `HTTP_PROXY`, `HTTPS_PROXY`, or `ALL_PROXY` variables are configured.
- WinHTTP reports direct access; Windows Internet Settings proxy is disabled.
- No global, site, or user pip configuration files exist.
- Pip is configured to use the official PyPI index from the project command.
- An enabled rule named `codex_sandbox_offline_block_outbound` exists in the local persistent
  firewall store with `Direction=Outbound`, `Action=Block`, `Profile=Any`, `Program=Any`,
  `Service=Any`, and all remote addresses/ports.
- The rule was not disabled or changed. Because Supabase/OpenAI connections succeed from this
  context, the evidence does not justify claiming that every outbound connection on the entire
  Windows computer is blocked. It is consistent with a Codex sandbox/egress policy or an
  allowlist layered over the local execution environment.

## Python environment

- Installed interpreter: Python 3.14.5 only
- `py -0p`: only Python 3.14.5
- Python 3.12/3.13: not installed
- System pip: 26.1.1
- Virtual environment: `backend/.venv`, Python 3.14.5
- `fastapi` import: unavailable
- `uvicorn` import: unavailable
- `pytest` import: unavailable
- Pip cache: no locally built wheels cached
- No `uv`, `conda`, `mamba`, `choco`, or `scoop` executable/cache was found; no usable
  alternate package source was available.
- VS Code command is installed (`code.cmd`), but this terminal exposes no separate VS Code
  proxy or package-index environment variables.

The pinned FastAPI release exists on official PyPI, but local installation cannot reach its
index or file host. Python 3.14 compatibility for the complete pinned dependency set remains
unverified; no package version was silently changed.

## Exact installation/test results

- `pip install -r requirements.txt`: could not retrieve package versions because the index path
  timed out.
- Direct PyPI probe: timeout after 5–20 seconds; curl exit code 28, HTTP 000.
- A direct pip attempt consequently ended with `ERROR: Could not find a version that satisfies
  the requirement fastapi==0.115.6` and `No matching distribution found`; this message is not
  treated as proof that the package is absent because the index connection had already timed out.
- `py -m compileall -q app tests`: passed.
- Commission checks: passed.
- `backend/.venv -m pytest -q`: blocked with `No module named pytest`.
- FastAPI/Uvicorn startup: blocked because imports are unavailable.
- Supabase REST catalog check: HTTP 200 using the existing publishable configuration; no secret
  key was printed.

## Host versus sandbox conclusion

The local terminal is operating under an execution-level egress restriction that selectively
prevents package-host access. The authorized web mechanism can read official PyPI metadata, so
PyPI itself is online; that mechanism cannot install wheel files into the local Windows virtual
environment. This task cannot safely override or remove the firewall/sandbox restriction.

Official [OpenAI sandbox guidance](https://learn.chatgpt.com/docs/sandboxing) states that local
commands inherit sandbox network boundaries and that network access is controlled separately from
approvals. Where available, the supported user-controlled resolution is to enable public internet
access for the execution environment or use the desktop permissions control with an appropriate
network-enabled profile. A managed policy may still override that setting.

## Recommended authorized resolution

Enable the approved public-internet/network-access setting for this Codex execution environment,
or run the same project in an authorized environment that permits outbound HTTPS to:

- `pypi.org`
- `files.pythonhosted.org`

Do not disable Windows Defender, remove the firewall rule, bypass TLS verification, or use an
untrusted package mirror.

## Step 1 success status

Not achieved: a trusted local dependency source is not available, and FastAPI/Uvicorn/Pytest
imports cannot be verified. Offline source compilation and Supabase connectivity checks passed.
