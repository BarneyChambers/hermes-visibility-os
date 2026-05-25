from __future__ import annotations

from typing import Any
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from plugins.visibility_os.core.actions import (
    approve_action,
    create_action,
    edit_action,
    get_action,
    list_actions,
    list_audit_log,
    reject_action,
    save_for_later,
)
from plugins.visibility_os.core.executors import execute_approved_action
from plugins.visibility_os.core.impact_picker import generate_daily_plan
from plugins.visibility_os.core.opportunities import get_opportunity, list_opportunities
from plugins.visibility_os.core.opportunity_actions import build_opportunity_detail, draft_action_from_opportunity
from plugins.visibility_os.core.pr_audit import audit_pr_from_opportunity, deep_review_pr_from_opportunity
from plugins.visibility_os.core.scanner import scan_github
from plugins.visibility_os.core.connectors.github import GitHubConnector
from plugins.visibility_os.core import db
from plugins.visibility_os.core.config import get_visibility_config

router = APIRouter()

class ActionCreate(BaseModel):
    proposed_by_agent: str
    action_type: str
    target_system: str
    target_location: str
    title: str
    summary: str
    proposed_payload: dict[str, Any]
    evidence_links: list[dict[str, Any]] = Field(default_factory=list)
    risk_level: str = "low"
    opportunity_id: str | None = None
    impact_score: int | None = None
    visibility_score: int | None = None
    effort_score: int | None = None
    approval_reason: str | None = None

class ActorBody(BaseModel):
    actor: str = "human"
    execute_immediately: bool = False

class EditBody(BaseModel):
    final_payload: dict[str, Any]
    actor: str = "human"

class RejectBody(BaseModel):
    reason: str
    actor: str = "human"

class ScanBody(BaseModel):
    repo: str | None = None

class OpportunityDraftBody(BaseModel):
    action_kind: str
    target_location: str | None = None
    actor: str = "visibility_os"

class OpportunityAuditBody(BaseModel):
    actor: str = "visibility_os"

def _is_github_actions_run_url(url: str | None) -> bool:
    return bool(url and "/actions/runs/" in url)


def _feed_action(action: dict[str, Any]) -> dict[str, Any]:
    item = {"kind": "action", **action}
    opportunity_id = action.get("opportunity_id")
    if not opportunity_id:
        return item
    try:
        opportunity = get_opportunity(opportunity_id)
    except KeyError:
        return item
    source_url = opportunity.get("source_url")
    item["opportunity_source_url"] = source_url
    item["opportunity_title"] = opportunity.get("title")
    item["can_diagnose_ci"] = _is_github_actions_run_url(source_url)
    return item


def _github_repo_allowed(repo: str | None) -> bool:
    return get_visibility_config().github_repo_allowed(repo)


@router.get("/config")
async def visibility_config() -> dict[str, Any]:
    cfg = get_visibility_config()
    return {
        "company_name": cfg.company_name,
        "github_orgs": sorted(cfg.github_orgs),
        "github_repos": cfg.github_repos,
        "default_slack_channel": cfg.default_slack_channel,
    }


@router.get("/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "plugin": "visibility-os"}

@router.get("/feed")
async def feed() -> dict[str, Any]:
    actions = list_actions()
    opportunities = list_opportunities(status="open", limit=50)
    items = []
    for a in actions:
        items.append(_feed_action(a))
    for o in opportunities:
        items.append({"kind": "opportunity", "can_diagnose_ci": _is_github_actions_run_url(o.get("source_url")), **o})
    items.sort(key=lambda x: (x.get("created_at") or x.get("updated_at") or ""), reverse=True)
    return {"items": items, "counts": {"actions": len(actions), "opportunities": len(opportunities)}}

@router.get("/actions")
async def actions(status: str | None = None) -> dict[str, Any]:
    return {"actions": list_actions(status=status)}

@router.post("/actions")
async def post_action(body: ActionCreate) -> dict[str, Any]:
    return create_action(**body.model_dump())

@router.get("/actions/{action_id}")
async def action_detail(action_id: str) -> dict[str, Any]:
    try:
        return get_action(action_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@router.post("/actions/{action_id}/approve")
async def approve(action_id: str, body: ActorBody) -> dict[str, Any]:
    try:
        approved = approve_action(action_id, actor=body.actor)
        if body.execute_immediately:
            return execute_approved_action(action_id, actor=body.actor)
        return approved
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.post("/actions/{action_id}/edit")
async def edit(action_id: str, body: EditBody) -> dict[str, Any]:
    try:
        return edit_action(action_id, final_payload=body.final_payload, actor=body.actor)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.post("/actions/{action_id}/reject")
async def reject(action_id: str, body: RejectBody) -> dict[str, Any]:
    try:
        return reject_action(action_id, reason=body.reason, actor=body.actor)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.post("/actions/{action_id}/save")
async def save(action_id: str, body: ActorBody) -> dict[str, Any]:
    return save_for_later(action_id, actor=body.actor)

@router.post("/actions/{action_id}/execute")
async def execute(action_id: str, body: ActorBody) -> dict[str, Any]:
    try:
        return execute_approved_action(action_id, actor=body.actor)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.get("/audit-log")
async def audit_log(action_id: str | None = None) -> dict[str, Any]:
    return {"events": list_audit_log(action_id=action_id)}

@router.get("/opportunities")
async def opportunities() -> dict[str, Any]:
    return {"opportunities": list_opportunities(limit=100)}

@router.get("/opportunities/{opportunity_id}")
async def opportunity_detail(opportunity_id: str) -> dict[str, Any]:
    try:
        return build_opportunity_detail(opportunity_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@router.post("/opportunities/{opportunity_id}/draft-action")
async def draft_opportunity_action(opportunity_id: str, body: OpportunityDraftBody) -> dict[str, Any]:
    try:
        return draft_action_from_opportunity(opportunity_id, action_kind=body.action_kind, target_location=body.target_location, actor=body.actor)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.post("/opportunities/{opportunity_id}/fix-ci")
async def fix_ci_opportunity(opportunity_id: str, body: ActorBody) -> dict[str, Any]:
    try:
        action = draft_action_from_opportunity(opportunity_id, action_kind="ci_fix_lane", actor=body.actor)
        approve_action(action["id"], actor=body.actor)
        return execute_approved_action(action["id"], actor=body.actor)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.post("/opportunities/{opportunity_id}/audit-pr")
async def audit_pr_opportunity(opportunity_id: str, body: OpportunityAuditBody) -> dict[str, Any]:
    try:
        return audit_pr_from_opportunity(opportunity_id, actor=body.actor)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.post("/opportunities/{opportunity_id}/deep-review-pr")
async def deep_review_pr_opportunity(opportunity_id: str, body: OpportunityAuditBody) -> dict[str, Any]:
    try:
        return deep_review_pr_from_opportunity(opportunity_id, actor=body.actor)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.post("/scan/github")
async def scan(body: ScanBody) -> dict[str, Any]:
    cfg = get_visibility_config()
    if not _github_repo_allowed(body.repo):
        raise HTTPException(status_code=400, detail=f"Visibility OS is restricted to configured GitHub organisations: {cfg.github_scope_label}")
    try:
        return {"opportunities": scan_github(GitHubConnector(repo=body.repo))}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

@router.post("/scan/github/all")
async def scan_all_github() -> dict[str, Any]:
    db.init_db()
    cfg = get_visibility_config()
    repos = cfg.github_repos
    if not repos:
        with db.connect() as conn:
            row = conn.execute("SELECT state_payload FROM connector_state WHERE connector_name = ?", ("github_repos",)).fetchone()
        if row:
            repos = json.loads(row["state_payload"]).get("repos") or []
    repos = [repo for repo in repos if _github_repo_allowed(repo)]
    if not repos:
        raise HTTPException(status_code=400, detail="No configured GitHub repos found. Set VISIBILITY_OS_GITHUB_REPOS and VISIBILITY_OS_GITHUB_ORGS in .env.")
    results = []
    for repo in repos:
        try:
            opportunities = scan_github(GitHubConnector(repo=repo))
            results.append({"repo": repo, "ok": True, "count": len(opportunities)})
        except Exception as exc:
            results.append({"repo": repo, "ok": False, "error": str(exc)})
    return {"results": results, "opportunities": list_opportunities(limit=100)}

@router.get("/connectors")
async def connectors() -> dict[str, Any]:
    db.init_db()
    with db.connect() as conn:
        rows = conn.execute("SELECT connector_name, state_payload, updated_at FROM connector_state ORDER BY connector_name").fetchall()
    return {"connectors": [{"name": r["connector_name"], "state": json.loads(r["state_payload"]), "updated_at": r["updated_at"]} for r in rows]}

@router.post("/daily-plan")
async def daily_plan() -> dict[str, Any]:
    return generate_daily_plan()
