/**
 * App-wide interface translator for screens that do not localise their own text yet.
 *
 * It swaps English text nodes and a few attributes for entries in ./catalogs/<language>.json.
 * Screens that own their translations (Search, researcher and institution profiles, the top navigation)
 * mark their root with `data-no-translate`; this translator never touches anything inside such a region,
 * so two translators can never fight over the same words.
 *
 * Safety rules (they stop machine-translated catalogs from corrupting the page):
 *   - pattern entries need at least 3 real letters outside their {placeholders}; a pattern such as
 *     "{value1} {value2}." would otherwise match almost any sentence and inject unrelated text;
 *   - a translation that loses a placeholder, or adds an arrow that the English did not have, is ignored;
 *   - URLs, HTTP verbs, code and form fields are left alone.
 */
import { ReactNode, useEffect, useLayoutEffect, useRef, useState } from "react";
import { getResearchLanguage } from "./languages";

type Catalog = Record<string, string>;
type PatternEntry = { regex: RegExp; names: string[]; output: string };
type PreparedCatalog = { exact: Map<string, string>; patterns: PatternEntry[] };

const catalogLoaders = import.meta.glob<Catalog>("./catalogs/*.json", { import: "default" });
const attributes = ["placeholder", "title", "aria-label", "alt"] as const;
const SKIP_SELECTOR = "[data-no-translate], [translate='no'], .notranslate, [contenteditable='true'], code, pre, textarea, select, script, style";
const PLACEHOLDER = /\{([A-Za-z_][A-Za-z0-9_]*)\}/g;
const EMPTY: PreparedCatalog = { exact: new Map(), patterns: [] };

function placeholderNames(value: string) {
  return [...value.matchAll(PLACEHOLDER)].map((match) => match[1]).sort().join(",");
}

function cleanOutput(source: string, output: unknown): output is string {
  if (typeof output !== "string" || !output.trim()) return false;
  if (output.includes("→") && !source.includes("→")) return false;
  return placeholderNames(source) === placeholderNames(output);
}

function letterCount(value: string) {
  return (value.replace(PLACEHOLDER, "").match(/\p{L}/gu) || []).length;
}

function prepare(catalog: Catalog): PreparedCatalog {
  const exact = new Map<string, string>();
  const patterns: PatternEntry[] = [];
  for (const [source, output] of Object.entries(catalog)) {
    if (!cleanOutput(source, output)) continue;
    if (!source.includes("{")) {
      exact.set(source, output);
      continue;
    }
    if (letterCount(source) < 3) continue; // too generic: would match unrelated sentences
    const names: string[] = [];
    const body = source.split(/(\{[A-Za-z_][A-Za-z0-9_]*\})/g).map((part) => {
      const placeholder = part.match(/^\{([A-Za-z_][A-Za-z0-9_]*)\}$/);
      if (placeholder) {
        names.push(placeholder[1]);
        return "(.+?)";
      }
      return part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    }).join("");
    patterns.push({ regex: new RegExp(`^${body}$`), names, output });
  }
  return { exact, patterns };
}

function translate(text: string, catalog: PreparedCatalog): string {
  const leading = text.match(/^\s*/)?.[0] || "";
  const trailing = text.match(/\s*$/)?.[0] || "";
  const source = text.trim().replace(/\s+/g, " ");
  if (!source || source.length > 500 || !/[A-Za-z]/.test(source)) return text;
  if (/^(?:GET|POST|PUT|PATCH|DELETE)\s/i.test(source) || /^https?:\/\/\S+$/i.test(source)) return text;
  const exact = catalog.exact.get(source);
  if (exact) return `${leading}${exact}${trailing}`;
  for (const pattern of catalog.patterns) {
    const match = pattern.regex.exec(source);
    if (!match) continue;
    let output = pattern.output;
    pattern.names.forEach((name, index) => {
      output = output.replace(`{${name}}`, match[index + 1]);
    });
    return `${leading}${output}${trailing}`;
  }
  return text;
}

function isSkipped(element: Element | null) {
  return Boolean(element?.closest(SKIP_SELECTOR));
}

export function AutoTranslator({ children, language }: { children: ReactNode; language: string }) {
  const rootRef = useRef<HTMLDivElement>(null);
  const originals = useRef(new WeakMap<Text, string>());
  const written = useRef(new WeakMap<Element, Record<string, string>>());
  const [catalog, setCatalog] = useState<PreparedCatalog>(EMPTY);

  useEffect(() => {
    let active = true;
    const loader = catalogLoaders[`./catalogs/${language}.json`];
    if (language === "en" || !loader) {
      setCatalog(EMPTY);
    } else {
      void loader()
        .then((loaded) => {
          if (active) setCatalog(prepare(loaded));
        })
        .catch(() => {
          if (active) setCatalog(EMPTY);
        });
    }
    return () => {
      active = false;
    };
  }, [language]);

  useLayoutEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    root.lang = language;
    root.dir = getResearchLanguage(language)?.direction || "ltr";

    const translateNode = (node: Text, refresh = false) => {
      if (!node.data.trim()) return;
      const source = refresh ? node.data : originals.current.get(node) ?? node.data;
      originals.current.set(node, source);
      const output = translate(source, catalog);
      if (output !== node.data) node.data = output;
    };

    const translateAttributes = (element: Element) => {
      attributes.forEach((attribute) => {
        const value = element.getAttribute(attribute);
        if (!value) return;
        const originalKey = `data-i18n-original-${attribute}`;
        const original = element.getAttribute(originalKey) || value;
        if (!element.hasAttribute(originalKey)) element.setAttribute(originalKey, original);
        const output = translate(original, catalog);
        if (output !== value) {
          element.setAttribute(attribute, output);
          written.current.set(element, { ...(written.current.get(element) || {}), [attribute]: output });
        }
      });
    };

    /** Walk a subtree, skipping (with all their descendants) regions that manage their own language. */
    const scan = (start: Node) => {
      if (start.nodeType === Node.TEXT_NODE) {
        if (!isSkipped(start.parentElement)) translateNode(start as Text);
        return;
      }
      if (start.nodeType !== Node.ELEMENT_NODE || isSkipped(start as Element)) return;
      const walker = document.createTreeWalker(start, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
        acceptNode: (node) =>
          node.nodeType === Node.ELEMENT_NODE && (node as Element).matches(SKIP_SELECTOR) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT,
      });
      translateAttributes(start as Element);
      let current = walker.nextNode();
      while (current) {
        if (current.nodeType === Node.TEXT_NODE) translateNode(current as Text);
        else translateAttributes(current as Element);
        current = walker.nextNode();
      }
    };

    scan(root);

    // Batch DOM changes into one pass per frame instead of re-scanning the page for every mutation.
    let queued = new Set<Node>();
    let frame = 0;
    const flush = () => {
      frame = 0;
      const nodes = queued;
      queued = new Set();
      nodes.forEach((node) => {
        if (node.isConnected) scan(node);
      });
    };
    const observer = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.type === "characterData") {
          const node = mutation.target as Text;
          if (isSkipped(node.parentElement)) continue;
          const source = originals.current.get(node);
          if (!source || node.data !== translate(source, catalog)) translateNode(node, true);
          continue;
        }
        if (mutation.type === "attributes") {
          const element = mutation.target as Element;
          const name = mutation.attributeName || "";
          if (written.current.get(element)?.[name] === element.getAttribute(name)) continue; // our own change
          if (!isSkipped(element) && (attributes as readonly string[]).includes(name)) {
            element.removeAttribute(`data-i18n-original-${name}`);
            queued.add(element);
          }
          continue;
        }
        mutation.addedNodes.forEach((node) => queued.add(node));
      }
      if (queued.size && !frame) frame = window.requestAnimationFrame(flush);
    });
    observer.observe(root, { characterData: true, childList: true, subtree: true, attributes: true, attributeFilter: [...attributes] });
    return () => {
      observer.disconnect();
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, [language, catalog]);

  return <div ref={rootRef}>{children}</div>;
}