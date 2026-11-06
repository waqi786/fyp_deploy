/**
 * PDF viewer built on pdf.js (Apache-2.0). Pages are rendered lazily (only near the viewport), re-rendered
 * crisply on zoom, and report which page is in view. `scrollToPage` jumps to a page (used by page chips).
 */
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import type { PDFDocumentProxy, RenderTask } from "pdfjs-dist";

export type PdfViewerHandle = { scrollToPage: (page: number) => void };
type Props = {
  url: string;
  zoom: number; // 1 = fit width
  darkPages: boolean;
  onPageChange: (page: number) => void;
  onReady: (pageCount: number) => void;
  onError: () => void;
  pageLabel: (page: number) => string;
};

let pdfjsPromise: Promise<typeof import("pdfjs-dist")> | null = null;

function loadPdfjs() {
  if (!pdfjsPromise) {
    pdfjsPromise = Promise.all([import("pdfjs-dist"), import("pdfjs-dist/build/pdf.worker.min.mjs?url")]).then(([pdfjs, worker]) => {
      pdfjs.GlobalWorkerOptions.workerSrc = (worker as { default: string }).default;
      return pdfjs;
    });
  }
  return pdfjsPromise;
}

export const PdfViewer = forwardRef<PdfViewerHandle, Props>(function PdfViewer({ url, zoom, darkPages, onPageChange, onReady, onError, pageLabel }, ref) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const pageRefs = useRef<Array<HTMLDivElement | null>>([]);
  const rendered = useRef(new Map<number, number>()); // page → width it was rendered at
  const tasks = useRef(new Map<number, RenderTask>());
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [ratio, setRatio] = useState(1.294); // height / width of page 1
  const [width, setWidth] = useState(0);

  useImperativeHandle(ref, () => ({
    scrollToPage: (page: number) => {
      const target = pageRefs.current[page - 1];
      const scroller = scrollRef.current;
      if (target && scroller) scroller.scrollTo({ top: target.offsetTop - 12, behavior: "smooth" });
    },
  }), []);

  // Load the document.
  useEffect(() => {
    let cancelled = false;
    let loaded: PDFDocumentProxy | null = null;
    rendered.current.clear();
    loadPdfjs()
      .then((pdfjs) => pdfjs.getDocument({ url, withCredentials: false, isEvalSupported: false }).promise)
      .then(async (document) => {
        if (cancelled) {
          void document.destroy();
          return;
        }
        loaded = document;
        const first = await document.getPage(1);
        const viewport = first.getViewport({ scale: 1 });
        setRatio(viewport.height / viewport.width);
        setPdf(document);
        onReady(document.numPages);
      })
      .catch(() => {
        if (!cancelled) onError();
      });
    return () => {
      cancelled = true;
      tasks.current.forEach((task) => task.cancel());
      tasks.current.clear();
      if (loaded) void loaded.destroy();
      setPdf(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url]);

  // Track the available width (fit width), so pages stay sharp after resizing.
  useEffect(() => {
    const scroller = scrollRef.current;
    if (!scroller) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(240, Math.floor(entry.contentRect.width - 32))));
    observer.observe(scroller);
    return () => observer.disconnect();
  }, []);

  const pageWidth = Math.round(width * zoom);

  const renderPage = useCallback(async (number: number) => {
    if (!pdf || !pageWidth) return;
    if (rendered.current.get(number) === pageWidth) return;
    const holder = pageRefs.current[number - 1];
    if (!holder) return;
    rendered.current.set(number, pageWidth);
    tasks.current.get(number)?.cancel();
    try {
      const page = await pdf.getPage(number);
      const base = page.getViewport({ scale: 1 });
      const scale = pageWidth / base.width;
      const pixelRatio = Math.min(window.devicePixelRatio || 1, 2.5);
      const viewport = page.getViewport({ scale: scale * pixelRatio });
      const canvas = document.createElement("canvas");
      canvas.width = Math.floor(viewport.width);
      canvas.height = Math.floor(viewport.height);
      canvas.style.width = "100%";
      canvas.style.height = "100%";
      const task = page.render({ canvas, viewport });
      tasks.current.set(number, task);
      await task.promise;
      tasks.current.delete(number);
      holder.querySelector("canvas")?.remove();
      holder.appendChild(canvas);
      holder.dataset.ready = "true";
    } catch {
      rendered.current.delete(number); // cancelled or failed: try again when visible
    }
  }, [pdf, pageWidth]);

  // Render pages near the viewport; report the page that fills most of it.
  useEffect(() => {
    const scroller = scrollRef.current;
    if (!pdf || !scroller) return;
    const visibility = new Map<number, number>();
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        const number = Number((entry.target as HTMLElement).dataset.page);
        visibility.set(number, entry.intersectionRatio);
        if (entry.isIntersecting) void renderPage(number);
      });
      let best = 1;
      let bestRatio = -1;
      visibility.forEach((value, key) => {
        if (value > bestRatio) {
          best = key;
          bestRatio = value;
        }
      });
      onPageChange(best);
    }, { root: scroller, rootMargin: "600px 0px", threshold: [0, 0.25, 0.5, 0.75, 1] });
    pageRefs.current.forEach((element) => element && observer.observe(element));
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pdf, renderPage]);

  return (
    <div className={`rd-pdf${darkPages ? " is-dark-pages" : ""}`} ref={scrollRef}>
      {pdf
        ? Array.from({ length: pdf.numPages }, (_, index) => (
            <div
              key={index}
              ref={(element) => {
                pageRefs.current[index] = element;
              }}
              className="rd-pdf-page"
              data-page={index + 1}
              style={{ width: pageWidth || undefined, height: pageWidth ? Math.round(pageWidth * ratio) : undefined }}
              aria-label={pageLabel(index + 1)}
              role="img"
            >
              <span className="rd-pdf-page-number" aria-hidden="true">{index + 1}</span>
            </div>
          ))
        : (
          <div className="rd-pdf-page rd-pdf-skeleton" style={{ width: pageWidth || undefined, height: pageWidth ? Math.round(pageWidth * ratio) : 600 }} />
        )}
    </div>
  );
});
