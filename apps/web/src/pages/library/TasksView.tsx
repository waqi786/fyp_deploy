/** Tasks with deadlines, grouped Overdue · Today · Upcoming · No date, with completed tasks folded away. */
import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import type { SearchCopyKey } from "../search/copy";
import { libraryApi, type LibraryTask } from "./libraryApi";
import { CheckGlyph, CloseGlyph, EmptyState, ErrorLine, Select, SkeletonRows, TaskGlyph, formatDay, today, useLib } from "./ui";

type Group = "overdue" | "today" | "upcoming" | "nodate";
const GROUPS: Array<{ id: Group; key: SearchCopyKey }> = [
  { id: "overdue", key: "libTasksOverdue" },
  { id: "today", key: "libTasksToday" },
  { id: "upcoming", key: "libTasksUpcoming" },
  { id: "nodate", key: "libTasksNoDate" },
];

function groupOf(task: LibraryTask, day: string): Group {
  if (!task.due_date) return "nodate";
  if (task.due_date < day) return "overdue";
  if (task.due_date === day) return "today";
  return "upcoming";
}

export function TasksView({ projectId, onChange }: { projectId?: string; onChange?: () => void }) {
  const { t, language, lists, toast, errorText, refresh } = useLib();
  const [tasks, setTasks] = useState<LibraryTask[] | null>(null);
  const [error, setError] = useState("");
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const [high, setHigh] = useState(false);
  const [project, setProject] = useState("");
  const [showDone, setShowDone] = useState(false);
  const day = today();
  const projects = lists.filter((list) => list.kind === "project");

  async function load() {
    setError("");
    try {
      setTasks(await libraryApi.tasks(projectId));
    } catch (caught) {
      setError(errorText(caught));
    }
  }
  useEffect(() => { void load(); }, [projectId]);

  const open = useMemo(() => (tasks || []).filter((task) => !task.done).sort((a, b) => (a.due_date || "9999").localeCompare(b.due_date || "9999") || (a.priority === "high" ? -1 : 0) - (b.priority === "high" ? -1 : 0)), [tasks]);
  const done = useMemo(() => (tasks || []).filter((task) => task.done).sort((a, b) => (b.completed_at || "").localeCompare(a.completed_at || "")), [tasks]);

  function changed() {
    onChange?.();
    void refresh();
  }

  async function add(event: FormEvent) {
    event.preventDefault();
    if (!title.trim()) return;
    try {
      const task = await libraryApi.createTask({ title: title.trim(), due_date: due || null, priority: high ? "high" : "normal", project_id: projectId || project || null });
      setTasks((current) => [...(current || []), task]);
      setTitle(""); setDue(""); setHigh(false);
      toast(t("libTaskAdded"));
      changed();
    } catch (caught) {
      toast(errorText(caught));
    }
  }

  async function patch(task: LibraryTask, changes: Partial<LibraryTask>) {
    setTasks((current) => (current || []).map((entry) => (entry.id === task.id ? { ...entry, ...changes } : entry)));
    try {
      const saved = await libraryApi.updateTask(task.id, changes);
      setTasks((current) => (current || []).map((entry) => (entry.id === task.id ? saved : entry)));
      changed();
    } catch (caught) {
      setTasks((current) => (current || []).map((entry) => (entry.id === task.id ? task : entry)));
      toast(errorText(caught));
    }
  }

  async function remove(task: LibraryTask) {
    try {
      await libraryApi.deleteTask(task.id);
      setTasks((current) => (current || []).filter((entry) => entry.id !== task.id));
      changed();
    } catch (caught) {
      toast(errorText(caught));
    }
  }

  const row = (task: LibraryTask) => {
    const group = groupOf(task, day);
    const projectName = !projectId ? projects.find((entry) => entry.id === task.project_id)?.name : "";
    return (
      <li key={task.id} className={`lb-task${task.done ? " is-done" : ""}`}>
        <label className="lb-check lb-check-round">
          <input type="checkbox" checked={task.done} onChange={() => void patch(task, { done: !task.done })} aria-label={task.done ? t("libMarkNotDone", { title: task.title }) : t("libMarkDone", { title: task.title })} />
          <span aria-hidden="true"><CheckGlyph /></span>
        </label>
        <span className="lb-task-title" dir="auto">{task.title}</span>
        {task.priority === "high" && !task.done ? <span className="lb-badge is-accent">{t("libHighPriority")}</span> : null}
        {projectName ? <span className="lb-chip is-quiet"><bdi>{projectName}</bdi></span> : null}
        {task.due_date ? <span className={`lb-due${group === "overdue" && !task.done ? " is-overdue" : ""}`}>{group === "today" && !task.done ? t("libTasksToday") : formatDay(task.due_date, language)}</span> : null}
        <button type="button" className="lb-icon-button lb-task-delete" aria-label={t("libDeleteTask", { title: task.title })} title={t("libDelete")} onClick={() => void remove(task)}><CloseGlyph /></button>
      </li>
    );
  };

  return (
    <div className="lb-section">
      <form className="lb-task-add" onSubmit={(event) => void add(event)}>
        <input value={title} maxLength={300} dir="auto" onChange={(event) => setTitle(event.target.value)} placeholder={t("libTaskPlaceholder")} aria-label={t("libNewTask")} />
        <label className="lb-date">
          <span className="rs-visually-hidden">{t("libDueDate")}</span>
          <input type="date" value={due} onChange={(event) => setDue(event.target.value)} aria-label={t("libDueDate")} />
        </label>
        <button type="button" className={`lb-pill${high ? " is-active" : ""}`} aria-pressed={high} onClick={() => setHigh((value) => !value)}>{t("libHighPriority")}</button>
        {!projectId && projects.length ? (
          <Select label={t("libProject")} value={project} onChange={setProject}
            options={[{ value: "", label: t("libNoProject") }, ...projects.map((entry) => ({ value: entry.id, label: entry.name }))]} />
        ) : null}
        <button type="submit" className="lb-button lb-button-primary" disabled={!title.trim()}>{t("libAddTask")}</button>
      </form>

      {error ? <ErrorLine message={error} onRetry={() => void load()} t={t} /> : null}
      {!tasks && !error ? <SkeletonRows rows={3} /> : null}
      {tasks && !tasks.length ? <EmptyState icon={<TaskGlyph />} title={t("libNoTasks")} body={t("libNoTasksBody")} /> : null}
      {tasks && tasks.length && !open.length ? <p className="lb-section-note lb-all-done">{t("libAllTasksDone")}</p> : null}

      {GROUPS.map((group) => {
        const members = open.filter((task) => groupOf(task, day) === group.id);
        return members.length ? (
          <section key={group.id} className={`lb-task-group lb-task-group-${group.id}`} aria-label={t(group.key)}>
            <h3>{t(group.key)}<span>{members.length}</span></h3>
            <ul>{members.map(row)}</ul>
          </section>
        ) : null;
      })}

      {done.length ? (
        <section className="lb-task-group" aria-label={t("libTasksCompleted")}>
          <button type="button" className="lb-text-button" aria-expanded={showDone} onClick={() => setShowDone((value) => !value)}>
            {showDone ? t("libHideCompleted") : t("libShowCompleted", { count: done.length })}
          </button>
          {showDone ? <ul>{done.map(row)}</ul> : null}
        </section>
      ) : null}
    </div>
  );
}
