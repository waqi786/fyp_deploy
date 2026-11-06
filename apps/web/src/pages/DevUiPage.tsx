import { useEffect, useState } from "react";
import {
  Avatar, Badge, BottomSheet, Button, Card, CitationMarker, ConfidenceDot, CreditsPill, DataTable, Dialog, Drawer,
  DropdownMenu, EmptyState, ErrorState, IconButton, KeyboardShortcut, LanguagePicker, PageHeader, Pill, Popover,
  ProgressLine, Section, SegmentedControl, Skeleton, Stepper, Tabs, Toast, Tooltip,
} from "../components/ui";
import { researchLanguages } from "../i18n/languages";

export function DevUiPage() {
  const [direction, setDirection] = useState<"ltr" | "rtl">("ltr");
  const [theme, setTheme] = useState<"dark" | "light">((document.body.dataset.theme as "dark" | "light") || "dark");
  useEffect(() => {
    const original = document.body.dataset.theme || "dark";
    document.body.dataset.theme = theme;
    return () => { document.body.dataset.theme = original; };
  }, [theme]);
  const [segment, setSegment] = useState("all");
  const [tab, setTab] = useState("overview");
  const [language, setLanguage] = useState("en");
  const [dialog, setDialog] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [sheet, setSheet] = useState(false);
  const [toast, setToast] = useState(true);
  return <main dir={direction} className="mx-auto max-w-6xl space-y-10 p-6">
    <PageHeader title="UI foundations" description="Development gallery for shared Resora components." actions={<div className="flex flex-wrap gap-2"><Button variant={theme === "dark" ? "primary" : "secondary"} onClick={() => setTheme("dark")}>Dark</Button><Button variant={theme === "light" ? "primary" : "secondary"} onClick={() => setTheme("light")}>Light</Button><Button variant={direction === "ltr" ? "primary" : "secondary"} onClick={() => setDirection("ltr")}>LTR</Button><Button variant={direction === "rtl" ? "primary" : "secondary"} onClick={() => setDirection("rtl")}>RTL</Button></div>} />
    <Section title="Actions and labels">
      <div className="flex flex-wrap items-center gap-3"><Button variant="primary">Primary</Button><Button>Secondary</Button><Button variant="ghost">Ghost</Button><Button variant="danger">Danger</Button><IconButton aria-label="Add item">+</IconButton><Pill>Research workspace</Pill><Badge>Neutral</Badge><Badge tone="success">Open access</Badge><Badge tone="warning">Review needed</Badge><Badge tone="danger">Retracted</Badge><CreditsPill balance={2400}/><Avatar name="Waqar Ali"/><KeyboardShortcut>Ctrl K</KeyboardShortcut><Tooltip label="Button hint"><Button>Hover or focus</Button></Tooltip></div>
    </Section>
    <Section title="Selection and menus">
      <div className="flex flex-wrap items-center gap-4"><SegmentedControl value={segment} label="Result type" options={[{value:"all",label:"All"},{value:"papers",label:"Papers"},{value:"web",label:"Web"}]} onChange={setSegment}/><Tabs value={tab} onChange={setTab} tabs={[{id:"overview",label:"Overview"},{id:"evidence",label:"Evidence"}]}/><Popover label="Filter options" trigger="Open popover"><p className="text-sm text-brand-muted">Outside click, Escape and route changes dismiss this panel.</p></Popover><DropdownMenu label="More options" items={[{label:"First action",onSelect:()=>setToast(true)},{label:"Second action",onSelect:()=>setToast(true)}]}/></div>
    </Section>
    <Section title="Language and confidence">
      <div className="flex flex-wrap items-center gap-5"><div className="w-64"><LanguagePicker languages={researchLanguages} value={language} onChange={setLanguage}/></div><ConfidenceDot level="High"/><ConfidenceDot level="Medium"/><ConfidenceDot level="Low"/><CitationMarker onClick={()=>setDrawer(true)}>[1]</CitationMarker></div>
    </Section>
    <Section title="Content, loading and data">
      <div className="grid gap-4 md:grid-cols-2"><Card><h3 className="font-display text-xl">Card surface</h3><p className="mt-2 text-sm text-brand-muted">A shared neutral container with a consistent border.</p></Card><Card><Skeleton className="h-4 w-2/3"/><Skeleton className="mt-3 h-4 w-full"/><Skeleton className="mt-3 h-24 w-full"/></Card></div>
      <DataTable><thead><tr className="bg-brand-surface-2 text-start"><th className="p-3">Paper</th><th className="p-3">Evidence</th></tr></thead><tbody><tr><td className="p-3">Study A</td><td className="p-3">Dataset reported</td></tr></tbody></DataTable>
      <Stepper steps={["Search","Read","Compare","Write"]} current={1}/>
      <ErrorState message="The preview could not load." onRetry={()=>setToast(true)}/>
      <EmptyState title="No saved items" description="Save a paper to keep it in your workspace." action={<Button variant="primary">Find papers</Button>}/>
    </Section>
    <Section title="Overlays and feedback">
      <div className="flex flex-wrap gap-3"><Button onClick={()=>setDialog(true)}>Dialog</Button><Button onClick={()=>setDrawer(true)}>Drawer</Button><Button onClick={()=>setSheet(true)}>Bottom sheet</Button><Button onClick={()=>setToast(true)}>Toast</Button></div>
      {toast ? <Toast message="Changes saved." tone="success" onClose={()=>setToast(false)}/> : null}
      <ProgressLine active={false}/>
    </Section>
    <Dialog open={dialog} title="Example dialog" onClose={()=>setDialog(false)}><p className="text-sm text-brand-muted">Escape and outside click close this dialog.</p></Dialog>
    <Drawer open={drawer} title="Evidence details" onClose={()=>setDrawer(false)}><p className="text-sm text-brand-muted">Evidence can be reviewed here with its source passage and page location.</p></Drawer>
    <BottomSheet open={sheet} title="Example sheet" onClose={()=>setSheet(false)}><p className="text-sm text-brand-muted">Compact mobile actions appear in a bottom sheet.</p></BottomSheet>
  </main>;
}
