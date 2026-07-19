# Hermes Visibility OS

Visibility OS is a Hermes dashboard plugin for engineering-lead visibility. It scans configured GitHub repositories for actionable issues, PRs, and failing CI, then drafts Slack or GitHub updates behind a human approval queue.

## Companion X/Twitter Visibility

For public launch, support, or incident profiles, pair Visibility OS with
[Hermes Tweet](https://github.com/Xquik-dev/hermes-tweet). Hermes Tweet can
collect X/Twitter account, post, or trend context inside Hermes, while
Visibility OS can turn that context into reviewed Slack or GitHub update drafts
behind the existing approval queue. Hermes Tweet is a third-party project
maintained by Xquik-dev, not by this repository.

Xquik is an independent third-party service. Not affiliated with X Corp.
"Twitter" and "X" are trademarks of X Corp.

## Features

- GitHub repository scanning for issues, pull requests, and CI failures
- Opportunity scoring based on impact, visibility, effort, safety, and risk
- Human-approved Slack and GitHub action drafts
- One-click Fix CI lane that prepares a local branch, self-audits, runs an independent fresh-session review, then queues a separate Push branch decision
- One-click Fix Issue lanes for GitHub issues, with specific Fix Docs, Fix Bug, and Deflake Test labels using the same local-branch, self-audit, independent-review, and push-gate flow
- One-click Fix PR CI and Prepare Handoff Branch lanes for PR-based opportunities
- Fresh-session Review PR lane that queues a separate human-approved GitHub review/comment
- Environment-scoped safety gates for allowed GitHub orgs and repos

## Install in Hermes

Copy or symlink `plugins/visibility_os` into your Hermes profile plugin directory, then restart Hermes or reload plugins.

## Configuration

Copy the example environment file into your Hermes profile `.env` and edit it for your organisation:

```bash
cp plugins/visibility_os/.env.example ~/.hermes/.env
```

Key settings:

- `VISIBILITY_OS_COMPANY_NAME`: label used in prompts, for example `Acme Robotics`
- `VISIBILITY_OS_GITHUB_ORGS`: comma-separated GitHub org owners Visibility OS may inspect or modify
- `VISIBILITY_OS_GITHUB_REPOS`: comma-separated `owner/repo` list scanned by Visibility OS
- `VISIBILITY_OS_DEFAULT_SLACK_CHANNEL`: default Slack destination for drafted updates
- `SLACK_BOT_TOKEN`: required only when executing Slack message actions

GitHub access uses the local `gh` CLI session:

```bash
gh auth login
gh auth refresh -h github.com -s repo -s read:org -s workflow
```

## Safety model

- GitHub actions and Fix CI lanes reject repositories outside `VISIBILITY_OS_GITHUB_ORGS`.
- If `VISIBILITY_OS_GITHUB_REPOS` is set, scans and actions are restricted to that explicit repo list.
- Fix CI, PR CI, Fix Docs, Fix Bug, Deflake Test, and WIP handoff lanes prepare local branches only. They do not push, merge, or deploy.
- Independent fresh Hermes sessions review prepared branches before a push action is queued.
- Review PR uses a fresh Hermes session and queues a separate human-approved GitHub comment/review action.
- Pushing remains a separate explicit human decision.

## Tests

```bash
PYTHONPATH=. pytest -q tests/plugins/visibility_os
```

## Project layout

- `plugins/visibility_os/`: Hermes dashboard plugin and backend logic
- `tests/plugins/visibility_os/`: plugin test suite
- `docs/plans/`: implementation notes
