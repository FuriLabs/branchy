from asyncio import create_subprocess_exec, subprocess
from aiohttp import ClientSession as HttpClientSession
from os import listdir, path, unlink, environ
from re import search
from typing import Dict
from collections import OrderedDict
from datetime import datetime

from .repository import Repository, Branch
from .utils import validate_branch_data, SOURCES_DIR, BRANCH_LIST_URL, ENABLED_BRANCHES_NAME, CODENAME, DEB_URL_TEMPLATE


async def refresh_branches(app):
    app.clear()

    async with HttpClientSession() as session:
        async with session.get(BRANCH_LIST_URL) as response:
            if response.status == 200:
                data = await response.text()
                parse_branches(app, data)
            else:
                raise Exception(f"Failed to fetch branches: HTTP {response.status}")

    app.enabled_branches = get_enabled_branches(app)
    app.initial_branches = app.enabled_branches.copy()


def parse_branches(app, data: str):
    lines = data.strip().split('\n')
    for i in range(0, len(lines), 5):
        repo_name = lines[i]
        branch_name = lines[i + 1].strip()
        timestamp = int(lines[i + 2].strip())
        packages = lines[i + 3].strip().split(' ')
        version = lines[i + 4].strip()

        validate_branch_data(repo_name, branch_name, packages, version)

        if repo_name not in app.repositories:
            app.repositories[repo_name] = Repository(repo_name)
        
        branch = Branch(branch_name, timestamp, packages, version)
        app.repositories[repo_name].add_branch(branch)

    app.repositories = OrderedDict(sorted(
        app.repositories.items(),
        key=lambda x: max(branch.timestamp for branch in x[1].branches),
        reverse=True
    ))


def get_enabled_branches(app) -> Dict[str, str]:
    enabled_branches = {}
    app.system_branches = {}
    for filename in listdir(SOURCES_DIR):
        if filename.endswith('.list'):
            try:
                with open(path.join(SOURCES_DIR, filename), 'r') as f:
                    for line in f:
                        if line.startswith('deb '):
                            match = search(DEB_URL_TEMPLATE.format(repo='(.+)', codename=CODENAME, branch='(.+)'), line)
                            if match:
                                repo = match.group(1)
                                branch = match.group(2)
                                if filename == ENABLED_BRANCHES_NAME:
                                    enabled_branches[repo] = branch
                                else:
                                    app.system_branches[repo] = (branch, filename)
            except IOError as e:
                print(f"Error reading {filename}: {e}")
    return enabled_branches


async def run_process(args: list[str], output_stream_callback: callable = None, ignore_stderr: bool = False) -> tuple[subprocess.Process, str]:
    process = await create_subprocess_exec(
        *args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT if not ignore_stderr else subprocess.DEVNULL
    )

    output = []

    while True:
        line = await process.stdout.readline()
        if not line:
            break

        output += line.decode('utf-8')

        if output_stream_callback:
            output_stream_callback(line)

    await process.communicate()

    return process, ''.join(output)


async def apply_changes(app, output_stream_callback: callable = None):
    if not app.changed_branches:
        return

    script_content = await generate_update_script(app)

    if output_stream_callback:
        output_stream_callback(script_content.encode('utf-8'))

    temp_path = environ['HOME'] + "/.branchy-update.sh"

    with open(temp_path, 'w') as temp_file:
        temp_file.write(script_content)

    try:
        process, output = await run_process(
            ['pkexec', 'bash', temp_path],
            output_stream_callback=output_stream_callback
        )

        if process.returncode != 0:
            raise Exception(f"Error applying changes: {output}")

    finally:
        unlink(temp_path)


async def generate_update_script(app) -> str:
    return f"""#!/bin/bash
set -e

cat << EOF > {SOURCES_DIR}/{ENABLED_BRANCHES_NAME}
{get_sources(app)}
EOF

apt update -y

{await generate_apt_install_commands(app)}
"""


def get_sources(app) -> str:
    content = [f"# This file was generated by Branchy on {datetime.now().isoformat()}\n"]
    for repo, branch in app.enabled_branches.items():
        if app.system_branches.get(repo) and branch == app.system_branches[repo][0]:
            continue
        content.append(f"deb {DEB_URL_TEMPLATE.format(repo=repo, codename=CODENAME, branch=branch)} {CODENAME} main")
    return '\n'.join(content)


async def generate_apt_install_commands(app) -> str:
    reinstall_list = []
    install_list = []
    for repo, (old_branch, new_branch) in app.changed_branches.items():
        branch_info = next((x for x in app.repositories[repo].branches if x.name == (new_branch or old_branch)), None)

        if branch_info:
            user_installed_packages_subset = list((await get_installed_package_versions(branch_info.packages)).keys())

            if new_branch is None:
                reinstall_list.extend(user_installed_packages_subset)
            else:
                install_list.extend(f"{pkg}={branch_info.version}" for pkg in user_installed_packages_subset)

    commands = []
    if reinstall_list:
        commands.append(f"apt install --reinstall --allow-downgrades -y {' '.join(reinstall_list)}")
    if install_list:
        commands.append(f"apt install --allow-downgrades -y {' '.join(install_list)}")

    return ' && '.join(commands) if commands else ''


async def get_installed_package_versions(filter: list[str] = []) -> Dict[str, str]:
    process, output = await run_process(['dpkg-query', '-f', '${binary:Package} ${Version}\n', '-W', *filter], ignore_stderr=True)

    return dict(line.split(' ', 1) for line in output.strip().split('\n'))
