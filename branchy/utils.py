from re import match
from datetime import datetime, timedelta
from gi.repository import Adw

SOURCES_DIR = '/etc/apt/sources.list.d'
BRANCH_LIST_URL = 'http://repo.furios.io/get-branches'
ENABLED_BRANCHES_NAME = 'experiments.list'
CODENAME = 'trixie'
DEB_URL_TEMPLATE = 'http://furilabs-{repo}.repo.furios.io/{codename}-{branch}/'


def validate_branch_data(repo: str, branch: str, packages: list[str], version: str):
    if not repo:
        raise ValueError("Repository name cannot be empty")
    if not branch:
        raise ValueError("Branch name cannot be empty")
    if not packages:
        raise ValueError("Package list cannot be empty")
    if not version:
        raise ValueError("Version cannot be empty")

    if not match(r'^[a-z0-9.\-+]+$', repo):
        raise ValueError(f"Invalid repo name: {repo}")
    if not match(r'^[a-z0-9.\-+~:]+$', version):
        raise ValueError(f"Invalid version: {version}")
    if not match(r'^[a-z0-9.\-]+$', branch):
        raise ValueError(f"Invalid branch name: {branch}")
    if not all(match(r'^[a-z0-9.\-]+$', package) for package in packages):
        raise ValueError(f"Invalid package names: {' '.join(packages)}")


def show_toast(self, message):
    toast = Adw.Toast(title=message)
    self.toast_overlay.add_toast(toast)


def show_results(self, title, results):
    dialog = Adw.MessageDialog(
        transient_for=self.win,
        heading=title,
        body=results,
    )

    dialog.add_response("ok", "OK")
    dialog.present()


def get_time_ago(timestamp: int) -> str:
    now = datetime.now()
    dt = datetime.fromtimestamp(timestamp)
    diff = now - dt

    word = "month"
    n = diff.days // 30

    if diff < timedelta(hours=1):
        n = diff.seconds // 60
        word = "minute"
    elif diff < timedelta(days=1):
        n = diff.seconds // 3600
        word = "hour"
    elif diff < timedelta(weeks=1):
        n = diff.days
        word = "day"
    else:
        n = diff.days // 7
        word = "week"

    s = "" if n == 1 else "s"
    return f"{n} {word}{s} ago"
