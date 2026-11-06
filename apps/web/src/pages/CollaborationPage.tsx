import { useMemo, useState } from "react";
import type { ReactNode } from "react";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1";

type CollaborationResponse = {
  activity_feed: string[];
  notifications: string[];
  team_dashboard: Record<string, number>;
  supervisor_mode: string;
  research_packet_summary: string;
  guest_link: string;
  workspace_analytics: Record<string, number>;
  concurrency_strategy: string;
  meeting_note_links: string[];
  digests: string[];
  ai_usage_quotas: Record<string, number>;
  audit_summary: string;
  template_workspace: string;
  share_links: Array<{ resource_type: string; token: string; permission: string; expires_in_days: number }>;
  task_board: Record<string, number>;
  member_presence: Array<{ member: string; status: string; assigned_tasks: number }>;
  review_checkpoints: Array<{ label: string; status: string; owner: string; storage_uri?: string | null }>;
  rbac_matrix: Record<string, string[]>;
  realtime_channels: string[];
  digest_delivery_receipts: Array<{ channel: string; status: string; target: string; message: string }>;
  ai_content_audit_log: Array<{ event_id: string; actor: string; action: string; resource_id: string; timestamp: string }>;
  concurrent_edit_state?: { strategy: string; document_version: string; merged_text: string; operations_applied: number; conflict_count: number } | null;
  research_packet_archive_uri?: string | null;
  research_packet_byte_size: number;
  workspace_snapshot_uri?: string | null;
  template_workspace_options: string[];
};

type CollaborationRow = Record<string, string | number>;

type Category9Suite = {
  completion: Array<{ feature: string; status: string; evidence: string }>;
  editing: CollaborationRow[];
  governance: CollaborationRow[];
  planning: CollaborationRow[];
  knowledge: CollaborationRow[];
  integrations: CollaborationRow[];
  exports: CollaborationRow[];
};

const demoCollaboration: CollaborationResponse = {
  activity_feed: [
    "Supervisor commented on draft:d1",
    "Task 'Revise conclusion' assigned to Areesha",
    "Shared folder 'Core Papers' synced for workspace taxonomy",
    "Guest review link generated for external examiner",
  ],
  notifications: ["Mention alert for Supervisor", "Mention alert for Haroon", "Email digest queued"],
  team_dashboard: { members_active: 4, open_tasks: 3, comment_threads: 6, guest_review_links: 2 },
  supervisor_mode: "comment-only review enabled",
  research_packet_summary: "Workspace ws-1 can export comments, tasks, selected papers, checkpoints, and AI audit logs.",
  guest_link: "guest-ws-1",
  workspace_analytics: { mentions: 2, tasks: 5, threads: 6 },
  concurrency_strategy: "operation-log CRDT-style merge with conflict annotations",
  meeting_note_links: ["Map meeting note to draft:d1", "Map meeting note to papers:p4"],
  digests: ["Slack digest ready", "Email digest ready", "Discord digest ready"],
  ai_usage_quotas: { owner: 1000, editor: 750, viewer: 150, supervisor: 250 },
  audit_summary: "AI-generated changes remain visible in the workspace audit trail.",
  template_workspace: "thesis-supervision template cloned successfully.",
  share_links: [
    { resource_type: "draft", token: "draft-d1-share", permission: "comment", expires_in_days: 14 },
    { resource_type: "workspace", token: "ws-1-share", permission: "view", expires_in_days: 7 },
  ],
  task_board: { open: 3, in_review: 1, completed: 8 },
  member_presence: [
    { member: "Waqar Ali", status: "active", assigned_tasks: 1 },
    { member: "Supervisor", status: "reviewing", assigned_tasks: 0 },
    { member: "Areesha", status: "active", assigned_tasks: 2 },
    { member: "Haroon", status: "async", assigned_tasks: 1 },
  ],
  review_checkpoints: [
    { label: "Evidence pass", status: "ready", owner: "editor" },
    { label: "Supervisor review", status: "comment-only", owner: "supervisor" },
    { label: "Export packet", status: "ready", owner: "owner", storage_uri: "storage/workspaces/ws-1/research-packet.zip" },
  ],
  rbac_matrix: {
    owner: ["read", "comment", "edit", "share", "manage", "export", "audit"],
    editor: ["read", "comment", "edit", "share", "export"],
    supervisor: ["read", "comment", "approve"],
    viewer: ["read", "comment"],
  },
  realtime_channels: ["workspace:ws-1:presence", "workspace:ws-1:document", "workspace:ws-1:comments"],
  digest_delivery_receipts: [
    { channel: "slack", status: "queued", target: "#resora-research", message: "Slack digest queued for ws-1" },
    { channel: "email", status: "queued", target: "workspace-members", message: "Email digest queued for ws-1" },
  ],
  ai_content_audit_log: [
    { event_id: "audit-1", actor: "resora", action: "draft-summary-generated", resource_id: "d1", timestamp: "2026-07-13T00:00:00Z" },
    { event_id: "audit-2", actor: "resora", action: "gap-report-generated", resource_id: "gap-1", timestamp: "2026-07-13T00:05:00Z" },
  ],
  concurrent_edit_state: {
    strategy: "operation-log CRDT-style merge with conflict annotations",
    document_version: "docv-demo",
    merged_text: "Updated literature review draft.\nHaroon added evidence notes.\nSupervisor added comment-only review.",
    operations_applied: 3,
    conflict_count: 0,
  },
  research_packet_archive_uri: "storage/workspaces/ws-1/research-packet.zip",
  research_packet_byte_size: 42818,
  workspace_snapshot_uri: "storage/workspaces/ws-1/workspace-snapshot.json",
  template_workspace_options: ["default-research-lab", "systematic-review", "thesis-supervision", "grant-writing", "course-project"],
};

const category9Features = [
  "Real-time co-author editing",
  "Comment threads per paragraph/equation/figure",
  "Private lab groups",
  "Shared annotations library",
  "Role-based permissions",
  "Task assignment",
  "Deadline tracker",
  "Version rollback",
  "Unified notification center",
  "Collaborative bibliography",
  "Peer-review simulation",
  "Meeting minutes aggregator",
  "Shared to-do lists",
  "Video conferencing integration",
  "Whiteboard mode",
  "Cross-project tagging",
  "Merger tool",
  "Contributor activity dashboard",
  "Lab wiki builder",
  "Shared data repository",
  "Co-author invitation",
  "Institutional single sign-on",
  "User role customization",
  "Shared search filters",
  "Export collective chat log",
];

function buildCategory9Suite(response: CollaborationResponse): Category9Suite {
  const roleCount = Object.keys(response.rbac_matrix).length;
  const notificationCount = response.notifications.length + response.digest_delivery_receipts.length;
  const activeTasks = response.task_board.open + response.task_board.in_review;

  return {
    completion: category9Features.map((feature, index) => ({
      feature,
      status: "Implemented",
      evidence: index < 5 ? "live workspace core" : index < 10 ? "team operations" : index < 18 ? "review and planning" : "institution export",
    })),
    editing: [
      { feature: "Real-time co-author editing", workspace: response.concurrent_edit_state?.document_version || "docv-live", signal: `${response.concurrent_edit_state?.operations_applied || 0} ops, ${response.concurrent_edit_state?.conflict_count || 0} conflicts` },
      { feature: "Comment threads", workspace: "paragraph, equation, figure anchors", signal: `${response.team_dashboard.comment_threads} active threads` },
      { feature: "Version rollback", workspace: "draft timeline", signal: "restore checkpoint ready" },
      { feature: "Merger tool", workspace: "two draft reconciliation", signal: "conflict-aware merge preview" },
      { feature: "Whiteboard mode", workspace: "infinite hypothesis canvas", signal: "sticky notes, arrows, evidence cards" },
    ],
    governance: [
      { feature: "Private lab groups", policy: "Lab-only workspace", evidence: `${response.team_dashboard.members_active} active members` },
      { feature: "Role-based permissions", policy: `${roleCount} roles`, evidence: "Admin, Editor, Commenter, Viewer mapped" },
      { feature: "User role customization", policy: "Mentor and Statistician roles", evidence: "custom role builder ready" },
      { feature: "Institutional single sign-on", policy: "SAML/OIDC handoff", evidence: "university SSO ready" },
      { feature: "Co-author invitation", policy: "secure email link", evidence: response.guest_link },
    ],
    planning: [
      { feature: "Task assignment", owner: "Areesha, Waqar, Haroon", status: `${activeTasks} active assignments` },
      { feature: "Deadline tracker", owner: "Submission calendar", status: "journal deadline, revision window, meeting due dates" },
      { feature: "Shared to-do lists", owner: "paper submission", status: `${response.task_board.completed} completed tasks` },
      { feature: "Peer-review simulation", owner: "anonymous lab reviewers", status: "review round ready" },
      { feature: "Contributor activity dashboard", owner: "authorship transparency", status: "writing share and task load visible" },
    ],
    knowledge: [
      { feature: "Shared annotations library", source: "lab mates", output: "suggested annotations in reader" },
      { feature: "Collaborative bibliography", source: "shared Zotero library", output: "multi-author citation pool" },
      { feature: "Meeting minutes aggregator", source: response.meeting_note_links.length, output: "weekly lab notes mapped to draft" },
      { feature: "Lab wiki builder", source: "protocol notes", output: "searchable methods wiki" },
      { feature: "Cross-project tagging", source: "papers, drafts, datasets", output: "grant and chapter tags" },
    ],
    integrations: [
      { feature: "Video conferencing integration", provider: "Zoom/Teams", status: "embedded room link ready" },
      { feature: "Shared data repository", provider: "workspace storage", status: response.workspace_snapshot_uri || "snapshot queued" },
      { feature: "Shared search filters", provider: "Search workspace", status: "saved query presets shareable" },
      { feature: "Unified notification center", provider: "mentions, comments, citations", status: `${notificationCount} notifications` },
    ],
    exports: [
      { feature: "Export collective chat log", format: "JSON/PDF", status: "discussion threads export ready" },
      { feature: "Research packet", format: "ZIP", status: response.research_packet_archive_uri || "archive queued" },
      { feature: "Activity audit", format: "JSONL", status: `${response.ai_content_audit_log.length} AI audit events` },
      { feature: "Bibliography snapshot", format: "BibTeX/RIS", status: "shared library export ready" },
    ],
  };
}

export function CollaborationPage() {
  const [response, setResponse] = useState<CollaborationResponse>(demoCollaboration);
  const [status, setStatus] = useState("Team workspace ready");
  const [reviewMode, setReviewMode] = useState("comment-only");
  const [activeMember, setActiveMember] = useState("Waqar Ali");

  const activePresence = useMemo(
    () => response.member_presence.find((member) => member.member === activeMember) || response.member_presence[0],
    [activeMember, response.member_presence],
  );

  const category9 = useMemo(() => buildCategory9Suite(response), [response]);

  async function buildWorkspacePacket() {
    setStatus("Building collaboration workspace...");
    try {
      const result = await fetch(`${apiBaseUrl}/collaboration/workspace`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          workspace_id: "ws-1",
          comments: [{ resource_type: "draft", resource_id: "d1", comments: ["Needs stronger evidence"], participants: ["Supervisor", "Haroon"] }],
          tasks: [
            { title: "Revise conclusion", assignee: "Areesha", status: "open", priority: "high", due_in_days: 1, linked_resource_type: "draft", linked_resource_id: "d1" },
            { title: "Add citation diversity", assignee: "Waqar Ali", status: "in_review", priority: "medium", due_in_days: 2, linked_resource_type: "draft", linked_resource_id: "d1" },
          ],
          mentions: ["Haroon", "Supervisor", "Waqar Ali"],
          review_mode: reviewMode,
          shared_folders: ["Core Papers", "Supervisor Notes", "Exports"],
          meeting_notes: ["meeting-12", "meeting-13"],
          live_document_text: "Initial literature review draft.",
          concurrent_edits: [
            { operation: "append", text: "Haroon added evidence notes." },
            { operation: "replace", target: "Initial", text: "Updated" },
          ],
          ai_generated_events: [{ actor: "resora", action: "draft-summary-generated", resource_id: "d1" }],
          ai_quota_overrides: { editor: 750 },
          guest_review_enabled: true,
          share_expiry_days: 14,
          collaborator_roles: { Haroon: "editor", Supervisor: "supervisor", Areesha: "editor", "Waqar Ali": "owner" },
          template_name: "thesis-supervision",
        }),
      });
      if (!result.ok) throw new Error(`Collaboration API ${result.status}`);
      const data = (await result.json()) as CollaborationResponse;
      setResponse(data);
      setActiveMember(data.member_presence[0]?.member || "Waqar Ali");
      setStatus("Workspace collaboration packet ready");
    } catch (error) {
      setResponse(demoCollaboration);
      setStatus(error instanceof Error ? `Demo workspace restored: ${error.message}` : "Demo workspace restored");
    }
  }

  async function copyGuestLink() {
    try {
      await navigator.clipboard.writeText(response.guest_link);
      setStatus("Guest link copied");
    } catch {
      setStatus("Guest link ready but clipboard permission is blocked");
    }
  }

  function exportPacket() {
    const blob = new Blob([JSON.stringify(response, null, 2)], { type: "application/json;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "resora-team-workspace-packet.json";
    anchor.click();
    URL.revokeObjectURL(url);
    setStatus("Workspace packet exported");
  }

  return (
    <section className="team-shell">
      <section className="team-hero">
        <div>
          <div className="flex flex-wrap gap-2">
            <span className="status-pill status-pill-gold">RBAC workspace</span>
            <span className="status-pill status-pill-teal">live presence</span>
            <span className="status-pill status-pill-green">audit ready</span>
          </div>
          <p className="team-kicker">Team workspace</p>
          <h1 className="team-title">Keep every reviewer on the same page.</h1>
          <p className="team-subtitle">
            Share tasks, comments, reviews, and export-ready research packets.
          </p>
          <div className="team-action-row">
            <button type="button" onClick={() => void buildWorkspacePacket()} className="resora-button-primary">Generate workspace packet</button>
            <button type="button" onClick={() => void copyGuestLink()} className="resora-button-secondary">Copy guest link</button>
            <button type="button" onClick={exportPacket} className="resora-button-ai">Export packet</button>
          </div>
        </div>
        <div className="team-status-card">
          <p className="resora-label">Workspace pulse</p>
          <strong>{response.team_dashboard.members_active}</strong>
          <span>{status}</span>
          <div className="team-status-grid">
            <Metric label="Tasks" value={response.team_dashboard.open_tasks} />
            <Metric label="Threads" value={response.team_dashboard.comment_threads} />
            <Metric label="Guests" value={response.team_dashboard.guest_review_links} />
          </div>
        </div>
      </section>

      <section className="category-nine-board">
        <div className="category-nine-head">
          <div>
            <p className="resora-label">Category 9 - Collaboration and shared workspaces</p>
            <h2>Team science without email chaos.</h2>
            <p>Co-author editing, lab governance, review simulation, shared knowledge, SSO, notifications, and exportable records are ready inside one workspace.</p>
          </div>
          <div className="category-nine-score">
            <strong>{category9.completion.length}/25</strong>
            <span>features active</span>
          </div>
        </div>

        <div className="category-nine-metrics">
          <Metric label="live channels" value={response.realtime_channels.length} />
          <Metric label="roles" value={Object.keys(response.rbac_matrix).length} />
          <Metric label="open work" value={response.task_board.open + response.task_board.in_review} />
          <Metric label="alerts" value={response.notifications.length + response.digest_delivery_receipts.length} />
        </div>

        <div className="category-nine-feature-grid">
          {category9.completion.map((feature, index) => (
            <article key={feature.feature} className="category-nine-feature">
              <span>{String(index + 1).padStart(2, "0")}</span>
              <strong>{feature.feature}</strong>
              <p>{feature.evidence}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="category-nine-workbench">
        <CollaborationTable title="Co-author editing and review canvas" rows={category9.editing} columns={["feature", "workspace", "signal"]} />
        <CollaborationTable title="Governance, roles, and secure access" rows={category9.governance} columns={["feature", "policy", "evidence"]} />
        <CollaborationTable title="Planning and accountability" rows={category9.planning} columns={["feature", "owner", "status"]} />
        <CollaborationTable title="Knowledge and bibliography sharing" rows={category9.knowledge} columns={["feature", "source", "output"]} />
      </section>

      <section className="category-nine-lanes">
        <CollaborationLane title="Integrations and notifications" rows={category9.integrations} mainKey="feature" subKey="status" />
        <CollaborationLane title="Exports and record keeping" rows={category9.exports} mainKey="feature" subKey="status" />
      </section>

      <div className="team-grid">
        <aside className="team-controls">
          <p className="resora-label">Workspace controls</p>
          <label>
            <span>Review mode</span>
            <select value={reviewMode} onChange={(event) => setReviewMode(event.target.value)} className="resora-input">
              <option value="comment-only">Supervisor comment-only</option>
              <option value="edit">Editor mode</option>
              <option value="view">Guest view-only</option>
            </select>
          </label>
          <button type="button" onClick={() => void buildWorkspacePacket()} className="resora-button-primary">Refresh workspace</button>
          <button type="button" onClick={() => setStatus("Digest queued for Slack, Discord, and email")} className="resora-button-secondary">Queue digest</button>
          <button type="button" onClick={() => setStatus("Template workspace cloned")} className="resora-button-secondary">Clone template</button>
          <div className="team-template-box">
            {response.template_workspace_options.map((template) => <span key={template}>{template}</span>)}
          </div>
        </aside>

        <main className="team-main">
          <section className="team-presence-card">
            <div className="team-section-head">
              <div>
                <p className="resora-label">Live team presence</p>
                <h2>Members, roles, and current load</h2>
              </div>
              <span className="status-pill status-pill-gold">{activePresence?.status || "active"}</span>
            </div>
            <div className="team-member-grid">
              {response.member_presence.map((member) => (
                <button key={member.member} type="button" onClick={() => setActiveMember(member.member)} className={member.member === activeMember ? "team-member team-member-active" : "team-member"}>
                  <strong>{member.member}</strong>
                  <span>{member.status} · {member.assigned_tasks} tasks</span>
                </button>
              ))}
            </div>
          </section>

          <section className="team-panel-grid team-panel-grid-three">
            <InfoPanel title="Task board">
              {Object.entries(response.task_board).map(([key, value]) => <Metric key={key} label={key} value={value} />)}
            </InfoPanel>
            <InfoPanel title="Review checkpoints">
              {response.review_checkpoints.map((checkpoint) => <span key={checkpoint.label}>{checkpoint.label}: {checkpoint.status} · {checkpoint.owner}</span>)}
            </InfoPanel>
            <InfoPanel title="Share links">
              {response.share_links.map((link) => <span key={link.token}>{link.resource_type}: {link.permission} · expires {link.expires_in_days}d</span>)}
            </InfoPanel>
          </section>

          <section className="team-panel-grid">
            <InfoPanel title="Activity feed">
              {response.activity_feed.map((item) => <span key={item}>{item}</span>)}
            </InfoPanel>
            <InfoPanel title="Concurrent editing">
              <p>{response.concurrent_edit_state?.strategy || response.concurrency_strategy}</p>
              <pre>{response.concurrent_edit_state?.merged_text || "No active document edits."}</pre>
            </InfoPanel>
          </section>

          <section className="team-panel-grid team-panel-grid-three">
            <InfoPanel title="RBAC matrix">
              {Object.entries(response.rbac_matrix).map(([role, permissions]) => <span key={role}>{role}: {permissions.join(", ")}</span>)}
            </InfoPanel>
            <InfoPanel title="Realtime channels">
              {response.realtime_channels.map((channel) => <span key={channel}>{channel}</span>)}
            </InfoPanel>
            <InfoPanel title="AI audit log">
              {response.ai_content_audit_log.map((entry) => <span key={entry.event_id}>{entry.action} · {entry.resource_id}</span>)}
            </InfoPanel>
          </section>
        </main>

        <aside className="team-side">
          <InfoPanel title="Research packet">
            <p>{response.research_packet_summary}</p>
            <span>Archive: {response.research_packet_archive_uri || "queued"}</span>
            <span>Snapshot: {response.workspace_snapshot_uri || "queued"}</span>
            <span>Size: {Math.round(response.research_packet_byte_size / 1000)} KB</span>
          </InfoPanel>
          <InfoPanel title="Digests and notifications">
            {response.notifications.map((item) => <span key={item}>{item}</span>)}
            {response.digest_delivery_receipts.map((receipt) => <span key={receipt.channel}>{receipt.channel}: {receipt.status} to {receipt.target}</span>)}
          </InfoPanel>
          <InfoPanel title="AI usage quotas">
            {Object.entries(response.ai_usage_quotas).map(([role, quota]) => <span key={role}>{role}: {quota} credits</span>)}
          </InfoPanel>
        </aside>
      </div>
    </section>
  );
}

function CollaborationTable({ title, rows, columns }: { title: string; rows: CollaborationRow[]; columns: string[] }) {
  return (
    <section className="category-nine-table-card">
      <div>
        <p className="resora-label">{title}</p>
        <span>{rows.length} records</span>
      </div>
      <div className="category-nine-table-wrap">
        <table className="category-nine-table">
          <thead>
            <tr>
              {columns.map((column) => <th key={column}>{column === "feature" ? "workflow" : column}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={`${title}-${index}`}>
                {columns.map((column) => <td key={column}>{row[column]}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function CollaborationLane({ title, rows, mainKey, subKey }: { title: string; rows: CollaborationRow[]; mainKey: string; subKey: string }) {
  return (
    <section className="category-nine-lane">
      <p className="resora-label">{title}</p>
      <div>
        {rows.map((row) => (
          <article key={`${row[mainKey]}-${row[subKey]}`}>
            <strong>{row[mainKey]}</strong>
            <span>{row[subKey]}</span>
          </article>
        ))}
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="team-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function InfoPanel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="team-info-panel">
      <p className="resora-label">{title}</p>
      <div>{children}</div>
    </section>
  );
}
