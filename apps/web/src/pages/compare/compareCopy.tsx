/** Compare page wording: every visible label comes from the shared catalog (search/copy.ts), never from the page-wide auto-translator.
 *  Values computed by the API stay in English internally (they drive matching and page lookups) and are localised only when shown. */
import { createContext, useContext } from "react";
import type { ReactNode } from "react";
import { fillTemplate, searchCopyEn, type SearchCopyKey, type SearchT } from "../search/copy";

export type CompareCopy = {
  t: SearchT;
  language: string;
  /** A column key (method, dataset, reproducibility…) as a header label. */
  column: (name: string) => string;
  /** An internal English label (stance, evidence kind, "Page 3", source line…) in the interface language. */
  label: (text: string) => string;
  /** Machine-translated table content when the reader turned it on; otherwise the original text. */
  content: (text: string) => string;
};

const englishT: SearchT = (key, values) => (values ? fillTemplate(searchCopyEn[key], values) : searchCopyEn[key]);

const COLUMN_KEYS: Record<string, SearchCopyKey> = {
  paper: "cmpPaper",
  method: "cmpColMethod",
  methods: "cmpColMethod",
  dataset: "cmpColDataset",
  datasets: "cmpColDataset",
  model: "cmpColModel",
  metric: "cmpColMetric",
  result: "cmpColResult",
  results: "cmpColResult",
  limitation: "cmpColLimitation",
  limitations: "cmpLimitations",
  baseline: "cmpColBaseline",
  "compute cost": "cmpColComputeCost",
  "dataset size": "cmpColDatasetSize",
  "main limitation": "cmpColMainLimitation",
  reproducibility: "cmpCodeAvailable",
  "code available": "cmpCodeAvailable",
  "study design": "cmpColStudyDesign",
  population: "cmpColPopulation",
  "sample size": "cmpColSampleSize",
  intervention: "cmpColIntervention",
  comparator: "cmpColComparator",
  outcome: "cmpColOutcome",
  "follow-up": "cmpColFollowUp",
  "research question": "cmpColResearchQuestion",
  "sampling method": "cmpColSamplingMethod",
  country: "cmpColCountry",
  "survey instrument": "cmpColInstrument",
  "analysis method": "cmpColAnalysis",
  "key finding": "cmpColKeyFinding",
  code: "cmpCode",
  data: "cmpData",
  hyperparameters: "cmpHyper",
  experimental_details: "cmpExpDetails",
  pretrained_model: "cmpPretrained",
  license: "cmpLicense",
};

const LABEL_KEYS: Record<string, SearchCopyKey> = {
  "Source passage": "cmpSourcePassage",
  "Takeaway source": "cmpTakeawaySource",
  "Full-paper evidence": "cmpFullPaperEvidence",
  "Matched table evidence": "cmpMatchedTableEvidence",
  Dataset: "cmpColDataset",
  Limitations: "cmpLimitations",
  "Research question": "cmpResearchQuestion",
  "Supporting signal": "cmpSupporting",
  "Opposing signal": "cmpOpposing",
  Mixed: "cmpMixed",
  "Evidence found": "cmpEvidenceFound",
  "Not addressed": "cmpNotAddressed",
  "Not located in extracted PDF text": "cmpNotLocated",
  "Uploaded PDF": "cmpSrcPdf",
  "Uploaded PDF text": "cmpSrcPdfText",
  high: "cmpHigh",
  medium: "cmpMedium",
  low: "cmpLow",
};

export const COLUMN_TEMPLATES: Array<{ id: string; name: SearchCopyKey; columns: string[] }> = [
  { id: "general", name: "cmpTplGeneral", columns: ["method", "dataset", "model", "metric", "result", "limitation", "reproducibility"] },
  { id: "ml", name: "cmpTplMl", columns: ["model", "dataset", "metric", "result", "baseline", "compute cost", "reproducibility", "limitation"] },
  { id: "clinical", name: "cmpTplClinical", columns: ["study design", "population", "sample size", "intervention", "comparator", "outcome", "follow-up", "limitation"] },
  { id: "survey", name: "cmpTplSurvey", columns: ["research question", "sample size", "sampling method", "country", "survey instrument", "analysis method", "key finding", "limitation"] },
];

export const SUGGESTED_COLUMNS = ["Dataset size", "Compute cost", "Main limitation", "Code available"];

export function makeCompareCopy(t: SearchT, language: string, translated: Record<string, string> = {}, translating = false): CompareCopy {
  const column = (name: string) => {
    const key = COLUMN_KEYS[name.trim().toLowerCase()];
    return key ? t(key) : name.replace(/\b\w/g, (letter) => letter.toUpperCase());
  };
  const label = (text: string): string => {
    if (!text) return text;
    const key = LABEL_KEYS[text];
    if (key) return t(key);
    const page = text.match(/^Uploaded PDF(?: text)? · page (\d+)$/);
    if (page) return t("cmpSrcPdfPage", { page: page[1] });
    const bare = text.match(/^Page (\d+)$/);
    if (bare) return t("cmpPageN", { page: bare[1] });
    const columnKey = COLUMN_KEYS[text.trim().toLowerCase()];
    return columnKey ? t(columnKey) : text;
  };
  const content = (text: string) => (translating ? text : translated[text] || text);
  return { t, language, column, label, content };
}

const CompareCopyContext = createContext<CompareCopy>(makeCompareCopy(englishT, "en"));

export function CompareCopyProvider({ value, children }: { value: CompareCopy; children: ReactNode }) {
  return <CompareCopyContext.Provider value={value}>{children}</CompareCopyContext.Provider>;
}

export function useCompareCopy() {
  return useContext(CompareCopyContext);
}

/** The interface language's own name for itself ("اردو", "Deutsch"); falls back to the code. */
export function languageName(code: string) {
  try {
    return new Intl.DisplayNames([code], { type: "language" }).of(code) || code;
  } catch {
    return code;
  }
}

const RTL = new Set(["ar", "ur", "fa", "he", "ps", "sd", "ug", "yi", "dv", "ckb", "pa-Arab"]);
export const isRtl = (code: string) => RTL.has(code) || RTL.has(code.split("-")[0]);
