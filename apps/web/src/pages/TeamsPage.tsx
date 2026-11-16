/** Teams: shared projects, supervisor reviews, members & invites, activity and pooled usage. */
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, NavLink, Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import type { SearchCopyKey, SearchT } from "./search/copy";
import { libraryApi, type LibraryItem } from "./library/libraryApi";
import { BackGlyph, CheckGlyph, ConfirmButton, CopyGlyph, EmptyState, ErrorLine, FolderGlyph, PlusGlyph, Select, SkeletonRows, formatNumber, useDismiss } from "./library/ui";
import { writeApi, type DocSummary } from "./write/writeApi";
import { teamsApi, type Activity, type Comment, type Invite, type Member, type Notification, type ProjectDetail, type Review, type Role, type Team, type TeamPaper, type TeamProject, type TeamSummary } from "./platform/platformApi";
import { Meter, PageShell, errorText, formatDate, formatDateTime, usePlatform } from "./platform/shared";

const ROLE_KEYS: Record<Role, SearchCopyKey> = { owner: "teamRoleOwner", admin: "teamRoleAdmin", supervisor: "teamRoleSupervisor", member: "teamRoleMember", viewer: "teamRoleViewer" };
const RANK: Record<Role, number> = { owner: 5, admin: 4, supervisor: 3, member: 2, viewer: 1 };
const STATUS_KEYS: Record<TeamPaper["status"], SearchCopyKey> = { to_read: "libStatusToRead", reading: "libStatusReading", done: "teamStatusDone" };
const REVIEW_KEYS: Record<Review["status"], SearchCopyKey> = { pending: "teamReviewPending", approved: "teamReviewApproved", changes_requested: "teamReviewChanges" };
const NOTE_KEYS: Record<string, SearchCopyKey> = { mention: "teamNoteMention", reply: "teamNoteReply", review_requested: "teamNoteReviewRequested", review_decided: "teamNoteReviewDecided", member_joined: "teamNoteJoined", role_changed: "teamNoteRole", paper_assigned: "teamNoteAssigned" };
const ACTION_KEYS: Record<string, SearchCopyKey> = {
  "team.created": "teamActCreated", "team.updated": "teamActUpdated", "team.transferred": "teamActTransferred", "invite.created": "teamActInvite", "member.joined": "teamActJoined",
  "member.left": "teamActLeft", "member.removed": "teamActRemoved", "member.role": "teamActRole", "project.created": "teamActProject", "project.deleted": "teamActProjectDeleted",
  "papers.added": "teamActPapers", "comment.added": "teamActComment", "review.requested": "teamActReviewRequested", "review.approved": "teamActReviewApproved", "review.changes_requested": "teamActReviewChanges",
};
const DISPLAY_NAME_KEY = "resora-team-display-name";

function rememberedName(): string {
  try { return window.localStorage.getItem(DISPLAY_NAME_KEY) || ""; } catch { return ""; }
}
function rememberName(name: string) {
  try { window.localStorage.setItem(DISPLAY_NAME_KEY, name); } catch { /* per-viewer convenience */ }
}

type Ctx = { t: SearchT; language: string; toast: (message: string) => void };

export function TeamsPage({ interfaceLanguage = "en" }: { interfaceLanguage?: string }) {
  const { t, toast, toastText } = usePlatform(interfaceLanguage);
  const ctx = { t, language: interfaceLanguage, toast };
  return (
    <PageShell language={interfaceLanguage} title={t("teamTitle")} subtitle={t("teamSubtitle")} toastText={toastText}>
      <Routes>
        <Route index element={<TeamsHome {...ctx} />} />
        <Route path=":teamId/*" element={<TeamView {...ctx} />} />
      </Routes>
    </PageShell>
  );
}

// ---------------------------------------------------------------------------------------------------- home: inbox + teams

function TeamsHome({ t, language, toast }: Ctx) {
  const navigate = useNavigate();
  const [teams, setTeams] = useState<TeamSummary[] | null>(null);
  const [notes, setNotes] = useState<Notification[]>([]);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [displayName, setDisplayName] = useState(rememberedName);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [list, inbox] = await Promise.all([teamsApi.list(), teamsApi.notifications()]);
      setTeams(list.teams);
      setNotes(inbox.notifications);
      setError("");
    } catch (caught) {
      setError(errorText(t, caught));
    }
  }, [t]);
  useEffect(() => { void load(); }, [load]);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    setBusy(true);
    try {
      rememberName(displayName.trim());
      const team = await teamsApi.create(name.trim(), description.trim(), displayName.trim() || t("teamRoleOwner"));
      toast(t("teamCreated"));
      navigate(`/teams/${team.id}`);
    } catch (caught) {
      toast(errorText(t, caught));
    } finally {
      setBusy(false);
    }
  }

  const unread = notes.filter((note) => !note.is_read);
  return (
    <div className="pf-teams-home">
      {error ? <ErrorLine message={error} onRetry={() => void load()} t={t} /> : null}
      {unread.length ? (
        <section className="gw-panel" aria-labelledby="inbox-title">
          <div className="lb-section-head">
            <h2 id="inbox-title">{t("teamInbox", { count: formatNumber(unread.length, language) })}</h2>
            <button type="button" className="lb-text-button" onClick={() => void teamsApi.markRead().then(load)}>{t("teamMarkAllRead")}</button>
          </div>
          <ul className="pf-inbox">
            {unread.slice(0, 12).map((note) => (
              <li key={note.id}>
                <Link to={`/teams/${note.team_id}${note.payload.review_id ? `/reviews/${note.payload.review_id}` : note.payload.project_id ? `/projects/${note.payload.project_id}` : ""}`} onClick={() => void teamsApi.markRead([note.id])}>
                  <b><bdi>{note.team_name}</bdi></b> · {t(NOTE_KEYS[note.kind] || "teamNoteGeneric", { by: note.payload.by || "", title: note.payload.title || "", role: note.payload.role ? t(ROLE_KEYS[note.payload.role as Role] || "teamRoleMember") : "", name: note.payload.name || "" })}
                  {note.payload.excerpt ? <span className="gw-small"> “<bdi>{note.payload.excerpt}</bdi>”</span> : null}
                </Link>
                <span className="gw-small">{formatDateTime(note.created_at, language)}</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="lb-section" aria-labelledby="teams-title">
        <div className="lb-section-head"><h2 id="teams-title">{t("teamYourTeams")}</h2></div>
        {!teams ? <SkeletonRows rows={3} /> : !teams.length ? <EmptyState icon={<FolderGlyph />} title={t("teamNoTeams")} body={t("teamNoTeamsBody")} /> : (
          <div className="pf-team-grid">
            {teams.map((team) => (
              <Link key={team.id} to={`/teams/${team.id}`} className="pf-team-card">
                <span className="pf-team-name"><bdi>{team.name}</bdi>{team.unread ? <span className="lb-tab-count">{formatNumber(team.unread, language)}</span> : null}</span>
                {team.description ? <span className="gw-small"><bdi>{team.description}</bdi></span> : null}
                <span className="lb-row-meta">{t(ROLE_KEYS[team.role])} · {t("teamMembersCount", { count: formatNumber(team.member_count, language) })} · {t("teamProjectsCount", { count: formatNumber(team.project_count, language) })}</span>
              </Link>
            ))}
          </div>
        )}
      </section>

      <form className="gw-panel gw-create" onSubmit={create} aria-labelledby="create-team-title">
        <h2 id="create-team-title">{t("teamCreateTitle")}</h2>
        <p className="lb-section-note">{t("teamCreateNote")}</p>
        <label className="lb-field"><span>{t("teamName")}</span><input value={name} maxLength={120} required onChange={(event) => setName(event.target.value)} placeholder={t("teamNamePlaceholder")} /></label>
        <label className="lb-field"><span>{t("teamDescription")}</span><input value={description} maxLength={500} onChange={(event) => setDescription(event.target.value)} placeholder={t("teamDescriptionPlaceholder")} /></label>
        <label className="lb-field"><span>{t("teamYourName")}</span><input value={displayName} maxLength={80} onChange={(event) => setDisplayName(event.target.value)} placeholder={t("teamYourNamePlaceholder")} /></label>
        <div><button type="submit" className="lb-button lb-button-primary" disabled={busy || !name.trim()}><PlusGlyph />{t("teamCreate")}</button></div>
      </form>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------- one team

const TABS: Array<{ id: string; key: SearchCopyKey }> = [
  { id: "projects", key: "teamTabProjects" },
  { id: "reviews", key: "teamTabReviews" },
  { id: "members", key: "teamTabMembers" },
  { id: "activity", key: "teamTabActivity" },
  { id: "usage", key: "teamTabUsage" },
];

type TeamCtx = Ctx & { team: Team; reload: () => Promise<void>; can: (role: Role) => boolean; nameOf: (userId?: string | null) => string };

function TeamView(ctx: Ctx) {
  const { t, language } = ctx;
  const { teamId = "" } = useParams();
  const location = useLocation();
  const [team, setTeam] = useState<Team | null>(null);
  const [error, setError] = useState("");
  const reload = useCallback(async () => {
    try {
      setTeam(await teamsApi.get(teamId));
      setError("");
    } catch (caught) {
      setError(errorText(t, caught));
    }
  }, [teamId, t]);
  useEffect(() => { void reload(); }, [reload]);

  if (error) return <><Link className="lb-back" to="/teams"><BackGlyph />{t("teamAllTeams")}</Link><ErrorLine message={error} onRetry={() => void reload()} t={t} /></>;
  if (!team) return <SkeletonRows rows={4} />;
  const can = (role: Role) => RANK[team.my_role] >= RANK[role];
  const nameOf = (userId?: string | null) => team.members.find((member) => member.user_id === userId)?.display_name || t("teamFormerMember");
  const shared: TeamCtx = { ...ctx, team, reload, can, nameOf };
  const base = `/teams/${team.id}`;
  return (
    <div className="pf-team">
      <Link className="lb-back" to="/teams"><BackGlyph />{t("teamAllTeams")}</Link>
      <div className="pf-team-head">
        <h2><bdi>{team.name}</bdi></h2>
        <span className="lb-badge">{t(ROLE_KEYS[team.my_role])}</span>
        {team.subscription ? <span className="lb-badge pf-badge-current">{t("billPooled", { seats: team.subscription.seats })}</span> : null}
      </div>
      {team.description ? <p className="lb-section-note"><bdi>{team.description}</bdi></p> : null}
      <nav className="lb-tabs" aria-label={team.name}>
        {TABS.map((tab) => (
          <NavLink key={tab.id} to={`${base}/${tab.id}`} className={({ isActive }) => `lb-tab${isActive || (tab.id === "projects" && location.pathname.replace(/\/$/, "") === base) ? " is-active" : ""}`}>
            <span>{t(tab.key)}</span>
            {tab.id === "reviews" && team.counts.pending_reviews ? <span className="lb-tab-count">{formatNumber(team.counts.pending_reviews, language)}</span> : null}
            {tab.id === "members" ? <span className="lb-tab-count">{formatNumber(team.members.length, language)}</span> : null}
          </NavLink>
        ))}
      </nav>
      <Routes>
        <Route index element={<ProjectsView {...shared} />} />
        <Route path="projects" element={<ProjectsView {...shared} />} />
        <Route path="projects/:projectId" element={<ProjectView {...shared} />} />
        <Route path="reviews" element={<ReviewsView {...shared} />} />
        <Route path="reviews/:reviewId" element={<ReviewView {...shared} />} />
        <Route path="members" element={<MembersView {...shared} />} />
        <Route path="activity" element={<ActivityView {...shared} />} />
        <Route path="usage" element={<UsageView {...shared} />} />
        <Route path="*" element={<Navigate to={`${base}/projects`} replace />} />
      </Routes>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------- projects

function ProjectsView({ t, language, toast, team, can }: TeamCtx) {
  const [projects, setProjects] = useState<TeamProject[] | null>(null);
  const [name, setName] = useState("");
  const load = useCallback(() => teamsApi.projects(team.id).then((result) => setProjects(result.projects)).catch((caught) => toast(errorText(t, caught))), [team.id, t, toast]);
  useEffect(() => { void load(); }, [load]);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    try {
      await teamsApi.createProject(team.id, name.trim(), "");
      setName("");
      toast(t("teamProjectCreated"));
      void load();
    } catch (caught) {
      toast(errorText(t, caught));
    }
  }

  return (
    <div className="lb-section">
      {can("admin") ? (
        <form className="pf-inline-form" onSubmit={create}>
          <label className="rs-visually-hidden" htmlFor="new-project">{t("teamProjectName")}</label>
          <input id="new-project" value={name} maxLength={160} placeholder={t("teamProjectPlaceholder")} onChange={(event) => setName(event.target.value)} />
          <button type="submit" className="lb-button lb-button-primary" disabled={!name.trim()}><PlusGlyph />{t("teamNewProject")}</button>
        </form>
      ) : null}
      {!projects ? <SkeletonRows rows={3} /> : !projects.length ? <EmptyState icon={<FolderGlyph />} title={t("teamNoProjects")} body={t(can("admin") ? "teamNoProjectsAdmin" : "teamNoProjectsBody")} /> : (
        <ul className="lb-rows">
          {projects.map((project) => (
            <li key={project.id} className="lb-row pf-row">
              <div className="lb-row-main">
                <Link className="lb-row-title" to={`/teams/${team.id}/projects/${project.id}`}><bdi>{project.name}</bdi></Link>
                <span className="lb-row-meta">{t("teamProjectMeta", { papers: formatNumber(project.paper_count, language), done: formatNumber(project.done_count, language), comments: formatNumber(project.comment_count, language) })} · {formatDate(project.updated_at, language)}</span>
                {project.paper_count ? <div className="pf-progress" aria-hidden="true"><span style={{ inlineSize: `${Math.round((project.done_count / project.paper_count) * 100)}%` }} /></div> : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ProjectView({ t, language, toast, team, can, nameOf }: TeamCtx) {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [adding, setAdding] = useState(false);
  const [openPaper, setOpenPaper] = useState<string | null>(null);
  const load = useCallback(() => teamsApi.project(team.id, projectId).then(setProject).catch((caught) => toast(errorText(t, caught))), [team.id, projectId, t, toast]);
  useEffect(() => { void load(); }, [load]);

  async function patch(paper: TeamPaper, changes: Parameters<typeof teamsApi.updatePaper>[3]) {
    try {
      setProject(await teamsApi.updatePaper(team.id, projectId, paper.id, changes));
    } catch (caught) {
      toast(errorText(t, caught));
    }
  }

  if (!project) return <SkeletonRows rows={4} />;
  const assignees = [{ value: "", label: t("teamUnassigned") }, ...team.members.map((member) => ({ value: member.user_id, label: member.display_name }))];
  return (
    <div className="lb-section">
      <Link className="lb-back" to={`/teams/${team.id}/projects`}><BackGlyph />{t("teamTabProjects")}</Link>
      <div className="lb-section-head">
        <h2><bdi>{project.name}</bdi></h2>
        <div className="lb-head-actions">
          {can("member") ? <button type="button" className="lb-button lb-button-primary" onClick={() => setAdding(true)}><PlusGlyph />{t("teamAddFromLibrary")}</button> : null}
          {can("admin") ? <ConfirmButton label={t("teamDeleteProject")} confirmLabel={t("teamConfirmDelete")} onConfirm={() => void teamsApi.removeProject(team.id, projectId).then(() => navigate(`/teams/${team.id}/projects`)).catch((caught) => toast(errorText(t, caught)))} /> : null}
        </div>
      </div>
      {!project.papers.length ? <EmptyState icon={<FolderGlyph />} title={t("teamNoPapers")} body={t("teamNoPapersBody")} /> : (
        <ul className="lb-rows">
          {project.papers.map((paper) => (
            <li key={paper.id} className="lb-row pf-row pf-paper">
              <div className="lb-row-main">
                <span className="lb-row-title"><bdi>{paper.title}</bdi></span>
                <span className="lb-row-meta"><bdi>{[paper.authors.slice(0, 3).join(", "), paper.venue, paper.year].filter(Boolean).join(" · ")}</bdi></span>
                <span className="gw-small">{t("teamAddedBy", { name: nameOf(paper.added_by), date: formatDate(paper.added_at, language) })}</span>
                <div className="pf-paper-tools">
                  <Select label={t("teamPaperStatus")} value={paper.status} disabled={!can("member")} onChange={(status) => void patch(paper, { status: status as TeamPaper["status"] })} options={(["to_read", "reading", "done"] as const).map((status) => ({ value: status, label: t(STATUS_KEYS[status]) }))} />
                  <Select label={t("teamAssignee")} value={paper.assignee_id || ""} disabled={!can("member")} onChange={(value) => void patch(paper, value ? { assignee_id: value } : { clear_assignee: true })} options={assignees} />
                  <button type="button" className={`lb-pill${openPaper === paper.id ? " is-active" : ""}`} aria-expanded={openPaper === paper.id} onClick={() => setOpenPaper(openPaper === paper.id ? null : paper.id)}>{t("teamCommentsCount", { count: formatNumber(paper.comment_count, language) })}</button>
                  {can("member") ? <ConfirmButton label={t("libRemove")} confirmLabel={t("teamConfirmRemove")} onConfirm={() => void teamsApi.removePaper(team.id, projectId, paper.id).then(load).catch((caught) => toast(errorText(t, caught)))} /> : null}
                </div>
                {openPaper === paper.id ? <CommentsThread t={t} language={language} toast={toast} team={team} can={can} targetType="paper" targetId={paper.id} onChange={load} /> : null}
              </div>
            </li>
          ))}
        </ul>
      )}
      <section className="gw-panel" aria-labelledby="project-discussion">
        <h3 id="project-discussion">{t("teamDiscussion")}</h3>
        <CommentsThread t={t} language={language} toast={toast} team={team} can={can} targetType="project" targetId={project.id} />
      </section>
      {adding ? <AddFromLibrary t={t} language={language} onClose={() => setAdding(false)} onAdd={async (ids) => {
        try {
          const result = await teamsApi.addPapers(team.id, projectId, ids);
          setProject(result.project);
          toast(t("teamPapersAdded", { added: formatNumber(result.added, language), skipped: formatNumber(result.skipped, language) }));
          setAdding(false);
        } catch (caught) {
          toast(errorText(t, caught));
        }
      }} /> : null}
    </div>
  );
}

function AddFromLibrary({ t, language, onClose, onAdd }: { t: SearchT; language: string; onClose: () => void; onAdd: (ids: string[]) => Promise<void> }) {
  const panel = useRef<HTMLDivElement>(null);
  const [items, setItems] = useState<LibraryItem[] | null>(null);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  useDismiss(true, [panel], onClose);
  useEffect(() => { libraryApi.items().then(setItems).catch(() => setItems([])); }, []);
  const shown = (items || []).filter((item) => !query.trim() || item.title.toLowerCase().includes(query.trim().toLowerCase()));
  return (
    <div className="lb-dialog-backdrop">
      <div ref={panel} className="lb-dialog lb-dialog-wide" role="dialog" aria-modal="true" aria-labelledby="add-library-title">
        <h2 id="add-library-title">{t("teamAddFromLibrary")}</h2>
        <p className="lb-dialog-sub">{t("teamAddFromLibraryNote")}</p>
        <input className="lb-dropdown-filter" value={query} dir="auto" placeholder={t("libFilterPapers")} aria-label={t("libFilterPapers")} onChange={(event) => setQuery(event.target.value)} />
        {!items ? <SkeletonRows rows={3} /> : !items.length ? <EmptyState title={t("wrNoLibrary")} /> : (
          <ul className="lb-pick-list">
            {shown.slice(0, 300).map((item) => {
              const on = chosen.has(item.id);
              return (
                <li key={item.id}>
                  <label className="lb-pick">
                    <span className="lb-check"><input type="checkbox" checked={on} onChange={() => setChosen((current) => { const next = new Set(current); if (on) next.delete(item.id); else next.add(item.id); return next; })} /><span aria-hidden="true"><CheckGlyph /></span></span>
                    <span className="lb-pick-text"><bdi className="lb-pick-title">{item.title}</bdi><span className="lb-row-meta"><bdi>{[item.authors[0], item.year].filter(Boolean).join(" · ")}</bdi></span></span>
                  </label>
                </li>
              );
            })}
          </ul>
        )}
        <div className="lb-dialog-actions">
          <button type="button" className="lb-button lb-button-quiet" onClick={onClose}>{t("libCancel")}</button>
          <button type="button" className="lb-button lb-button-primary" disabled={!chosen.size || busy} onClick={() => { setBusy(true); void onAdd([...chosen]).finally(() => setBusy(false)); }}>{t("teamAddCount", { count: formatNumber(chosen.size, language) })}</button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------- comments

function CommentsThread({ t, language, toast, team, can, targetType, targetId, onChange }: { t: SearchT; language: string; toast: (message: string) => void; team: Team; can: (role: Role) => boolean; targetType: "project" | "paper" | "review"; targetId: string; onChange?: () => void }) {
  const [comments, setComments] = useState<Comment[] | null>(null);
  const [body, setBody] = useState("");
  const [replyTo, setReplyTo] = useState<Comment | null>(null);
  const load = useCallback(() => teamsApi.comments(team.id, targetType, targetId).then((result) => setComments(result.comments)).catch(() => setComments([])), [team.id, targetType, targetId]);
  useEffect(() => { void load(); }, [load]);

  async function send(event: FormEvent) {
    event.preventDefault();
    if (!body.trim()) return;
    try {
      await teamsApi.comment(team.id, { target_type: targetType, target_id: targetId, body: body.trim(), parent_id: replyTo?.id });
      setBody("");
      setReplyTo(null);
      await load();
      onChange?.();
    } catch (caught) {
      toast(errorText(t, caught));
    }
  }

  const roots = (comments || []).filter((comment) => !comment.parent_id);
  const replies = (id: string) => (comments || []).filter((comment) => comment.parent_id === id);
  const render = (comment: Comment, depth = 0) => (
    <li key={comment.id} className={`pf-comment${depth ? " is-reply" : ""}`}>
      <div className="pf-comment-head"><b><bdi>{comment.author_name || t("teamFormerMember")}</bdi></b><span className="gw-small">{formatDateTime(comment.created_at, language)}{comment.edited_at ? ` · ${t("teamEdited")}` : ""}</span></div>
      {comment.deleted ? <p className="gw-small">{t("teamCommentDeleted")}</p> : <p className="pf-comment-body" dir="auto">{highlightMentions(comment.body, team.members)}</p>}
      {!comment.deleted && can("member") && !depth ? <button type="button" className="lb-text-button" onClick={() => setReplyTo(comment)}>{t("teamReply")}</button> : null}
      {replies(comment.id).length ? <ul className="pf-comments">{replies(comment.id).map((reply) => render(reply, depth + 1))}</ul> : null}
    </li>
  );
  return (
    <div className="pf-thread">
      {!comments ? <SkeletonRows rows={2} /> : !comments.length ? <p className="gw-small">{t("teamNoComments")}</p> : <ul className="pf-comments">{roots.map((comment) => render(comment))}</ul>}
      {can("member") ? (
        <form className="pf-comment-form" onSubmit={send}>
          {replyTo ? <p className="gw-small">{t("teamReplyingTo", { name: replyTo.author_name || "" })} <button type="button" className="lb-text-button" onClick={() => setReplyTo(null)}>{t("libCancel")}</button></p> : null}
          <label className="rs-visually-hidden" htmlFor={`comment-${targetId}`}>{t("teamWriteComment")}</label>
          <textarea id={`comment-${targetId}`} value={body} maxLength={5000} dir="auto" rows={2} placeholder={t("teamCommentPlaceholder")} onChange={(event) => setBody(event.target.value)} />
          <div><button type="submit" className="lb-button lb-button-primary" disabled={!body.trim()}>{t("teamSend")}</button></div>
        </form>
      ) : null}
    </div>
  );
}

function highlightMentions(text: string, members: Member[]) {
  const names = members.map((member) => member.display_name).filter(Boolean).sort((a, b) => b.length - a.length);
  if (!names.length) return text;
  const pattern = new RegExp(`(@(?:${names.map((name) => name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")}))`, "giu");
  return text.split(pattern).map((part, index) => (part.startsWith("@") && index % 2 === 1 ? <mark key={index} className="pf-mention">{part}</mark> : part));
}

// ---------------------------------------------------------------------------------------------------- reviews

function ReviewsView({ t, language, toast, team, can, nameOf }: TeamCtx) {
  const navigate = useNavigate();
  const [reviews, setReviews] = useState<Review[] | null>(null);
  const [docs, setDocs] = useState<DocSummary[]>([]);
  const [docId, setDocId] = useState("");
  const [reviewer, setReviewer] = useState("");
  const load = useCallback(() => teamsApi.reviews(team.id).then((result) => setReviews(result.reviews)).catch((caught) => toast(errorText(t, caught))), [team.id, t, toast]);
  useEffect(() => {
    void load();
    writeApi.documents().then((list) => { setDocs(list); setDocId((current) => current || list[0]?.id || ""); }).catch(() => undefined);
  }, [load]);
  const supervisors = team.members.filter((member) => RANK[member.role] >= RANK.supervisor);

  async function request(event: FormEvent) {
    event.preventDefault();
    if (!docId) return;
    try {
      const review = await teamsApi.requestReview(team.id, docId, reviewer || undefined);
      toast(t("teamReviewRequested"));
      navigate(`/teams/${team.id}/reviews/${review.id}`);
    } catch (caught) {
      toast(errorText(t, caught));
    }
  }

  return (
    <div className="lb-section">
      <p className="lb-section-note">{t("teamReviewsNote")}</p>
      {can("member") ? (
        <form className="gw-panel pf-review-form" onSubmit={request} aria-labelledby="request-review-title">
          <h3 id="request-review-title">{t("teamRequestReview")}</h3>
          {!docs.length ? <p className="gw-small">{t("teamNoDocuments")} <Link className="lb-text-button" to="/writing/draft">{t("wrNewDraft")}</Link></p> : (
            <div className="pf-inline-form">
              <Select label={t("teamDocument")} value={docId} onChange={setDocId} options={docs.map((doc) => ({ value: doc.id, label: doc.title || t("wrDocTitle") }))} />
              <Select label={t("teamReviewer")} value={reviewer} onChange={setReviewer} options={[{ value: "", label: t("teamAnySupervisor") }, ...supervisors.map((member) => ({ value: member.user_id, label: member.display_name }))]} />
              <button type="submit" className="lb-button lb-button-primary" disabled={!docId}>{t("teamSendForReview")}</button>
            </div>
          )}
        </form>
      ) : null}
      {!reviews ? <SkeletonRows rows={3} /> : !reviews.length ? <EmptyState title={t("teamNoReviews")} body={t("teamNoReviewsBody")} /> : (
        <ul className="lb-rows">
          {reviews.map((review) => (
            <li key={review.id} className="lb-row pf-row">
              <div className="lb-row-main">
                <Link className="lb-row-title" to={`/teams/${team.id}/reviews/${review.id}`}><bdi>{review.title}</bdi></Link>
                <span className="lb-row-meta">{t("teamReviewMeta", { name: review.requester_name || nameOf(review.requested_by), round: review.round, date: formatDate(review.created_at, language) })}</span>
              </div>
              <span className={`pf-review-status is-${review.status}`}>{t(REVIEW_KEYS[review.status])}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ReviewView({ t, language, toast, team, can, nameOf }: TeamCtx) {
  const { reviewId = "" } = useParams();
  const [review, setReview] = useState<Review | null>(null);
  const [note, setNote] = useState("");
  const load = useCallback(() => teamsApi.review(team.id, reviewId).then(setReview).catch((caught) => toast(errorText(t, caught))), [team.id, reviewId, t, toast]);
  useEffect(() => { void load(); }, [load]);

  async function decide(status: "approved" | "changes_requested") {
    try {
      setReview(await teamsApi.decide(team.id, reviewId, status, note.trim()));
      toast(t(status === "approved" ? "teamApprovedToast" : "teamChangesToast"));
    } catch (caught) {
      toast(errorText(t, caught));
    }
  }

  if (!review) return <SkeletonRows rows={4} />;
  return (
    <div className="lb-section">
      <Link className="lb-back" to={`/teams/${team.id}/reviews`}><BackGlyph />{t("teamTabReviews")}</Link>
      <div className="lb-section-head">
        <h2><bdi>{review.title}</bdi></h2>
        <span className={`pf-review-status is-${review.status}`}>{t(REVIEW_KEYS[review.status])}</span>
      </div>
      <p className="lb-section-note">{t("teamReviewMeta", { name: nameOf(review.requested_by), round: review.round, date: formatDate(review.created_at, language) })}</p>
      {review.decision_note ? <blockquote className="gw-quote" dir="auto">{review.decision_note}<cite>{nameOf((review as Review & { decided_by?: string }).decided_by)}</cite></blockquote> : null}
      <article className="gw-panel pf-snapshot" dir="auto" aria-label={t("teamSnapshot")}>{review.snapshot}</article>
      {review.can_decide ? (
        <section className="gw-panel" aria-labelledby="decision-title">
          <h3 id="decision-title">{t("teamYourDecision")}</h3>
          <label className="rs-visually-hidden" htmlFor="decision-note">{t("teamDecisionNote")}</label>
          <textarea id="decision-note" value={note} rows={3} dir="auto" maxLength={4000} placeholder={t("teamDecisionPlaceholder")} onChange={(event) => setNote(event.target.value)} />
          <div className="lb-head-actions">
            <button type="button" className="lb-button lb-button-primary" onClick={() => void decide("approved")}>{t("teamApprove")}</button>
            <button type="button" className="lb-button lb-button-quiet" onClick={() => void decide("changes_requested")}>{t("teamRequestChanges")}</button>
          </div>
        </section>
      ) : null}
      <section className="gw-panel" aria-labelledby="review-discussion">
        <h3 id="review-discussion">{t("teamDiscussion")}</h3>
        <CommentsThread t={t} language={language} toast={toast} team={team} can={can} targetType="review" targetId={review.id} />
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------- members + invites

function MembersView({ t, language, toast, team, can, reload }: TeamCtx) {
  const navigate = useNavigate();
  const [invites, setInvites] = useState<Invite[]>([]);
  const [role, setRole] = useState<Role>("member");
  const [days, setDays] = useState("7");
  const [uses, setUses] = useState("1");
  const [link, setLink] = useState("");
  const [name, setName] = useState(team.name);
  const loadInvites = useCallback(() => { if (can("admin")) teamsApi.invites(team.id).then((result) => setInvites(result.invites)).catch(() => undefined); }, [team.id, can]);
  useEffect(() => { loadInvites(); }, [loadInvites]);

  async function run(action: () => Promise<unknown>, message: SearchCopyKey) {
    try {
      await action();
      toast(t(message));
      await reload();
      loadInvites();
    } catch (caught) {
      toast(errorText(t, caught));
    }
  }

  async function invite(event: FormEvent) {
    event.preventDefault();
    try {
      const created = await teamsApi.invite(team.id, role, Number(days), Number(uses));
      const url = `${window.location.origin}/join/${created.token}`;
      setLink(url);
      loadInvites();
    } catch (caught) {
      toast(errorText(t, caught));
    }
  }

  const roleOptions = (["admin", "supervisor", "member", "viewer"] as Role[]).filter((value) => value !== "admin" || team.my_role === "owner").map((value) => ({ value, label: t(ROLE_KEYS[value]) }));
  return (
    <div className="lb-section">
      <ul className="lb-rows">
        {team.members.map((member) => (
          <li key={member.user_id} className="lb-row pf-row">
            <div className="lb-row-main">
              <span className="lb-row-title"><bdi>{member.display_name}</bdi></span>
              <span className="lb-row-meta">{t("teamJoined", { date: formatDate(member.joined_at, language) })}</span>
            </div>
            <div className="lb-row-actions">
              {can("admin") && member.role !== "owner" && (member.role !== "admin" || team.my_role === "owner") ? (
                <Select label={t("teamRole")} value={member.role} align="end" onChange={(value) => void run(() => teamsApi.updateMember(team.id, member.user_id, { role: value as Role }), "teamRoleUpdated")} options={roleOptions} />
              ) : <span className="lb-badge">{t(ROLE_KEYS[member.role])}</span>}
              {can("admin") && member.role !== "owner" && (member.role !== "admin" || team.my_role === "owner") ? <ConfirmButton label={t("libRemove")} confirmLabel={t("teamConfirmRemove")} onConfirm={() => void run(() => teamsApi.removeMember(team.id, member.user_id), "teamMemberRemoved")} /> : null}
              {team.my_role === "owner" && member.role !== "owner" ? <ConfirmButton label={t("teamMakeOwner")} confirmLabel={t("teamConfirmTransfer")} onConfirm={() => void run(() => teamsApi.transfer(team.id, member.user_id), "teamTransferred")} /> : null}
            </div>
          </li>
        ))}
      </ul>

      {can("admin") ? (
        <form className="gw-panel gw-create" onSubmit={invite} aria-labelledby="invite-title">
          <h3 id="invite-title">{t("teamInviteTitle")}</h3>
          <p className="lb-section-note">{t("teamInviteNote")}</p>
          <div className="pf-inline-form">
            <Select label={t("teamRole")} value={role} onChange={(value) => setRole(value as Role)} options={roleOptions} />
            <Select label={t("teamInviteExpires")} value={days} onChange={setDays} options={["1", "7", "30"].map((value) => ({ value, label: t("teamDays", { count: value }) }))} />
            <Select label={t("teamInviteUses")} value={uses} onChange={setUses} options={["1", "5", "25"].map((value) => ({ value, label: t("teamUses", { count: value }) }))} />
            <button type="submit" className="lb-button lb-button-primary">{t("teamCreateLink")}</button>
          </div>
          {link ? (
            <div className="pf-invite-link">
              <input readOnly value={link} aria-label={t("teamInviteLink")} onFocus={(event) => event.currentTarget.select()} />
              <button type="button" className="lb-button lb-button-quiet" onClick={() => void navigator.clipboard?.writeText(link).then(() => toast(t("wrCopied")))}><CopyGlyph />{t("teamCopy")}</button>
              <p className="gw-small">{t("teamLinkOnce")}</p>
            </div>
          ) : null}
          {invites.filter((entry) => entry.active).length ? (
            <ul className="gw-plain-list">
              {invites.filter((entry) => entry.active).map((entry) => (
                <li key={entry.id} className="pf-invite-row">
                  <span>{t(ROLE_KEYS[entry.role])} · {t("teamInviteUsage", { uses: entry.uses, max: entry.max_uses })} · {t("teamExpiresOn", { date: formatDate(entry.expires_at, language) })}</span>
                  <button type="button" className="lb-text-button" onClick={() => void run(() => teamsApi.revokeInvite(team.id, entry.id), "teamInviteRevoked")}>{t("teamRevoke")}</button>
                </li>
              ))}
            </ul>
          ) : null}
        </form>
      ) : null}

      <section className="gw-panel" aria-labelledby="team-settings">
        <h3 id="team-settings">{t("teamSettings")}</h3>
        {can("admin") ? (
          <form className="pf-inline-form" onSubmit={(event) => { event.preventDefault(); void run(() => teamsApi.update(team.id, { name }), "teamSaved"); }}>
            <label className="rs-visually-hidden" htmlFor="team-rename">{t("teamName")}</label>
            <input id="team-rename" value={name} maxLength={120} onChange={(event) => setName(event.target.value)} />
            <button type="submit" className="lb-button lb-button-quiet" disabled={!name.trim() || name === team.name}>{t("teamRename")}</button>
          </form>
        ) : null}
        <div className="lb-head-actions">
          {team.my_role !== "owner" ? <ConfirmButton label={t("teamLeave")} confirmLabel={t("teamConfirmLeave")} onConfirm={() => void teamsApi.removeMember(team.id, team.my_user_id).then(() => navigate("/teams")).catch(() => undefined)} /> : null}
          {team.my_role === "owner" ? <ConfirmButton label={t("teamDelete")} confirmLabel={t("teamConfirmDelete")} onConfirm={() => void teamsApi.remove(team.id).then(() => navigate("/teams")).catch((caught) => toast(errorText(t, caught)))} /> : null}
        </div>
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------- activity + usage

function ActivityView({ t, language, toast, team }: TeamCtx) {
  const [rows, setRows] = useState<Activity[] | null>(null);
  useEffect(() => { teamsApi.activity(team.id).then((result) => setRows(result.activity)).catch((caught) => toast(errorText(t, caught))); }, [team.id, t, toast]);
  if (!rows) return <SkeletonRows rows={5} />;
  if (!rows.length) return <EmptyState title={t("teamNoActivity")} />;
  return (
    <ol className="pf-activity">
      {rows.map((row) => (
        <li key={row.id}>
          <span className="pf-activity-dot" aria-hidden="true" />
          <div><b><bdi>{row.actor_name || t("teamFormerMember")}</bdi></b> {t(ACTION_KEYS[row.action] || "teamActOther")} {row.action === "comment.added" || row.action.startsWith("review") || row.action.startsWith("project") || row.action === "papers.added" ? <span className="gw-small">“<bdi>{row.summary}</bdi>”</span> : null}</div>
          <span className="gw-small">{formatDateTime(row.created_at, language)}</span>
        </li>
      ))}
    </ol>
  );
}

function UsageView({ t, language, toast, team }: TeamCtx) {
  const [data, setData] = useState<Awaited<ReturnType<typeof teamsApi.usage>> | null>(null);
  useEffect(() => { teamsApi.usage(team.id).then(setData).catch((caught) => toast(errorText(t, caught))); }, [team.id, t, toast]);
  const upgrade = useMemo(() => `/pricing`, []);
  if (!data) return <SkeletonRows rows={3} />;
  if (!data.pooled || !data.usage) {
    return <EmptyState title={t("teamNotPooled")} body={t("teamNotPooledBody")} action={team.my_role === "owner" ? <Link className="lb-button lb-button-primary" to={upgrade}>{t("teamUpgrade")}</Link> : undefined} />;
  }
  return (
    <section className="gw-panel">
      <p className="lb-section-note">{t("teamPooledNote", { seats: formatNumber(data.seats, language), members: formatNumber(data.members, language) })}</p>
      <div className="pf-meters">{data.usage.windows.map((window) => <Meter key={window.scope} t={t} language={language} window={window} />)}</div>
      {data.members > data.seats ? <p className="pf-notice is-warn">{t("teamOverSeats")}</p> : null}
    </section>
  );
}

// ---------------------------------------------------------------------------------------------------- invite link landing

export function JoinTeamPage({ interfaceLanguage = "en" }: { interfaceLanguage?: string }) {
  const { t, toast, toastText } = usePlatform(interfaceLanguage);
  const { token = "" } = useParams();
  const navigate = useNavigate();
  const [preview, setPreview] = useState<Awaited<ReturnType<typeof teamsApi.previewInvite>> | null>(null);
  const [error, setError] = useState("");
  const [name, setName] = useState(rememberedName);
  useEffect(() => { teamsApi.previewInvite(token).then(setPreview).catch((caught) => setError(errorText(t, caught))); }, [token, t]);

  async function accept(event: FormEvent) {
    event.preventDefault();
    try {
      rememberName(name.trim());
      const result = await teamsApi.acceptInvite(token, name.trim() || t("teamRoleMember"));
      toast(t(result.already_member ? "teamAlreadyMember" : "teamJoinedToast"));
      navigate(`/teams/${result.team_id}`);
    } catch (caught) {
      setError(errorText(t, caught));
    }
  }

  return (
    <PageShell language={interfaceLanguage} title={t("teamJoinTitle")} toastText={toastText}>
      {error ? <ErrorLine message={error} t={t} /> : !preview ? <SkeletonRows rows={2} /> : (
        <form className="gw-panel gw-create pf-join" onSubmit={accept}>
          <h2><bdi>{preview.team.name}</bdi></h2>
          <p className="lb-section-note">{t("teamJoinNote", { role: t(ROLE_KEYS[preview.role]), members: preview.members })}</p>
          <label className="lb-field"><span>{t("teamYourName")}</span><input value={name} maxLength={80} required onChange={(event) => setName(event.target.value)} placeholder={t("teamYourNamePlaceholder")} /></label>
          <div><button type="submit" className="lb-button lb-button-primary" disabled={!name.trim()}>{t("teamJoin")}</button></div>
        </form>
      )}
    </PageShell>
  );
}
