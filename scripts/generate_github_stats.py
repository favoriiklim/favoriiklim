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
    rows = [
        ("Total personal repos", stats["total_repos"]),
        ("Active repos last year", stats["active_repos"]),
        ("Commits last year", stats["commits_last_year"]),
        ("Private repos included", stats["private_repos"]),
        ("Public stars", stats["stars"]),
    ]

    row_svg = []
    y = 86

    for label, value in rows:
        row_svg.append(
            f'''
            <text x="32" y="{y}" class="label">{html.escape(label)}</text>
            <text x="500" y="{y}" text-anchor="end" class="value">{value}</text>
            '''
        )
        y += 34

    top_svg = []
    y = 254

    for repo in top_repos[:3]:
        top_svg.append(
            f'''
            <text x="32" y="{y}" class="small">{html.escape(repo["name"])}</text>
            <text x="500" y="{y}" text-anchor="end" class="smallvalue">{repo["commits"]} commits</text>
            '''
        )
        y += 22

    return f'''<svg width="560" height="320" viewBox="0 0 560 320" fill="none" xmlns="http://www.w3.org/2000/svg">
  <rect width="560" height="320" rx="16" fill="#0c1014"/>
  <rect x="1" y="1" width="558" height="318" rx="15" stroke="#2aa889" stroke-opacity="0.35"/>

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

  <text x="32" y="228" class="section">Top active repos</text>
  {''.join(top_svg)}
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
