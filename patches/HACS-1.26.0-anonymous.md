# HACS 1.26.0 - anonymous GitHub API patch

Why: the Pi has no GitHub account and no token. HACS 1.26.0 can browse public
repositories anonymously, but it disables itself when it sees an empty token
or hits GitHub's 60-requests-per-hour anonymous rate limit. Home Assistant
itself still works with no internet; only HACS browsing needs GitHub.

Applied to a local copy of HACS 1.26.0 (the patched bundle is kept outside Git):

1. `custom_components/hacs/__init__.py`
   - Empty YAML token (`token: ""`) is passed as `None` to both GitHub clients
     instead of an empty string, so the anonymous client path is used.

2. `custom_components/hacs/base.py`
   - `async_can_update()` no longer marks HACS disabled when the anonymous
     rate limit is reached. It fetches a small set of repos per cycle instead.

3. `custom_components/hacs/base.py`
   - `async_github_api_method()` no longer disables HACS on authentication or
     rate-limit exceptions; it logs and returns so HACS recovers later.

YAML mode in `configuration.yaml`:

```yaml
hacs:
  token: ""
  sidepanel_title: HACS
  sidepanel_icon: "hacs:hacs"
```

Note: GitHub rate-limit checks can still time out on a slow link. That shows
up in the HA log as a HACS timeout; it does not break Home Assistant or the
local tools. We do not ship the patched HACS bundle here - HACS is MIT, but
it belongs in its own release, not mixed into our repository.
