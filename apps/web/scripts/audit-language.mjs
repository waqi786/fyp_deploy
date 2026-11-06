import fs from "node:fs/promises";
import path from "node:path";

const port = Number(process.env.EDGE_CDP_PORT || 9223);
const baseUrl = process.env.RESORA_URL || "http://127.0.0.1:5173";
const language = process.argv[2] || "ur";
const outDir = path.resolve("test-shots", language);

const routes = [
  ["/", "home"],
  ["/search", "search"],
  ["/summaries", "reader"],
  ["/chat", "chat"],
  ["/multimodal", "multimodal"],
  ["/comparison", "comparison"],
  ["/gaps", "gaps"],
  ["/writing", "writing"],
  ["/collaboration", "collaboration"],
  ["/personalization", "personalization"],
  ["/analytics", "analytics"],
  ["/security-mobile", "trust"],
  ["/developer-ai", "developer-ai"],
  ["/control", "control"],
];

const allowedEnglish = new Set([
  "Resora",
  "API",
  "AI",
  "FYP",
  "PDF",
  "PDFs",
  "PWA",
  "RTL",
  "LTR",
  "WCAG",
  "DOI",
  "URL",
  "JSON",
  "CSV",
  "HTML",
  "CSS",
  "TTS",
  "RAG",
  "OCR",
  "CORE",
  "PMC",
  "PubMed",
  "DOAJ",
  "Unpaywall",
  "Google",
  "Scopus",
  "IEEE",
  "Xplore",
  "ACM",
  "Springer",
  "Nature",
  "ScienceDirect",
  "Wiley",
  "DBLP",
  "Dimensions",
  "GraphQL",
  "REST",
  "LaTeX",
  "WhatsApp",
  "JPEG",
  "AUC",
  "SVG",
  "GitHub",
  "DFDC",
  "CVPR",
  "TIFS",
  "ICCV",
  "PUCIT",
  "USA",
  "RIS",
  "NIH",
  "ERC",
  "NSF",
  "DOCX",
  "APA",
  "DNA",
  "TOIS",
  "APC",
  "UKRI",
  "MLA",
  "PLOS",
  "ONE",
  "LOI",
  "HEC",
  "NRPU",
  "MATLAB",
  "ATG",
  "CGT",
  "AAC",
  "GTT",
  "CSL",
  "RBAC",
  "SAML",
  "OIDC",
  "SSO",
  "IRB",
  "POST",
  "DND",
  "NMR",
  "PPT",
  "PRISMA",
  "CHI",
  "CRISPR",
  "PICO",
  "RNA",
  "STR",
  "ACL",
  "ANOVA",
  "CMYK",
  "OSF",
  "COI",
  "README",
  "STROBE",
  "LLM",
  "ORCID",
  "RSS",
  "IFTTT",
  "XML",
  "GDPR",
  "HIPAA",
  "TEX",
  "SMTP",
  "UNO",
  "PHI",
  "TOC",
  "BLOCKED",
  "FFFFFF",
  "arXiv",
  "OpenAlex",
  "Crossref",
  "Semantic",
  "Scholar",
  "Waqar",
  "Ali",
  "Chen",
  "Khan",
  "Areesha",
  "Haroon",
  "github",
  "resora",
  "frac",
  "numerator",
  "denominator",
  "article",
  "title",
  "Hybrid",
  "Retrieval",
  "Benchmark",
  "Dataset",
  "webhooks",
  "research",
  "flow",
  "example",
  "events",
  "summaries",
  "workspace",
  "history",
]);

function requestJson(targetPath, init = {}) {
  return fetch(`http://127.0.0.1:${port}${targetPath}`, init).then((response) => {
    if (!response.ok) throw new Error(`${targetPath} ${response.status}`);
    return response.json();
  });
}

async function createTarget() {
  try {
    return await requestJson(`/json/new?${encodeURIComponent("about:blank")}`, { method: "PUT" });
  } catch {
    return requestJson(`/json/new?${encodeURIComponent("about:blank")}`);
  }
}

async function connect(wsUrl) {
  const socket = new WebSocket(wsUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });

  let id = 0;
  const pending = new Map();
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) reject(new Error(message.error.message));
      else resolve(message.result);
    }
  });

  return {
    send(method, params = {}) {
      const messageId = ++id;
      socket.send(JSON.stringify({ id: messageId, method, params }));
      return new Promise((resolve, reject) => pending.set(messageId, { resolve, reject }));
    },
    close() {
      socket.close();
    },
  };
}

function englishLeaks(text) {
  const matches = text.match(/\b[A-Z][A-Za-z]{2,}\b|\b[a-z][a-z]{3,}\b/g) || [];
  const counts = new Map();
  for (const word of matches) {
    if (allowedEnglish.has(word)) continue;
    if (/^[A-Z0-9]{2,}$/.test(word)) continue;
    if (/^(http|https|localhost|true|false|null|undefined)$/i.test(word)) continue;
    counts.set(word, (counts.get(word) || 0) + 1);
  }
  return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 40);
}

await fs.mkdir(outDir, { recursive: true });
const target = await createTarget();
const client = await connect(target.webSocketDebuggerUrl);
await client.send("Page.enable");
await client.send("Runtime.enable");
await client.send("Page.addScriptToEvaluateOnNewDocument", {
  source: `
    window.localStorage.setItem('resora-language-source', 'settings');
    window.localStorage.setItem('resora-language', ${JSON.stringify(language)});
  `,
});
await client.send("Emulation.setDeviceMetricsOverride", {
  width: 1440,
  height: 1000,
  deviceScaleFactor: 1,
  mobile: false,
});

const report = [];
for (const [route, name] of routes) {
  const url = `${baseUrl}${route}?lang=${language}`;
  await client.send("Page.navigate", { url });
  await new Promise((resolve) => setTimeout(resolve, 2200));
  const textResult = await client.send("Runtime.evaluate", {
    returnByValue: true,
    expression: `(() => {
      const hidden = (el) => {
        const s = getComputedStyle(el);
        return s.display === 'none' || s.visibility === 'hidden' || Number(s.opacity) === 0;
      };
      return [...document.body.querySelectorAll('body *')]
        .filter((el) => !hidden(el) && !['SCRIPT','STYLE','CODE','PRE','SELECT','OPTION','TEXTAREA'].includes(el.tagName))
        .map((el) => [...el.childNodes].filter((n) => n.nodeType === Node.TEXT_NODE).map((n) => n.textContent.trim()).join(' '))
        .filter(Boolean)
        .join('\\n');
    })()`,
  });
  const text = textResult.result.value || "";
  const leaks = englishLeaks(text);
  report.push({ route, name, leaks });
  const screenshot = await client.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  await fs.writeFile(path.join(outDir, `${name}.png`), Buffer.from(screenshot.data, "base64"));
}

await client.send("Page.navigate", { url: `${baseUrl}/?lang=en` });
await new Promise((resolve) => setTimeout(resolve, 1600));
await client.send("Runtime.evaluate", {
  expression: `(() => {
    document.querySelector('.sidebar-footer button')?.click();
  })()`,
});
await new Promise((resolve) => setTimeout(resolve, 400));
await client.send("Runtime.evaluate", {
  expression: `(() => {
    const select = document.querySelector('.settings-panel select');
    if (!select) return false;
    select.value = ${JSON.stringify(language)};
    select.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  })()`,
});
await new Promise((resolve) => setTimeout(resolve, 900));
const settingsScreenshot = await client.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
await fs.writeFile(path.join(outDir, "settings-modal.png"), Buffer.from(settingsScreenshot.data, "base64"));

await fs.writeFile(path.join(outDir, "report.json"), JSON.stringify(report, null, 2));
client.close();

console.log(JSON.stringify(report, null, 2));
