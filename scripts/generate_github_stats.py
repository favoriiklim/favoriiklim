import os
import re
import json
import html
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone, timedelta

TOKEN = os.environ["GH_TOKEN"]
USERNAME = os.environ.get("GITHUB_USERNAME", "favoriiklim")

API_ROOT = "https://api.github.com"

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "custom-github-stats-card",
}


def api_get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as response:
        data = json.loads(response.read().decode("utf-8"))
        link = response.headers.get("Link", "")
        return data, link


def get_next_link(link_header):
    if not link_header:
        return None

    for part in link_header.split(","):
        if 'rel="next"' in part:
            match = re.search(r"<([^>]+)>", part)
            if match:
                return match.group(1)

    return None


def get_last_page_count_from_link(link_header):
    if not link_header:
        return None

    for part in link_header.split(","):
        if 'rel="last"' in part:
            match = re.search(r"[?&]page=(\d+)", part)
            if match:
                return int(match.group(1))

    return None


def paginated(url):
    items = []

    while url:
        data, link = api_get(url)

        if isinstance(data, list):
            items.extend(data)
        else:
            items.append(data)

        url = get_next_link(link)

    return items


def count_commits_last_year(repo):
    since = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat().replace("+00:00", "Z")

    full_name = repo["full_name"]
    branch = urllib.parse.quote(repo["default_branch"], safe="")
    author = urllib.parse.quote(USERNAME, safe="")
    since_q = urllib.parse.quote(since, safe="")

    url = (
        f"{API_ROOT}/repos/{full_name}/commits"
        f"?sha={branch}&author={author}&since={since_q}&per_page=1"
    )

    try:
        data, link = api_get(url)

        last_page = get_last_page_count_from_link(link)

        if last_page is not None:
            return last_page

        return len(data)

    except urllib.error.HTTPError as error:
        print(f"Skipping {full_name}: HTTP {error.code}")
        return 0

    except Exception as error:
        print(f"Skipping {full_name}: {error}")
        return 0


def make_svg(stats, top_repos):
    width = 495
    height = 195

    # Sağdaki halka içinde artık saçma rank değil,
    # gerçek aktif repo sayını gösteriyoruz.
    badge_text = str(stats["active_repos"])

    rows = [
        ("☆", "Total Stars:", stats["stars"]),
        ("↻", "Total Commits:", stats["commits_last_year"]),
        ("⑂", "Total Personal Repos:", stats["total_repos"]),
        ("!", "Active Repos:", stats["active_repos"]),
        ("▣", "Private Repos:", stats["private_repos"]),
    ]

    row_svg = []
    y = 72

    for icon, label, value in rows:
        row_svg.append(
            f'''
            <text x="25" y="{y}" class="icon">{html.escape(icon)}</text>
            <text x="55" y="{y}" class="label">{html.escape(label)}</text>
            <text x="300" y="{y}" class="value">{value}</text>
            '''
        )
        y += 28

    return f'''<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect width="{width}" height="{height}" rx="4" fill="#0c1014"/>

  <style>
    .title {{
      fill: #2aa889;
      font: 600 22px Arial, sans-serif;
    }}

    .icon {{
      fill: #5fb3c8;
      font: 400 21px Arial, sans-serif;
    }}

    .label {{
      fill: #99d1ce;
      font: 700 16px Arial, sans-serif;
    }}

    .value {{
      fill: #99d1ce;
      font: 700 16px Arial, sans-serif;
    }}

    .badge {{
      fill: #99d1ce;
      font: 700 31px Arial, sans-serif;
    }}

    .badge-sub {{
      fill: #2aa889;
      font: 700 10px Arial, sans-serif;
      letter-spacing: 0.8px;
    }}
  </style>

  <text x="25" y="35" class="title">{html.escape(USERNAME)}'s GitHub Stats</text>

  {''.join(row_svg)}

  <circle cx="400" cy="106" r="49" stroke="#153f37" stroke-width="7"/>
  <path
    d="M 400 57
       A 49 49 0 0 1 447 92"
    stroke="#2aa889"
    stroke-width="7"
    stroke-linecap="round"
    fill="none"
  />

  <text x="400" y="110" text-anchor="middle" dominant-baseline="middle" class="badge">{badge_text}</text>
  <text x="400" y="137" text-anchor="middle" class="badge-sub">ACTIVE</text>
</svg>
'''


def main():
    repos_url = (
        f"{API_ROOT}/user/repos"
        "?visibility=all&affiliation=owner&per_page=100&sort=pushed"
    )

    repos = paginated(repos_url)

    owner_repos = [
        repo for repo in repos
        if repo["owner"]["login"].lower() == USERNAME.lower()
    ]

    non_fork_repos = [
        repo for repo in owner_repos
        if not repo["fork"]
    ]

    active_repos = []
    total_commits = 0

    for repo in non_fork_repos:
        commits = count_commits_last_year(repo)

        if commits > 0:
            active_repos.append({
                "name": repo["name"],
                "commits": commits,
                "private": repo["private"],
            })
            total_commits += commits

    active_repos.sort(key=lambda item: item["commits"], reverse=True)

    stats = {
        "total_repos": len(owner_repos),
        "active_repos": len(active_repos),
        "commits_last_year": total_commits,
        "private_repos": sum(1 for repo in owner_repos if repo["private"]),
        "stars": sum(repo.get("stargazers_count", 0) for repo in owner_repos),
    }

    print(stats)

    Path("profile").mkdir(exist_ok=True)
    Path("profile/github-stats.svg").write_text(make_svg(stats, active_repos), encoding="utf-8")


if __name__ == "__main__":
    main()
