/**
 * "Read this paper aloud" in any supported language → a listening intent.
 *
 * Not a single keyword: a request must combine a READ/LISTEN verb with a TARGET (paper, summary, key points,
 * section, selection) or be a playback command (stop, pause, next section). Each language contributes verb and
 * target cues; the best-scoring target wins, and plain questions about the paper ("what does the paper say about
 * reading?") are rejected because they are questions without a request to speak.
 */
export type ListenIntent =
  | { action: "play"; target: "paper" | "summary" | "key_points" | "section" | "selection" }
  | { action: "pause" | "resume" | "stop" | "next_section" | "previous_section" };

type Cues = { verbs: RegExp[]; targets: Record<"paper" | "summary" | "key_points" | "section" | "selection", RegExp[]>; commands: Partial<Record<"pause" | "resume" | "stop" | "next_section" | "previous_section", RegExp[]>> };

const CUES: Cues[] = [
  { // English
    verbs: [/\bread\b.*\b(aloud|out loud|to me|for me)\b/, /\b(read|listen|play|narrate|speak)\b/, /\bcan you read\b/],
    targets: { paper: [/\b(paper|article|document|pdf|whole thing|it)\b/], summary: [/\bsummary\b|\bsummar/], key_points: [/\bkey points?\b|\bhighlights\b|\bmain points\b/], section: [/\b(this|current) section\b|\bsection\b/], selection: [/\b(selection|selected|highlighted) (text)?\b/] },
    commands: { stop: [/^\s*(stop|stop reading|stop listening)\s*[.!]?\s*$/], pause: [/^\s*pause( reading)?\s*[.!]?\s*$/], resume: [/^\s*(resume|continue)( reading)?\s*[.!]?\s*$/], next_section: [/^\s*next section\s*[.!]?\s*$/], previous_section: [/^\s*(previous|last) section\s*[.!]?\s*$/] },
  },
  { // Urdu
    verbs: [/پڑھ\s*کر\s*سنا/, /سناؤ|سنائیں|سنا\s*دو|سنا\s*دیں/, /بلند\s*آواز/, /پڑھو|پڑھیں|پڑھ\s*دو/],
    targets: { paper: [/پیپر|مقالہ|مقالے|دستاویز|پوری/], summary: [/خلاصہ|خلاصے/], key_points: [/اہم\s*نکات|نکات/], section: [/حصہ|سیکشن/], selection: [/منتخب/] },
    commands: { stop: [/^\s*(رک\s*جاؤ|رکو|بند\s*کرو|بس)\s*$/], pause: [/^\s*(روکو|وقفہ)\s*$/], resume: [/^\s*(جاری\s*رکھو|دوبارہ\s*شروع)\s*$/], next_section: [/اگلا\s*(حصہ|سیکشن)/] },
  },
  { // Chinese
    verbs: [/读给我听|朗读|念给我|读一下|读出来|播放/],
    targets: { paper: [/论文|文章|文档|全文/], summary: [/摘要|总结/], key_points: [/要点|重点/], section: [/这一节|本节|章节/], selection: [/选中/] },
    commands: { stop: [/^\s*(停止|别读了)\s*$/], pause: [/^\s*暂停\s*$/], resume: [/^\s*继续\s*$/], next_section: [/下一节/] },
  },
  { // Spanish
    verbs: [/\blee(r|me)?\b.*\b(en voz alta|para mí)\b/, /\blee\b|\bleer\b|\bescuchar\b|\breproduc/],
    targets: { paper: [/\b(art[ií]culo|documento|paper|trabajo)\b/], summary: [/\bresumen\b/], key_points: [/\bpuntos clave\b/], section: [/\bsecci[oó]n\b/], selection: [/\bselecci[oó]n\b/] },
    commands: { stop: [/^\s*(para|detente|deja de leer)\s*$/], pause: [/^\s*pausa\s*$/], resume: [/^\s*(contin[uú]a|sigue)\s*$/], next_section: [/siguiente secci[oó]n/] },
  },
  { // Arabic
    verbs: [/اقرأ|اقرا|بصوت\s*عال|استمع|شغّل/],
    targets: { paper: [/الورقة|البحث|المقال|المستند/], summary: [/الملخص|ملخص/], key_points: [/النقاط\s*الرئيسية/], section: [/القسم/], selection: [/المحدد/] },
    commands: { stop: [/^\s*(توقف|أوقف)\s*$/], pause: [/^\s*إيقاف\s*مؤقت\s*$/], resume: [/^\s*(استمر|تابع)\s*$/] },
  },
  { // Hindi
    verbs: [/पढ़\s*कर\s*सुना|सुनाओ|सुनाइए|पढ़ो|ज़ोर\s*से/],
    targets: { paper: [/पेपर|शोधपत्र|लेख|दस्तावेज़/], summary: [/सारांश/], key_points: [/मुख्य\s*बिंदु/], section: [/भाग|सेक्शन/], selection: [/चुना/] },
    commands: { stop: [/^\s*(रुको|बंद\s*करो)\s*$/], pause: [/^\s*रोको\s*$/], resume: [/^\s*जारी\s*रखो\s*$/] },
  },
  { // French / German / Portuguese (short)
    verbs: [/\blis(-moi)?\b|\blire\b.*\bvoix haute\b|\bvorlesen\b|\blies\b|\bleia\b|\bler\b.*\bem voz alta\b/],
    targets: { paper: [/\barticle\b|\bdocument\b|\bartikel\b|\bpapier\b|\bartigo\b/], summary: [/\br[ée]sum[ée]\b|\bzusammenfassung\b|\bresumo\b/], key_points: [/\bpoints cl[ée]s\b|\bkernpunkte\b|\bpontos principais\b/], section: [/\bsection\b|\babschnitt\b|\bse[cç][aã]o\b/], selection: [/\bs[ée]lection\b|\bauswahl\b|\bsele[cç][aã]o\b/] },
    commands: { stop: [/^\s*(arr[eê]te|stopp|pare)\s*$/] },
  },
];

const QUESTION = /^(what|why|how|who|when|which|does|is|are|do|explain|summari[sz]e|compare|کیا|کیوں|کیسے|什么|为什么|如何|qu[eé]|por qu[eé]|c[oó]mo)\b/i;

export function detectListenIntent(input: string): ListenIntent | null {
  const text = input.trim().toLowerCase();
  if (!text || text.length > 160) return null;
  for (const cues of CUES) {
    for (const [action, patterns] of Object.entries(cues.commands)) {
      if (patterns?.some((pattern) => pattern.test(text))) return { action } as ListenIntent;
    }
  }
  let best: { target: keyof Cues["targets"]; score: number } | null = null;
  for (const cues of CUES) {
    const verb = cues.verbs.filter((pattern) => pattern.test(text)).length;
    if (!verb) continue;
    for (const [target, patterns] of Object.entries(cues.targets) as Array<[keyof Cues["targets"], RegExp[]]>) {
      const hits = patterns.filter((pattern) => pattern.test(text)).length;
      if (!hits) continue;
      // More specific targets (summary, key points, section) outrank the generic "paper / it".
      const score = verb * 2 + hits * 3 + (target === "paper" ? 0 : 2);
      if (!best || score > best.score) best = { target, score };
    }
  }
  if (!best) return null;
  // "What does the paper say about reading?" is a question, not a request to speak (unless it says aloud/سناؤ…).
  if (QUESTION.test(text) && !/aloud|out loud|سنا|朗读|读给|voz alta|بصوت|सुना/.test(text)) return null;
  return { action: "play", target: best.target };
}
