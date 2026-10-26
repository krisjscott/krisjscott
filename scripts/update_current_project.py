```python
import json
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

USER = "krisjscott"
PROFILE = f"{USER}/{USER}"
START = "<!-- CURRENT-PROJECT:START -->"
END = "<!-- CURRENT-PROJECT:END -->"


def api(path):
    # Deliberately unauthenticated: only public activity can be published.
    request = Request("https://api.github.com" + path, headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "public-profile-updater",
    })
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def timestamp(event):
    return datetime.strptime(event["created_at"], "%Y-%m-%dT%H:%M:%SZ")


def latest_push():
    events = []
    for page in range(1, 4):
        batch = api(f"/users/{USER}/events/public?per_page=100&page={page}")
        if not isinstance(batch, list):
            raise ValueError("Invalid events response")
        events.extend(batch)
        if len(batch) < 100:
            break
    pushes = [e for e in events if e.get("type") == "PushEvent"
              and e.get("public") is True
              and e.get("actor", {}).get("login", "").lower() == USER.lower()
              and e.get("repo", {}).get("name", "").lower() != PROFILE.lower()]
    return max(pushes, key=timestamp) if pushes else None


def safe_text(text):
    # Plain text, not Markdown/HTML, even for hostile commit messages.
    text = " ".join(text.split())
    text = "".join(c for c in text if not unicodedata.category(c).startswith("C"))
    return "".join(c if c.isalnum() or c == " " else f"&#{ord(c)};"
                   for c in text[:180])


def update(path=Path("README.md")):
    original = path.read_text(encoding="utf-8")
    if (original.count(START) != 1 or original.count(END) != 1
            or original.index(START) >= original.index(END)):
        raise ValueError("README needs one ordered pair of CURRENT-PROJECT markers")
    event = latest_push()
    if event is None:
        print("No public push found; README unchanged.")
        return
    repo = event["repo"]["name"]
    head = event["payload"].get("head", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Invalid repository name")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", head) or int(head, 16) == 0:
        raise ValueError("Push has no usable head commit")
    metadata = api(f"/repos/{repo}")
    if metadata.get("private") is not False:
        raise ValueError("Repository is not public")
    commit = api(f"/repos/{repo}/commits/{head}")
    if commit.get("sha", "").lower() != head.lower():
        raise ValueError("Commit does not match push")
    message = commit["commit"]["message"].splitlines()[0]
    date = timestamp(event).strftime("%d %b %Y, %H:%M UTC")
    block = (f'\n**Currently working on:** '
             f'[{safe_text(repo.split("/", 1)[1])}](https://github.com/{repo})\n\n'
             f'Latest public push: {date} | '
             f'[{head[:7]}](https://github.com/{repo}/commit/{head})\n\n'
             f'{safe_text(message)}\n')
    before, rest = original.split(START, 1)
    _, after = rest.split(END, 1)
    updated = before + START + block + END + after
    if updated != original:
        path.write_text(updated, encoding="utf-8")
        print("Updated current-project block.")
    else:
        print("Current-project block already up to date.")


if __name__ == "__main__":
    try:
        update()
    except Exception:
        print("Update failed; existing README preserved. Check API access and markers.",
              file=sys.stderr)
        sys.exit(1)

```
