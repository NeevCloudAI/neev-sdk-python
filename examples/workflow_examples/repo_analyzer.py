"""
Repository Analyzer — clone and audit an untrusted git repo in a Neev sandbox.

Demonstrates:
- Cloning untrusted repositories
- Executing shell commands against foreign code
- Scanning source for structure and security patterns
- Isolating the entire workload in a disposable sandbox

Run::

    uv run python examples/workflow_examples/repo_analyzer.py \\
        --repo https://github.com/tncrayt/react-calculator

"""

from __future__ import annotations

import argparse
import io
import os
import re
import shlex
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent_patterns"))

from utils.agent_loop import RUN_SHELL_TOOL, StreamingAgentLoop, make_run_shell_handler

from neevai import NeevAI
from neevai.handles import Sandbox
from neevai.types import ExecResult

SYSTEM_PROMPT = (
    "You are a code-review assistant. You have a run_shell tool that executes "
    "POSIX sh in a secure Neev sandbox. The repository has already been cloned "
    "to /workspace/repo. You should produce four clearly labelled sections:\n"
    "1. Architecture summary — language, framework, directory layout, entry points\n"
    "2. Dependency report — key dependencies, build system, license\n"
    "3. Security findings — use of exec/eval, network calls, file access, secrets in code\n"
    "4. Interesting observations — unusual patterns, monorepo layout, typing, code generation\n"
    "Be specific, reference actual file paths and line numbers where relevant."
)

MAX_STEPS = int(os.environ.get("NEEVAI_WORKFLOW_MAX_STEPS", "35"))
_GIT_STATIC_URL = os.environ.get("NEEV_GIT_STATIC_URL", "").strip()

HERE = Path(__file__).resolve().parent
OUTPUT_DIR = HERE / "output"

_PACKAGE_INSTALLERS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("apt-get", "/usr/bin/apt-get"),
        (
            "export DEBIAN_FRONTEND=noninteractive && "
            "{bin} update -qq && {bin} install -y -qq --no-install-recommends {pkg}"
        ),
    ),
    (
        ("apt", "/usr/bin/apt"),
        (
            "export DEBIAN_FRONTEND=noninteractive && "
            "{bin} update -qq && {bin} install -y -qq --no-install-recommends {pkg}"
        ),
    ),
    (("apk", "/sbin/apk", "/usr/bin/apk"), "{bin} add --no-cache {pkg}"),
    (("microdnf", "/usr/bin/microdnf"), "{bin} install -y {pkg}"),
    (("dnf", "/usr/bin/dnf"), "{bin} install -y {pkg}"),
    (("yum", "/usr/bin/yum"), "{bin} install -y {pkg}"),
    (("zypper", "/usr/bin/zypper"), "{bin} --non-interactive install -y {pkg}"),
    (("pacman", "/usr/bin/pacman"), "{bin} -Sy --noconfirm {pkg}"),
)


def _exec_sh(sandbox: Sandbox, script: str, *, timeout_ms: int | None = None) -> ExecResult:
    command: list[str] = ["sh", "-c", script]
    if timeout_ms is None:
        return sandbox.exec(command)
    return sandbox.exec(command, timeout_ms=timeout_ms)


def _resolve_tool_path(sandbox: Sandbox, name: str) -> str | None:
    result = _exec_sh(
        sandbox,
        (
            f'name="{name}"; '
            f'for p in "$name" /usr/bin/"$name" /bin/"$name" /sbin/"$name"; do '
            'if command -v "$p" >/dev/null 2>&1; then command -v "$p"; exit 0; fi; '
            'if [ -x "$p" ]; then printf "%s" "$p"; exit 0; fi; '
            "done; exit 1"
        ),
    )
    if result.exit_code == 0 and result.stdout.strip():
        return result.stdout.strip()
    return None


def _has_tool(sandbox: Sandbox, name: str) -> bool:
    return _resolve_tool_path(sandbox, name) is not None


def _resolve_binary(sandbox: Sandbox, candidate: str) -> str | None:
    if candidate.startswith("/"):
        result = _exec_sh(sandbox, f'[ -x "{candidate}" ] && printf "%s" "{candidate}"')
        if result.exit_code == 0 and result.stdout.strip():
            return result.stdout.strip()
        return None
    return _resolve_tool_path(sandbox, candidate)


def _install_package(sandbox: Sandbox, package: str) -> tuple[bool, str]:
    errors: list[str] = []
    for candidates, template in _PACKAGE_INSTALLERS:
        for candidate in candidates:
            bin_path = _resolve_binary(sandbox, candidate)
            if bin_path is None:
                continue
            print(f"[bootstrap] installing {package} via {bin_path}…", file=sys.stderr)
            result = _exec_sh(
                sandbox, template.format(bin=bin_path, pkg=package), timeout_ms=300_000
            )
            if result.exit_code == 0:
                return True, ""
            errors.append(f"{bin_path}: {result.stderr.strip() or result.stdout.strip()}")
    return False, "\n".join(errors)


def _install_git_static(sandbox: Sandbox) -> bool:
    if not _GIT_STATIC_URL:
        return False

    downloader = _resolve_tool_path(sandbox, "curl") or _resolve_tool_path(sandbox, "wget")
    if downloader is None:
        return False

    print(f"[bootstrap] installing git from NEEV_GIT_STATIC_URL via {downloader}…", file=sys.stderr)
    if downloader.endswith("curl"):
        fetch = f'curl -fsSL "{_GIT_STATIC_URL}" -o /usr/local/bin/git'
    else:
        fetch = f'wget -qO /usr/local/bin/git "{_GIT_STATIC_URL}"'

    result = _exec_sh(
        sandbox,
        f"mkdir -p /usr/local/bin && {fetch} && chmod +x /usr/local/bin/git",
        timeout_ms=300_000,
    )
    if result.exit_code != 0:
        print(
            f"[bootstrap] static git install failed:\n{result.stderr or result.stdout}",
            file=sys.stderr,
        )
        return False
    return _has_tool(sandbox, "git")


def _bootstrap_failure_message(tool: str, details: str, *, required: bool) -> str:
    template_id = os.environ.get("NEEV_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")
    requirement = "required" if required else "optional"
    return (
        f"Could not install {tool} ({requirement}) in the sandbox.\n"
        f"Tried common package managers (apt-get, apt, apk, dnf, yum, …) and no "
        f"supported manager was found.\n"
        f"Current template: {template_id}\n"
        f"Recommendations:\n"
        f"  - Use a template with {tool} preinstalled (set NEEV_SANDBOX_TEMPLATE_ID)\n"
        f"  - For git only: host archive fallback is attempted automatically for GitHub URLs\n"
        f"  - For static git: set NEEV_GIT_STATIC_URL to a downloadable linux git binary\n"
        f"Details:\n{details or '(no package manager output)'}"
    )


def create_standard_sandbox(client: NeevAI, region: str | None = None) -> Sandbox:
    template_id = os.environ.get("NEEV_SANDBOX_TEMPLATE_ID", "sb-ubuntu-26-04-minimal")
    suffix = hex(int(time.time() * 1e6))[-6:]
    print(f"[sandbox] creating (template={template_id})…", file=sys.stderr)
    sandbox = client.sandboxes.create(
        {
            "name": f"repo-analyzer-{suffix}",
            "sandbox_template_id": template_id,
        }
    )
    print(f"[sandbox] created {sandbox.id}; waiting until ready…", file=sys.stderr)
    sandbox.wait_until_ready()
    print(f"[sandbox] ready: {sandbox.connect_url}", file=sys.stderr)
    return sandbox


def install_git(sandbox: Sandbox) -> bool:
    """Install git when possible; return True if git is available afterward."""
    if _has_tool(sandbox, "git"):
        print("[bootstrap] git available", file=sys.stderr)
        return True

    ok, details = _install_package(sandbox, "git")
    if ok and _has_tool(sandbox, "git"):
        print("[bootstrap] git installed", file=sys.stderr)
        return True

    if _install_git_static(sandbox):
        print("[bootstrap] git installed from static binary", file=sys.stderr)
        return True

    if _has_tool(sandbox, "git"):
        print("[bootstrap] git available", file=sys.stderr)
        return True

    print(
        "[bootstrap] WARNING: git is not installed in the sandbox. "
        "Will try archive-based clone fallbacks for supported hosts.",
        file=sys.stderr,
    )
    if details:
        print(f"[bootstrap] package manager attempts:\n{details}", file=sys.stderr)
    return False


def ensure_tools(sandbox: Sandbox) -> None:
    """Ensure git (or clone fallback) and optionally ripgrep are available."""
    install_git(sandbox)

    if _has_tool(sandbox, "rg"):
        print("[bootstrap] ripgrep available", file=sys.stderr)
        return

    ok, details = _install_package(sandbox, "ripgrep")
    if ok and _has_tool(sandbox, "rg"):
        print("[bootstrap] ripgrep installed", file=sys.stderr)
        return

    print(
        "[bootstrap] WARNING: could not install ripgrep. The agent can still use grep/find.",
        file=sys.stderr,
    )
    if details:
        print(f"[bootstrap] package manager attempts:\n{details}", file=sys.stderr)


_GITHUB_REPO_RE = re.compile(
    r"^https?://(?:www\.)?github\.com/(?P<owner>[^/]+)/(?P<repo>[^/.]+?)(?:\.git)?/?$"
)


def _github_archive_url(owner: str, repo: str, branch: str) -> str:
    return f"https://codeload.github.com/{owner}/{repo}/tar.gz/refs/heads/{branch}"


def _github_archive_exists(url: str) -> bool:
    request = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return 200 <= response.status < 300
    except urllib.error.HTTPError as exc:
        return exc.code == 302
    except urllib.error.URLError:
        return False


def _download_github_archive(owner: str, repo: str) -> tuple[bytes, str]:
    last_error = "archive not found"
    for branch in ("main", "master"):
        archive_url = _github_archive_url(owner, repo, branch)
        if not _github_archive_exists(archive_url):
            continue
        try:
            with urllib.request.urlopen(archive_url, timeout=120) as response:
                return response.read(), branch
        except urllib.error.URLError as exc:
            last_error = str(exc)
    raise RuntimeError(f"Could not download GitHub archive for {owner}/{repo}: {last_error}")


def _extract_archive_in_sandbox(sandbox: Sandbox) -> bool:
    result = _exec_sh(
        sandbox,
        "mkdir -p /workspace/repo && tar -xzf /workspace/repo.tar.gz -C /workspace/repo --strip-components=1",
    )
    return result.exit_code == 0


def _extract_archive_from_host(sandbox: Sandbox, archive: bytes) -> None:
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as archive_file:
        members = [member for member in archive_file.getmembers() if member.isfile()]
        if not members:
            raise RuntimeError("Downloaded archive contained no files")

        top_prefix = members[0].name.split("/", 1)[0] + "/"
        for member in members:
            if not member.name.startswith(top_prefix):
                continue
            relative = member.name[len(top_prefix) :]
            if not relative:
                continue
            extracted = archive_file.extractfile(member)
            if extracted is None:
                continue
            sandbox.files.write(f"repo/{relative}", extracted.read())


def _clone_via_archive_in_sandbox(sandbox: Sandbox, owner: str, repo: str) -> bool:
    downloader = _resolve_tool_path(sandbox, "curl") or _resolve_tool_path(sandbox, "wget")
    if downloader is None or not _has_tool(sandbox, "tar"):
        return False

    for branch in ("main", "master"):
        archive_url = _github_archive_url(owner, repo, branch)
        print(f"[clone] trying GitHub archive ({branch}) inside sandbox…", file=sys.stderr)
        if downloader.endswith("curl"):
            fetch = f'curl -fsSL "{archive_url}" -o /workspace/repo.tar.gz'
        else:
            fetch = f'wget -qO /workspace/repo.tar.gz "{archive_url}"'

        result = _exec_sh(sandbox, f"mkdir -p /workspace && {fetch}", timeout_ms=300_000)
        if result.exit_code != 0:
            continue
        if _extract_archive_in_sandbox(sandbox):
            print(f"[clone] extracted archive via sandbox ({branch})", file=sys.stderr)
            return True
    return False


def _clone_from_host(sandbox: Sandbox, owner: str, repo: str) -> None:
    print(f"[clone] downloading GitHub archive on host for {owner}/{repo}…", file=sys.stderr)
    archive, branch = _download_github_archive(owner, repo)
    sandbox.files.write("repo.tar.gz", archive)

    if _extract_archive_in_sandbox(sandbox):
        print(f"[clone] extracted archive in sandbox ({branch})", file=sys.stderr)
        return

    print(
        "[clone] tar unavailable in sandbox; uploading extracted files from host…", file=sys.stderr
    )
    _extract_archive_from_host(sandbox, archive)
    print(f"[clone] uploaded extracted archive from host ({branch})", file=sys.stderr)


def clone_repo(sandbox: Sandbox, repo_url: str) -> None:
    print(f"[clone] fetching {repo_url}…", file=sys.stderr)

    if _has_tool(sandbox, "git"):
        result = _exec_sh(
            sandbox,
            f"git clone --depth=1 {shlex.quote(repo_url)} /workspace/repo",
            timeout_ms=300_000,
        )
        if result.exit_code == 0:
            size = _exec_sh(
                sandbox, "du -sh /workspace/repo 2>/dev/null || echo unknown"
            ).stdout.strip()
            print(f"[clone] done ({size})", file=sys.stderr)
            return
        print(
            "[clone] git clone failed; trying archive fallback if supported…\n"
            f"{result.stderr or result.stdout}",
            file=sys.stderr,
        )

    match = _GITHUB_REPO_RE.match(repo_url.rstrip("/"))
    if match is None:
        raise RuntimeError(
            _bootstrap_failure_message(
                "git",
                "git clone is unavailable and archive fallback only supports GitHub HTTPS URLs.",
                required=True,
            )
        )

    owner = match.group("owner")
    repo = match.group("repo")
    if _clone_via_archive_in_sandbox(sandbox, owner, repo):
        size = _exec_sh(
            sandbox, "du -sh /workspace/repo 2>/dev/null || echo unknown"
        ).stdout.strip()
        print(f"[clone] done ({size})", file=sys.stderr)
        return

    try:
        _clone_from_host(sandbox, owner, repo)
    except RuntimeError as exc:
        raise RuntimeError(_bootstrap_failure_message("git", str(exc), required=True)) from exc

    size = _exec_sh(sandbox, "du -sh /workspace/repo 2>/dev/null || echo unknown").stdout.strip()
    print(f"[clone] done ({size})", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze a git repository in a sandbox.")
    parser.add_argument(
        "--repo",
        default="https://github.com/NeevCloudAI/neevai-sdk-python",
        help="Repository URL to clone and analyze (default: neevai-sdk-python)",
    )
    args = parser.parse_args()

    with NeevAI() as client:
        sandbox = create_standard_sandbox(client)
        try:
            ensure_tools(sandbox)
            clone_repo(sandbox, args.repo)

            loop = StreamingAgentLoop(
                sandbox,
                system_prompt=SYSTEM_PROMPT,
                tools=[RUN_SHELL_TOOL],
                handlers={"run_shell": make_run_shell_handler(sandbox)},
                max_steps=MAX_STEPS,
            )
            final = loop.run("Analyze the repository cloned at /workspace/repo.")
            print(final)

            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            report_path = OUTPUT_DIR / "repo-analysis.md"
            report_path.write_text(final, encoding="utf-8")
            print(
                f"[artifact] saved {len(final.encode('utf-8'))} bytes → {report_path}",
                file=sys.stderr,
            )
        finally:
            print(f"[sandbox] deleting {sandbox.id}", file=sys.stderr)
            sandbox.delete()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
