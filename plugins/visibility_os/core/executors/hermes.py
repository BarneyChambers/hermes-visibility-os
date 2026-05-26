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


def _parse_json_object(stdout: str, *, label: str) -> dict[str, Any]:
    text = (stdout or "").strip()
    if not text:
        raise RuntimeError(f"{label} returned no JSON payload")
    try:
        parsed = json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise RuntimeError(f"{label} must return JSON")
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{label} JSON must be an object")
    return parsed


def _parse_independent_review(stdout: str) -> dict[str, Any]:
    parsed = _parse_json_object(stdout, label="Independent Fix CI review")
    if not parsed.get("review_status"):
        raise RuntimeError("Independent Fix CI review requires review_status")
    status = str(parsed.get("review_status")).lower()
    if status not in {"passed", "approved", "no_blockers"}:
        raise RuntimeError(f"Independent Fix CI review did not pass: {parsed.get('review_status')}")
    return parsed


def _build_independent_review_prompt(repo: str, prepared: dict[str, Any], *, lane_label: str = "CI fix", issue_number: int | None = None) -> str:
    context = [f"Repository: {repo}"]
    if issue_number is not None:
        context.append(f"Issue: #{issue_number}")
    return "\n".join([
        f"You are a fresh session independent reviewer for a prepared {lane_label}.",
        "You were not involved in the fix. Do not assume the fix is correct.",
        "Review only the current local repository state, branch, commit/diff, proposed PR text, and verification evidence.",
        "Do not use or rely on the original fixing prompt or the fixing agent's reasoning.",
        "Look for regressions, unintended scope creep, security issues, missing tests, brittle logic, and PR description inaccuracies.",
        "Do not push, merge, deploy, rotate secrets, or touch production infrastructure.",
        *context,
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


def _execute_pr_review_lane(action: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("lane") != "review_pr":
        raise RuntimeError("Hermes PR review payload must declare lane='review_pr'")
    repo = payload.get("repo")
    _ensure_allowed_repo(repo)
    prompt = payload.get("prompt")
    if not prompt:
        raise RuntimeError("PR review lane requires a prompt")
    workdir = payload.get("workdir") or str(Path.home() / ".hermes" / "visibility-os" / "pr-review-workspaces" / str(repo).replace("/", "__"))
    Path(workdir).mkdir(parents=True, exist_ok=True)
    cmd = _command_with_prompt(payload.get("command") or [], str(prompt), source="visibility-os-pr-review")
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=int(payload.get("timeout_seconds") or 1800), check=False, cwd=workdir)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or res.stdout.strip() or "Hermes PR review lane failed")
    review = _parse_json_object(res.stdout, label="Hermes PR review lane")
    if not review.get("review_status") or not review.get("body"):
        raise RuntimeError("Hermes PR review lane requires review_status and body")
    post_action = create_action(
        proposed_by_agent="visibility_os",
        action_type="github_pr_comment",
        target_system="github",
        target_location=payload.get("pr_url") or action.get("target_location") or "",
        title=f"Post PR review: {payload.get('repo')}#{payload.get('pr_number')}",
        summary="Review and optionally post the fresh-session Hermes PR review comment.",
        proposed_payload={"body": review["body"], "review_status": review.get("review_status"), "findings": review.get("findings") or [], "notes": review.get("notes")},
        evidence_links=action.get("evidence_links") or [],
        risk_level="medium",
        opportunity_id=action.get("opportunity_id"),
        impact_score=action.get("impact_score"),
        visibility_score=action.get("visibility_score"),
        effort_score=action.get("effort_score"),
        approval_reason="Posts an external GitHub PR review/comment, so a human approver must explicitly approve it.",
    )
    return {"ok": True, "lane": "review_pr", "repo": repo, "pr_number": payload.get("pr_number"), "review_status": review.get("review_status"), "post_action_id": post_action["id"], "review": review, "stdout": res.stdout.strip(), "stderr": res.stderr.strip(), "command": cmd[:3] + ["..."], "workdir": workdir}


def execute_hermes_action(action: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    action_type = action["action_type"]
    lane = payload.get("lane")
    if action_type == "ci_fix_lane":
        expected_lanes = {"fix_ci"}
        source = "visibility-os-ci-review"
        lane_label = "CI fix"
        default_workspace = "ci-fix-workspaces"
        push_title = "Push prepared CI fix branch"
        if payload.get("should_create_fix_branch") is False:
            raise RuntimeError("Refusing to execute Fix CI lane because diagnosis marked it non-actionable")
    elif action_type == "github_issue_fix_lane":
        expected_lanes = {"fix_github_issue", "fix_docs", "fix_bug", "deflake_test"}
        source = "visibility-os-issue-review"
        lane_label = "GitHub issue fix"
        default_workspace = "issue-fix-workspaces"
        push_title = "Push prepared issue fix branch"
    elif action_type == "pr_ci_fix_lane":
        expected_lanes = {"fix_pr_ci"}
        source = "visibility-os-pr-ci-review"
        lane_label = "PR CI fix"
        default_workspace = "pr-ci-fix-workspaces"
        push_title = "Push prepared PR CI fix branch"
    elif action_type == "wip_handoff_lane":
        expected_lanes = {"prepare_handoff_branch"}
        source = "visibility-os-wip-handoff-review"
        lane_label = "WIP handoff"
        default_workspace = "wip-handoff-workspaces"
        push_title = "Push prepared WIP handoff branch"
    elif action_type == "github_pr_review_lane":
        return _execute_pr_review_lane(action, payload)
    else:
        raise RuntimeError(f"Unsupported Hermes action type {action_type}")
    if lane not in expected_lanes:
        raise RuntimeError(f"Hermes action payload must declare lane in {sorted(expected_lanes)}")
    repo = payload.get("repo")
    _ensure_allowed_repo(repo)
    prompt = payload.get("prompt")
    if not prompt:
        raise RuntimeError(f"{lane_label} lane requires a prompt")
    workdir = payload.get("workdir") or str(Path.home() / ".hermes" / "visibility-os" / default_workspace / str(repo).replace("/", "__"))
    Path(workdir).mkdir(parents=True, exist_ok=True)
    cmd = _command_with_prompt(payload.get("command") or [], str(prompt), source="visibility-os-issue-fix" if action_type == "github_issue_fix_lane" else "visibility-os-ci-fix")
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=int(payload.get("timeout_seconds") or 3600), check=False, cwd=workdir)
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or res.stdout.strip() or f"Hermes {lane_label} lane failed")
    prepared = _parse_prepared_fix(res.stdout)
    review_prompt = _build_independent_review_prompt(str(repo), prepared, lane_label=lane_label, issue_number=payload.get("issue_number"))
    review_cmd = _command_with_prompt(payload.get("review_command") or [], review_prompt, source=source)
    review_res = subprocess.run(review_cmd, capture_output=True, text=True, timeout=int(payload.get("review_timeout_seconds") or 1800), check=False, cwd=workdir)
    if review_res.returncode != 0:
        raise RuntimeError(review_res.stderr.strip() or review_res.stdout.strip() or f"Independent {lane_label} review failed")
    independent_review = _parse_independent_review(review_res.stdout)
    push_payload = {
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
        "issue_number": payload.get("issue_number"),
        "issue_url": payload.get("issue_url"),
    }
    push_action = create_action(
        proposed_by_agent="visibility_os",
        action_type="github_push_branch",
        target_system="github",
        target_location=f"{repo}#{prepared['branch']}",
        title=f"{push_title}: {prepared['branch']}",
        summary=f"Review and optionally push local branch {prepared['branch']} and create a PR for {repo}.",
        proposed_payload=push_payload,
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
        "lane": lane,
        "mode": "prepared_local_branch_only",
        "repo": repo,
        "run_id": payload.get("run_id"),
        "issue_number": payload.get("issue_number"),
        "issue_url": payload.get("issue_url"),
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
