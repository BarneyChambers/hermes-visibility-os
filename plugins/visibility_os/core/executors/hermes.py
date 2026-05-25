from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

from ..actions import create_action
from ..config import get_visibility_config


def _ensure_allowed_repo(repo: str | None) -> None:
    cfg = get_visibility_config()
    if not cfg.github_repo_allowed(repo):
        raise RuntimeError(f"Visibility OS Hermes lanes are restricted to configured repositories: {cfg.github_scope_label}")


def _command_with_prompt(command: list[Any], prompt: str, *, source: str = "visibility-os-ci-fix") -> list[str]:
    if not command:
        return [
            "hermes",
            "chat",
            "--query",
            prompt,
            "--quiet",
            "--source",
            source,
            "--toolsets",
            "terminal,file",
        ]
    return [prompt if str(part) == "__PROMPT__" else str(part) for part in command]


def _parse_prepared_fix(stdout: str) -> dict[str, Any]:
    text = (stdout or "").strip()
    if not text:
        raise RuntimeError("Hermes Fix CI lane returned no prepared-branch payload")
    try:
        parsed = json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise RuntimeError("Hermes Fix CI lane must return JSON describing the prepared branch")
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise RuntimeError("Hermes Fix CI lane JSON must be an object")
    missing = [key for key in ("branch", "commit_message", "pr_title", "pr_body", "self_audit") if not parsed.get(key)]
    if missing:
        raise RuntimeError(f"Prepared Fix CI payload missing required field(s): {', '.join(missing)}")
    self_audit = parsed.get("self_audit")
    if not isinstance(self_audit, dict) or not self_audit.get("audit_status"):
        raise RuntimeError("Prepared Fix CI payload requires self_audit.audit_status from the second-pass review")
    if parsed.get("ready_to_push") is False:
        raise RuntimeError("Hermes Fix CI lane did not mark the prepared branch ready to push")
    return parsed


def _parse_independent_review(stdout: str) -> dict[str, Any]:
    text = (stdout or "").strip()
    if not text:
        raise RuntimeError("Independent Fix CI review returned no JSON payload")
    try:
        parsed = json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise RuntimeError("Independent Fix CI review must return JSON")
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict) or not parsed.get("review_status"):
        raise RuntimeError("Independent Fix CI review requires review_status")
    status = str(parsed.get("review_status")).lower()
    if status not in {"passed", "approved", "no_blockers"}:
        raise RuntimeError(f"Independent Fix CI review did not pass: {parsed.get('review_status')}")
    return parsed


def _build_independent_review_prompt(repo: str, prepared: dict[str, Any]) -> str:
    return "\n".join([
        "You are a fresh session independent reviewer for a prepared CI fix.",
        "You were not involved in the fix. Do not assume the fix is correct.",
        "Review only the current local repository state, branch, commit/diff, proposed PR text, and verification evidence.",
        "Do not use or rely on the original fixing prompt or the fixing agent's reasoning.",
        "Look for regressions, unintended scope creep, security issues, missing tests, brittle logic, and PR description inaccuracies.",
        "Do not push, merge, deploy, rotate secrets, or touch production infrastructure.",
        f"Repository: {repo}",
        f"Prepared branch: {prepared.get('branch')}",
        f"Commit: {prepared.get('commit_sha') or 'unknown'}",
        f"Commit message: {prepared.get('commit_message')}",
        f"PR title: {prepared.get('pr_title')}",
        "Changed files: " + json.dumps(prepared.get("changed_files") or []),
        "Verification evidence: " + json.dumps(prepared.get("verification") or []),
        "PR body:",
        str(prepared.get("pr_body") or ""),
        "Return JSON only with: review_status, findings, fixes_required, notes.",
        "Use review_status='passed' only if there are no blockers to pushing this prepared branch for PR creation.",
    ])


def execute_hermes_action(action: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if action["action_type"] != "ci_fix_lane":
        raise RuntimeError(f"Unsupported Hermes action type {action['action_type']}")
    if payload.get("lane") != "fix_ci":
        raise RuntimeError("Hermes action payload must declare lane='fix_ci'")
    repo = payload.get("repo")
    _ensure_allowed_repo(repo)
    if payload.get("should_create_fix_branch") is False:
        raise RuntimeError("Refusing to execute Fix CI lane because diagnosis marked it non-actionable")
    prompt = payload.get("prompt")
    if not prompt:
        raise RuntimeError("Fix CI lane requires a prompt")
    workdir = payload.get("workdir") or str(Path.home() / ".hermes" / "visibility-os" / "ci-fix-workspaces" / str(repo).replace("/", "__"))
    Path(workdir).mkdir(parents=True, exist_ok=True)
    cmd = _command_with_prompt(payload.get("command") or [], str(prompt))
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=int(payload.get("timeout_seconds") or 3600), check=False, cwd=workdir)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or res.stdout.strip() or "Hermes Fix CI lane failed")
    prepared = _parse_prepared_fix(res.stdout)
    review_prompt = _build_independent_review_prompt(str(repo), prepared)
    review_cmd = _command_with_prompt(payload.get("review_command") or [], review_prompt, source="visibility-os-ci-review")
    review_res = subprocess.run(review_cmd, capture_output=True, text=True, timeout=int(payload.get("review_timeout_seconds") or 1800), check=False, cwd=workdir)
    if review_res.returncode != 0:
        raise RuntimeError(review_res.stderr.strip() or review_res.stdout.strip() or "Independent Fix CI review failed")
    independent_review = _parse_independent_review(review_res.stdout)
    push_action = create_action(
        proposed_by_agent="visibility_os",
        action_type="github_push_branch",
        target_system="github",
        target_location=f"{repo}#{prepared['branch']}",
        title=f"Push prepared CI fix branch: {prepared['branch']}",
        summary=f"Review and optionally push local branch {prepared['branch']} and create a PR for {repo}.",
        proposed_payload={
            "repo": repo,
            "branch": prepared["branch"],
            "base_branch": (payload.get("pr_context") or {}).get("base_branch") or prepared.get("base_branch") or "main",
            "workdir": workdir,
            "commit_sha": prepared.get("commit_sha"),
            "commit_message": prepared.get("commit_message"),
            "pr_title": prepared.get("pr_title") or prepared.get("commit_message"),
            "pr_body": prepared.get("pr_body"),
            "verification": prepared.get("verification") or [],
            "changed_files": prepared.get("changed_files") or [],
            "self_audit": prepared.get("self_audit") or {},
            "independent_review": independent_review,
            "source_run_id": payload.get("run_id"),
            "source_run_url": payload.get("run_url"),
        },
        evidence_links=action.get("evidence_links") or [],
        risk_level="high",
        opportunity_id=action.get("opportunity_id"),
        impact_score=action.get("impact_score"),
        visibility_score=action.get("visibility_score"),
        effort_score=action.get("effort_score"),
        approval_reason="Pushes a prepared local branch and creates a GitHub PR, so a human approver must explicitly choose Push branch.",
    )
    return {
        "ok": True,
        "lane": "fix_ci",
        "mode": "prepared_local_branch_only",
        "repo": repo,
        "run_id": payload.get("run_id"),
        "prepared_branch": prepared["branch"],
        "commit_sha": prepared.get("commit_sha"),
        "commit_message": prepared.get("commit_message"),
        "pr_title": prepared.get("pr_title"),
        "pr_body": prepared.get("pr_body"),
        "verification": prepared.get("verification") or [],
        "changed_files": prepared.get("changed_files") or [],
        "self_audit": prepared.get("self_audit") or {},
        "independent_review": independent_review,
        "push_action_id": push_action["id"],
        "stdout": res.stdout.strip(),
        "stderr": res.stderr.strip(),
        "command": cmd[:3] + ["..."],
        "workdir": workdir,
    }
