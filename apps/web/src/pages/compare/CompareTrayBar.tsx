/** Floating bar showing the papers picked for Compare (Search and Reader). Opens the Compare page with them. */
import { useNavigate } from "react-router-dom";
import type { SearchT } from "../search/copy";
import { clearTray, removeFromTray, useTray } from "./compareTray";
import "./CompareTrayBar.css";

export function CompareTrayBar({ t }: { t: SearchT }) {
  const items = useTray();
  const navigate = useNavigate();
  if (!items.length) return null;
  const shown = items.slice(0, 3);
  return (
    <div className="ct-bar" role="region" aria-label={items.length === 1 ? t("compareTrayOne") : t("compareTrayCount", { count: items.length })}>
      <div className="ct-count">
        <span className="ct-badge" aria-hidden="true">{items.length}</span>
        <span>{items.length === 1 ? t("compareTrayOne") : t("compareTrayCount", { count: items.length })}</span>
      </div>
      <ul className="ct-chips">
        {shown.map((item) => (
          <li key={item.key}>
            <bdi>{item.title}</bdi>
            <button type="button" aria-label={t("compareTrayRemove", { title: item.title })} title={t("compareTrayRemove", { title: item.title })} onClick={() => removeFromTray(item.key)}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>
            </button>
          </li>
        ))}
        {items.length > shown.length ? <li className="ct-more">+{items.length - shown.length}</li> : null}
      </ul>
      <div className="ct-actions">
        <button type="button" className="ct-clear" onClick={clearTray}>{t("compareTrayClear")}</button>
        <button type="button" className="ct-open" onClick={() => navigate("/comparison?from=tray")}>
          {t("compareTrayOpen")}
          <svg className="ct-arrow" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6" /></svg>
        </button>
      </div>
    </div>
  );
}
