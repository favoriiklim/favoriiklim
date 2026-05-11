import os
import re
import html
import json
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


def request_json(url: str):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
        link = response.headers.get("Link", "")
        return data, link


def next_link(link_header: str):
    if not link_header:
        return None

    for part in link_header.split(","):
        section = part.strip()
        if 'rel="next"' in section:
            match = re.search(r"<([^>]+)>", section)
            if match:
                return match.group(1)

    return None


def paginated(url: str):
    while url:
        data, link = request_json(url)

        if isinstance(data, list):
            for item in data:
                yield item
        else:
            yield data

        url = next_link(link)


def safe_api_get(url: str):
    try:
        return list(paginated(url))
    except urllib.error.HTTPError as exc:
        if exc.code in (404, 409, 422):
            return []
        raise


def count_commits_on_default_branch(repo):
    since = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat().replace("+00:00", "Z")

    full_name = repo["full_name"]
    branch = urllib.parse.quote(repo["default_branch"], safe="")
    author = urllib.parse.quote(USERNAME, safe="")
    since_q = urllib.parse.quote(since, safe="")

    url = (
        f"{API_ROOT}/repos/{full_name}/commits"
        f"?sha={branch}&author={author}&since={since_q}&per_page=100"
    )

    return len(safe_api_get(url))


def make_svg(stats, top_repos):
    width = 560
    height = 310

    rows = [
        ("Total personal repos", stats["total_repos"]),
        ("Active repos last year", stats["active_repos"]),
        ("Commits last year", stats["commits_last_year"]),
        ("Private repos included", stats["private_repos"]),
        ("Public stars", stats["stars"]),
    ]

    row_svg = []
    y = 84

    for label, value in rows:
        row_svg.append(
            f'''
            <text x="32" y="{y}" class="label">{html.escape(label)}</text>
            <text x="500" y="{y}" text-anchor="end" class="value">{value}</text>
            '''
        )
        y += 34

    top_svg = []
    y = 250

    for repo in top_repos[:3]:
        name = html.escape(repo["name"])
        commits = repo["commits"]
        top_svg.append(
            f'''
            <text x="32" y="{y}" class="small">{name}</text>
            <text x="500" y="{y}" text-anchor="end" class="smallvalue">{commits} commits</text>
            '''
        )
        y += 22

    return f'''<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect width="{width}" height="{height}" rx="16" fill="#0c1014"/>
  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="15" stroke="#2aa889" stroke-opacity="0.35"/>

  <style>
    .title {{ fill: #2aa889; font: 700 22px Arial, sans-serif; }}
    .subtitle {{ fill: #8fbcbb; font: 400 13px Arial, sans-serif; }}
    .label {{ fill: #99d1ce; font: 400 16px Arial, sans-serif; }}
    .value {{ fill: #2aa889; font: 700 17px Arial, sans-serif; }}
    .section {{ fill: #8fbcbb; font: 700 14px Arial, sans-serif; }}
    .small {{ fill: #99d1ce; font: 400 13px Arial, sans-serif; }}
    .smallvalue {{ fill: #2aa889; font: 700 13px Arial, sans-serif; }}
  </style>

  <text x="32" y="42" class="title">{html.escape(USERNAME)}'s GitHub Stats</text>
  <text x="32" y="62" class="subtitle">Private repos included • last 365 days • default branches</text>

  {''.join(row_svg)}

  <text x="32" y="224" class="section">Top active repos</text>
  {''.join(top_svg)}
</svg>
'''


def main():
    repos_url = (
        f"{API_ROOT}/user/repos"
        "?visibility=all&affiliation=owner&per_page=100&sort=pushed"
    )

    repos = list(paginated(repos_url))

    owner_repos = [
        repo for repo in repos
        if repo["owner"]["login"].lower() == USERNAME.lower()
    ]

    non_fork_repos = [
        repo for repo in owner_repos
        if not repo["fork"]
    ]

    active = []
    total_commits = 0

    for repo in non_fork_repos:
        commits = count_commits_on_default_branch(repo)

        if commits > 0:
            active.append({
                "name": repo["name"],
                "full_name": repo["full_name"],
                "private": repo["private"],
                "commits": commits,
            })
            total_commits += commits

    active.sort(key=lambda item: item["commits"], reverse=True)

    stats = {
        "total_repos": len(owner_repos),
        "active_repos": len(active),
        "commits_last_year": total_commits,
        "private_repos": sum(1 for repo in owner_repos if repo["private"]),
        "stars": sum(repo.get("stargazers_count", 0) for repo in owner_repos),
    }

    svg = make_svg(stats, active)

    output_dir = Path("profile")
    output_dir.mkdir(exist_ok=True)

    Path("profile/github-stats.svg").write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    main()
