---
name: domain-check
description: Use when someone asks whether a domain name is taken or available, wants a list of candidate names checked ("is mybrand.com free", "check these domains"), or is brainstorming a company or product name and needs to know which domains can still be registered.
---

# Domain check

Checks whether domain names are registered, from the terminal, with no account, API key or registrar quota. The script in this folder does the lookups; run it, do not retype its logic.

`<skill-dir>` below means the folder this file is in.

## Run it

```bash
bash <skill-dir>/scripts/check.sh acme-example brightpath.io
bash <skill-dir>/scripts/check.sh --tlds "com ai io" acme-example brightpath
```

A bare name is checked with each ending in `--tlds` (default `com`). A full domain is checked as given. Use `com` alone unless the user names other endings; for "any ending" use `--tlds "com ai io co app"`.

Pass names that can be registered (`example.com`, `example.co.uk`), not host names (`www.example.com`): a host name has no registration record of its own, so its answer means nothing.

## Read the answer

One line per domain, with the reason in brackets:

| Status | Meaning | What to tell the user |
|---|---|---|
| `AVAILABLE` | The registry holds no registration record for the name. | Probably free to register. A few names are reserved or restricted with no record, and a name registered minutes ago may not show yet, so the registrar's checkout page is the final word. |
| `TAKEN` | The name is registered. | Registered is not the same as in use: many names are parked for resale. Opening the address in a browser shows which. |
| `UNCLEAR` | The script could not get an answer it trusts (rate limit, timeout, a reply it does not recognise). | Say it is unknown and why. Run the script again later for those names, or check them at a registrar. Never report an `UNCLEAR` name as available. |

Show the user a table, `AVAILABLE` first. If nothing is available, say so and offer to try more names or other endings.

For a long list, run it in batches of about twenty; the lookup service slows callers that ask too fast, and the slowed ones fall back to whois, which is slower.

## How it decides

It asks rdap.org, a public service that forwards a domain question to the registry running that ending. A registry's own answer is trusted. For endings the service has no registry for (`.io`, `.co`, `.de` among others), and when the service is rate-limited or slow, the script asks the system `whois` instead and reads its answer conservatively: a clear record is `TAKEN`, a clear not-found is `AVAILABLE`, anything else is `UNCLEAR`.

## Requirements

`bash`, `curl` and `whois`. All three ship with macOS; on Debian or Ubuntu, `sudo apt-get install -y curl whois`. Without `whois` the script still works for the endings rdap.org covers and answers `UNCLEAR` for the rest. Tested on macOS and Ubuntu Linux; Windows is untested.

The script only checks. To register a name, the user goes to a registrar.
