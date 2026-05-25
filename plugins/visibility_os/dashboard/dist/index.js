(function () {
  const sdk = window.__HERMES_PLUGIN_SDK__;
  const plugins = window.__HERMES_PLUGINS__;
  if (!sdk || !plugins) return;
  const React = sdk.React;
  const h = React.createElement;
  const fetchJSON = sdk.fetchJSON;
  const Card = sdk.components.Card;
  const CardHeader = sdk.components.CardHeader;
  const CardTitle = sdk.components.CardTitle;
  const CardContent = sdk.components.CardContent;
  const Badge = sdk.components.Badge;

  function ActionButton(props) {
    const disabled = props && props.disabled;
    const extraClass = props && props.className ? ' ' + props.className : '';
    const className = 'inline-flex items-center justify-center rounded border border-current/20 bg-midground px-3 py-2 text-sm font-semibold leading-none tracking-normal normal-case whitespace-nowrap hover:bg-midground/90 disabled:opacity-50 disabled:cursor-not-allowed' + extraClass;
    const style = Object.assign({ color: '#061512', letterSpacing: 'normal', textTransform: 'none', fontFamily: 'Arial, Helvetica, sans-serif', fontWeight: 700, lineHeight: 1.1 }, props && props.style ? props.style : {});
    return h('button', Object.assign({}, props || {}, { type: (props && props.type) || 'button', disabled: disabled, className: className, style: style }), props && props.children);
  }

  function payloadText(action) {
    const p = action.final_payload || action.proposed_payload || {};
    return p.text || p.body || JSON.stringify(p, null, 2);
  }

  function VisibilityOS() {
    const hooks = sdk.hooks;
    const [feed, setFeed] = hooks.useState({ items: [], counts: {} });
    const [error, setError] = hooks.useState(null);
    const [busy, setBusy] = hooks.useState(false);
    const [selectedOpportunity, setSelectedOpportunity] = hooks.useState(null);
    const [slackTarget, setSlackTarget] = hooks.useState('');
    const [severityFilter, setSeverityFilter] = hooks.useState('all');
    const [sourceFilter, setSourceFilter] = hooks.useState('all');
    const [findingStatus, setFindingStatus] = hooks.useState({});
    const load = hooks.useCallback(function () {
      setBusy(true);
      fetchJSON('/api/plugins/visibility-os/feed')
        .then(setFeed)
        .catch(function (e) { setError(String(e)); })
        .finally(function () { setBusy(false); });
    }, []);
    hooks.useEffect(load, [load]);
    hooks.useEffect(function () {
      fetchJSON('/api/plugins/visibility-os/config')
        .then(function (cfg) { if (cfg && cfg.default_slack_channel) setSlackTarget(cfg.default_slack_channel); })
        .catch(function () {});
    }, []);
    function post(path, body) {
      setBusy(true);
      fetchJSON(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) })
        .then(load)
        .catch(function (e) { setError(String(e)); setBusy(false); });
    }
    function viewOpportunity(id) {
      setBusy(true);
      fetchJSON('/api/plugins/visibility-os/opportunities/' + id)
        .then(function (detail) { setSelectedOpportunity(detail); })
        .catch(function (e) { setError(String(e)); })
        .finally(function () { setBusy(false); });
    }
    function draftOpportunity(detail, actionKind) {
      const body = { action_kind: actionKind, actor: 'human' };
      if (actionKind === 'slack_update' && slackTarget) body.target_location = slackTarget;
      post('/api/plugins/visibility-os/opportunities/' + detail.id + '/draft-action', body);
      setSelectedOpportunity(null);
    }
    function auditOpportunity(detail) {
      post('/api/plugins/visibility-os/opportunities/' + detail.id + '/audit-pr', { actor: 'human' });
      setSelectedOpportunity(null);
    }
    function deepReviewOpportunity(detail) {
      post('/api/plugins/visibility-os/opportunities/' + detail.id + '/deep-review-pr', { actor: 'human' });
      setSelectedOpportunity(null);
    }
    function fixCI(item) {
      const opportunityId = item.opportunity_id || item.id;
      post('/api/plugins/visibility-os/opportunities/' + opportunityId + '/fix-ci', { actor: 'human' });
    }
    function pushBranchNow(item) {
      post('/api/plugins/visibility-os/actions/' + item.id + '/approve', { actor: 'human', execute_immediately: true });
    }
    function scoreLine(detail) {
      return 'Impact ' + detail.impact_score + ' · Visibility ' + detail.visibility_score + ' · Effort ' + detail.effort_score + ' · Safety ' + detail.safety_score + ' · Risk penalty ' + detail.risk_penalty;
    }
    function editPayload(item) {
      const current = payloadText(item);
      const next = window.prompt('Edit reviewed payload before approval', current);
      if (next === null) return;
      const key = (item.proposed_payload && item.proposed_payload.body !== undefined) ? 'body' : 'text';
      post('/api/plugins/visibility-os/actions/' + item.id + '/edit', { actor: 'human', final_payload: { [key]: next } });
    }
    function evidenceLinks(item) {
      const links = item.evidence_links || [];
      if (!links.length) return h('div', { className: 'text-xs text-amber-300' }, 'No evidence links attached');
      return h('div', { className: 'flex gap-2 flex-wrap' }, links.map(function (link, idx) {
        const url = link.url || link.href || String(link);
        return h('a', { key: idx, className: 'text-xs underline text-midground', href: url, target: '_blank' }, link.type ? link.type + ': ' + url : url);
      }));
    }
    function proposedPRView(item) {
      if (item.action_type !== 'github_push_branch') return null;
      const p = item.final_payload || item.proposed_payload || {};
      return h('div', { className: 'rounded border border-emerald-500/30 bg-emerald-500/10 p-4 space-y-3' },
        h('div', { className: 'flex items-center justify-between gap-2 flex-wrap' },
          h('div', null,
            h('div', { className: 'text-sm font-bold text-midground' }, 'Proposed PR'),
            h('div', { className: 'text-xs text-text-secondary' }, 'Hermes prepared this locally. Nothing is pushed until you choose Push branch.')
          ),
          h(Badge, null, p.branch || 'branch pending')
        ),
        h('div', { className: 'grid grid-cols-1 md:grid-cols-2 gap-3 text-xs' },
          h('div', { className: 'rounded bg-black/20 p-2' }, h('div', { className: 'font-semibold text-text-secondary' }, 'Commit message'), h('div', null, p.commit_message || 'not provided')),
          h('div', { className: 'rounded bg-black/20 p-2' }, h('div', { className: 'font-semibold text-text-secondary' }, 'PR title'), h('div', null, p.pr_title || p.commit_message || 'not provided'))
        ),
        p.changed_files && p.changed_files.length && h('div', { className: 'text-xs' }, h('div', { className: 'font-semibold text-text-secondary' }, 'Changed files'), h('ul', { className: 'list-disc pl-4' }, p.changed_files.map(function (f) { return h('li', { key: f }, f); }))),
        p.verification && p.verification.length && h('div', { className: 'text-xs' }, h('div', { className: 'font-semibold text-text-secondary' }, 'Verification'), h('ul', { className: 'list-disc pl-4' }, p.verification.map(function (v) { return h('li', { key: v }, v); }))),
        p.self_audit && h('div', { className: 'text-xs rounded bg-black/20 p-2' }, h('div', { className: 'font-semibold text-text-secondary' }, 'Self-audit'), h('div', null, 'Status: ' + (p.self_audit.audit_status || 'unknown')), p.self_audit.issues_found && h('div', null, 'Issues found: ' + p.self_audit.issues_found.length), p.self_audit.fixes_applied && h('div', null, 'Fixes applied: ' + p.self_audit.fixes_applied.length)),
        p.independent_review && h('div', { className: 'text-xs rounded bg-black/20 p-2' }, h('div', { className: 'font-semibold text-text-secondary' }, 'Independent review'), h('div', null, 'Status: ' + (p.independent_review.review_status || 'unknown')), p.independent_review.findings && h('div', null, 'Findings: ' + p.independent_review.findings.length), p.independent_review.fixes_required && h('div', null, 'Fixes required: ' + p.independent_review.fixes_required.length)),
        h('details', { className: 'text-xs' }, h('summary', { className: 'cursor-pointer font-semibold text-text-secondary' }, 'PR body'), h('pre', { className: 'mt-2 whitespace-pre-wrap rounded bg-black/40 p-3' }, p.pr_body || 'not provided'))
      );
    }
    function actionPayloadView(item) {
      if (item.action_type === 'github_push_branch') return proposedPRView(item);
      return h('details', { className: 'text-xs' },
        h('summary', { className: 'cursor-pointer text-text-secondary' }, 'Raw payload'),
        h('pre', { className: 'mt-2 whitespace-pre-wrap rounded bg-black/40 p-3 text-xs' }, payloadText(item))
      );
    }
    function findingsSummaryView(findings) {
      const counts = findings.reduce(function (acc, f) { acc[f.severity || 'suggestion'] = (acc[f.severity || 'suggestion'] || 0) + 1; return acc; }, { critical: 0, warning: 0, suggestion: 0 });
      return h('div', { className: 'grid grid-cols-3 gap-2 text-xs' },
        ['critical', 'warning', 'suggestion'].map(function (sev) {
          return h('div', { key: sev, className: 'rounded border border-current/10 bg-black/20 p-2' },
            h('div', { className: 'text-lg font-bold' }, counts[sev] || 0),
            h('div', { className: 'text-text-secondary capitalize' }, sev)
          );
        })
      );
    }
    function groupFindingsByFile(findings) {
      return findings.reduce(function (acc, f) {
        const key = f.path || 'unknown';
        (acc[key] = acc[key] || []).push(f);
        return acc;
      }, {});
    }
    function copyFindingComment(f) {
      const text = f.copy_comment || ((f.casual_comment || f.title || 'Finding') + '\n\n' + (f.path || 'unknown') + ':' + (f.line || '?') + '\n\nSuggested change: ' + (f.solution || ''));
      if (navigator.clipboard) navigator.clipboard.writeText(text);
      else window.prompt('Copy review comment', text);
    }
    function markFindingStatus(item, idx, status) {
      const key = item.id + ':' + idx;
      setFindingStatus(function (prev) { return Object.assign({}, prev, { [key]: status }); });
    }
    function findingCard(item, f, idx) {
      const status = findingStatus[item.id + ':' + idx] || f.status || 'open';
      return h('div', { key: idx, className: 'rounded border border-current/10 bg-black/20 p-3 text-xs space-y-2' },
        h('div', { className: 'flex gap-2 flex-wrap items-center' },
          h(Badge, null, f.severity || 'suggestion'),
          h(Badge, null, f.source || 'deterministic'),
          h(Badge, null, status),
          h(Badge, null, (f.path || 'unknown') + ':' + (f.line || '?'))
        ),
        h('div', { className: 'rounded bg-emerald-500/10 border border-emerald-500/20 p-2 text-sm font-medium' }, f.casual_comment || f.title),
        h('details', { className: 'space-y-2' },
          h('summary', { className: 'cursor-pointer text-text-secondary' }, 'Structured detail'),
          h('div', { className: 'font-semibold pt-2' }, f.title),
          h('div', { className: 'text-text-secondary' }, f.detail),
          h('div', null, h('span', { className: 'text-text-secondary' }, 'Suggested fix: '), f.solution)
        ),
        f.code && h('pre', { className: 'whitespace-pre-wrap rounded bg-black/40 p-2 border-l-2 border-midground' }, f.code),
        h('div', { className: 'flex gap-2 flex-wrap' },
          f.github_diff_url && h('a', { className: 'text-xs underline text-midground', href: f.github_diff_url, target: '_blank' }, 'Open diff line'),
          h(ActionButton, { onClick: function () { copyFindingComment(f); } }, 'Copy comment'),
          h(ActionButton, { onClick: function () { markFindingStatus(item, idx, 'checked'); } }, 'Mark checked'),
          h(ActionButton, { onClick: function () { markFindingStatus(item, idx, 'needs follow-up'); } }, 'Needs follow-up')
        )
      );
    }
    function findingsView(item) {
      const p = item.final_payload || item.proposed_payload || {};
      const findings = p.findings || [];
      if (!findings.length) return null;
      const filtered = findings.filter(function (f) {
        return (severityFilter === 'all' || f.severity === severityFilter) && (sourceFilter === 'all' || (f.source || 'deterministic') === sourceFilter);
      });
      const bySource = {
        agentic: filtered.filter(function (f) { return f.source === 'agentic'; }),
        deterministic: filtered.filter(function (f) { return (f.source || 'deterministic') !== 'agentic'; })
      };
      function sourceSection(title, rows) {
        const grouped = groupFindingsByFile(rows);
        return h('div', { className: 'space-y-2' },
          h('div', { className: 'text-xs font-bold text-midground' }, title + ' (' + rows.length + ')'),
          Object.keys(grouped).sort().map(function (file) {
            return h('details', { key: file, open: true, className: 'rounded border border-current/10 p-2 space-y-2' },
              h('summary', { className: 'cursor-pointer text-xs font-semibold' }, file + ' · ' + grouped[file].length + ' finding(s)'),
              h('div', { className: 'space-y-2 pt-2' }, grouped[file].map(function (f) { return findingCard(item, f, findings.indexOf(f)); }))
            );
          })
        );
      }
      return h('div', { className: 'space-y-3 rounded border border-current/10 p-3' },
        h('div', { className: 'flex items-center justify-between gap-2 flex-wrap' },
          h('div', { className: 'text-sm font-bold text-midground' }, 'Audit findings'),
          h('div', { className: 'flex gap-2 flex-wrap' },
            h('select', { className: 'rounded bg-black/40 px-2 py-1 text-xs border border-current/20', value: severityFilter, onChange: function (e) { setSeverityFilter(e.target.value); } }, ['all','critical','warning','suggestion'].map(function (v) { return h('option', { key: v, value: v }, 'severity: ' + v); })),
            h('select', { className: 'rounded bg-black/40 px-2 py-1 text-xs border border-current/20', value: sourceFilter, onChange: function (e) { setSourceFilter(e.target.value); } }, ['all','agentic','deterministic'].map(function (v) { return h('option', { key: v, value: v }, 'source: ' + v); }))
          )
        ),
        findingsSummaryView(findings),
        p.review_notes && p.review_notes.length && h('details', { className: 'rounded bg-black/20 p-2 text-xs' }, h('summary', { className: 'cursor-pointer font-semibold' }, 'Review notes'), h('ul', { className: 'list-disc pl-4 pt-2 space-y-1' }, p.review_notes.map(function (n, i) { return h('li', { key: i }, n); }))),
        sourceSection('Agentic findings', bySource.agentic),
        sourceSection('Deterministic findings', bySource.deterministic)
      );
    }
    return h('div', { className: 'h-full min-h-0 overflow-auto p-6 space-y-4' },
      h('div', { className: 'flex items-center justify-between gap-4' },
        h('div', null,
          h('h1', { className: 'text-2xl font-bold text-midground' }, 'Hermes Visibility OS'),
          h('p', { className: 'text-sm text-text-secondary' }, 'Evidence-backed opportunities and human-approved write actions.')
        ),
        h('div', { className: 'flex gap-2 flex-wrap justify-end' },
          h(ActionButton, { onClick: load, disabled: busy }, busy ? 'Loading…' : 'Refresh'),
          h(ActionButton, { onClick: function () { post('/api/plugins/visibility-os/scan/github/all', {}); }, disabled: busy }, 'Scan GitHub Repos'),
          h(ActionButton, { onClick: function () { post('/api/plugins/visibility-os/daily-plan', {}); }, disabled: busy }, 'Generate Daily Plan')
        )
      ),
      error && h('div', { className: 'rounded border border-red-500/40 p-3 text-red-300' }, error),
      selectedOpportunity && h(Card, { className: 'border-emerald-500/40' },
        h(CardHeader, null, h(CardTitle, null, 'Opportunity detail: ' + selectedOpportunity.title)),
        h(CardContent, { className: 'space-y-3' },
          h('div', { className: 'flex gap-2 flex-wrap' },
            h(Badge, null, selectedOpportunity.source_repo || selectedOpportunity.source_system),
            h(Badge, null, selectedOpportunity.category),
            h(Badge, null, 'Priority ' + selectedOpportunity.priority_score)
          ),
          h('p', { className: 'text-sm text-text-secondary' }, selectedOpportunity.why_it_matters || selectedOpportunity.description),
          h('p', { className: 'text-xs text-text-secondary' }, scoreLine(selectedOpportunity)),
          h('pre', { className: 'whitespace-pre-wrap rounded bg-black/40 p-3 text-xs' }, selectedOpportunity.score_explanation),
          evidenceLinks(selectedOpportunity),
          h('div', { className: 'flex items-center gap-2 flex-wrap' },
            h('label', { className: 'text-xs text-text-secondary' }, 'Slack target'),
            h('input', { className: 'rounded bg-black/40 px-2 py-1 text-xs border border-current/20', value: slackTarget, onChange: function (e) { setSlackTarget(e.target.value); } })
          ),
          h('div', { className: 'flex gap-2 flex-wrap' },
            selectedOpportunity.source_url && selectedOpportunity.source_url.indexOf('/pull/') !== -1 && h(ActionButton, { disabled: busy, onClick: function () { auditOpportunity(selectedOpportunity); } }, 'Audit PR'),
            selectedOpportunity.source_url && selectedOpportunity.source_url.indexOf('/pull/') !== -1 && h(ActionButton, { disabled: busy, onClick: function () { deepReviewOpportunity(selectedOpportunity); } }, 'Deep Review PR'),
            (selectedOpportunity.recommended_actions || []).map(function (a) {
              return h(ActionButton, { key: a.action_kind, disabled: busy, onClick: function () { draftOpportunity(selectedOpportunity, a.action_kind); } }, a.label);
            }),
            h(ActionButton, { disabled: busy, onClick: function () { setSelectedOpportunity(null); } }, 'Close')
          )
        )
      ),
      h('div', { className: 'grid grid-cols-1 md:grid-cols-3 gap-3' },
        h(Card, null, h(CardContent, { className: 'p-4' }, h('div', { className: 'text-2xl font-bold' }, feed.counts.actions || 0), h('div', { className: 'text-xs text-text-secondary' }, 'Actions'))),
        h(Card, null, h(CardContent, { className: 'p-4' }, h('div', { className: 'text-2xl font-bold' }, feed.counts.opportunities || 0), h('div', { className: 'text-xs text-text-secondary' }, 'Opportunities'))),
        h(Card, null, h(CardContent, { className: 'p-4' }, h('div', { className: 'text-2xl font-bold' }, (feed.items || []).filter(i => i.status === 'approved').length), h('div', { className: 'text-xs text-text-secondary' }, 'Approved')))
      ),
      h('div', { className: 'space-y-3' }, (feed.items || []).map(function (item) {
        if (item.kind === 'opportunity') {
          return h(Card, { key: item.id, className: 'border-current/15' },
            h(CardHeader, null, h(CardTitle, null, item.title)),
            h(CardContent, { className: 'space-y-2' },
              h('div', { className: 'flex gap-2 flex-wrap' }, h(Badge, null, 'Opportunity'), h(Badge, null, 'Priority ' + item.priority_score), h(Badge, null, item.category || item.source_system)),
              h('p', { className: 'text-sm text-text-secondary' }, item.description),
              item.source_url && h('a', { className: 'text-sm underline text-midground', href: item.source_url, target: '_blank' }, item.source_url),
              h('div', { className: 'flex gap-2 flex-wrap pt-2' },
                item.can_diagnose_ci ? h(ActionButton, { disabled: busy, onClick: function () { fixCI(item); }, className: 'border-emerald-500/50' }, 'Fix CI') : h(ActionButton, { disabled: busy, onClick: function () { viewOpportunity(item.id); } }, 'View detail / draft action')
              )
            )
          );
        }
        return h(Card, { key: item.id, className: 'border-current/15' },
          h(CardHeader, null, h(CardTitle, null, item.title)),
          h(CardContent, { className: 'space-y-3' },
            h('div', { className: 'flex gap-2 flex-wrap' }, h(Badge, null, item.status), h(Badge, null, item.target_system), h(Badge, null, item.risk_level + ' risk')),
            h('p', { className: 'text-sm text-text-secondary' }, item.summary),
            actionPayloadView(item),
            findingsView(item),
            evidenceLinks(item),
            h('div', { className: 'flex gap-2 flex-wrap' },
              item.action_type === 'github_push_branch' && h(ActionButton, { disabled: busy || !['queued','edited_by_human'].includes(item.status), onClick: function () { pushBranchNow(item); }, className: 'border-emerald-500/50' }, 'Push branch'),
              item.action_type !== 'github_push_branch' && h(ActionButton, { disabled: busy || !['queued','edited_by_human'].includes(item.status), onClick: function () { editPayload(item); } }, 'Edit'),
              item.action_type !== 'github_push_branch' && h(ActionButton, { disabled: busy || !['queued','edited_by_human'].includes(item.status), onClick: function () { post('/api/plugins/visibility-os/actions/' + item.id + '/approve', { actor: 'human' }); } }, 'Approve'),
              item.action_type !== 'github_push_branch' && h(ActionButton, { disabled: busy || item.status !== 'approved', onClick: function () { post('/api/plugins/visibility-os/actions/' + item.id + '/execute', { actor: 'human' }); } }, 'Execute'),
              h(ActionButton, { disabled: busy || ['rejected','executed'].includes(item.status), onClick: function () { post('/api/plugins/visibility-os/actions/' + item.id + '/save', { actor: 'human' }); } }, 'Save for later'),
              h(ActionButton, { disabled: busy || ['rejected','executed'].includes(item.status), onClick: function () { post('/api/plugins/visibility-os/actions/' + item.id + '/reject', { actor: 'human', reason: 'Rejected from dashboard' }); } }, 'Reject')
            )
          )
        );
      }))
    );
  }
  plugins.register('visibility-os', VisibilityOS);
})();
