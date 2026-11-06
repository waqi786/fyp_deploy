/** Compare exports built in the browser: an .xlsx workbook (no library) and a printable report the browser saves as PDF.
 *  Both use exactly what the table shows: values, their source passages, sources and confidence. */

export type ExportCell = { value: string; quote: string; source: string; confidence: string };
export type ExportTable = {
  title: string;
  columns: Array<{ key: string; label: string }>;
  rows: Array<{ title: string; cells: Record<string, ExportCell> }>;
  labels: { paper: string; column: string; value: string; quote: string; source: string; confidence: string; sheetTable: string; sheetEvidence: string; reportTitle: string; generated: string; note: string };
  rtl: boolean;
  language: string;
};

// ---------- XLSX (Office Open XML, stored zip) ----------

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  return table;
})();

function crc32(bytes: Uint8Array) {
  let crc = 0xffffffff;
  for (let index = 0; index < bytes.length; index += 1) crc = CRC_TABLE[(crc ^ bytes[index]) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

/** A zip archive with stored (uncompressed) entries — valid for Excel, LibreOffice, Numbers and Google Sheets. */
function zip(files: Array<{ name: string; data: Uint8Array }>): Blob {
  const encoder = new TextEncoder();
  const chunks: Uint8Array[] = [];
  const central: Uint8Array[] = [];
  let offset = 0;
  for (const file of files) {
    const name = encoder.encode(file.name);
    const crc = crc32(file.data);
    const local = new Uint8Array(30 + name.length);
    const view = new DataView(local.buffer);
    view.setUint32(0, 0x04034b50, true);
    view.setUint16(4, 20, true);
    view.setUint16(6, 0x0800, true); // UTF-8 names
    view.setUint16(8, 0, true);
    view.setUint32(14, crc, true);
    view.setUint32(18, file.data.length, true);
    view.setUint32(22, file.data.length, true);
    view.setUint16(26, name.length, true);
    local.set(name, 30);
    const header = new Uint8Array(46 + name.length);
    const headerView = new DataView(header.buffer);
    headerView.setUint32(0, 0x02014b50, true);
    headerView.setUint16(4, 20, true);
    headerView.setUint16(6, 20, true);
    headerView.setUint16(8, 0x0800, true);
    headerView.setUint32(16, crc, true);
    headerView.setUint32(20, file.data.length, true);
    headerView.setUint32(24, file.data.length, true);
    headerView.setUint16(28, name.length, true);
    headerView.setUint32(42, offset, true);
    header.set(name, 46);
    chunks.push(local, file.data);
    central.push(header);
    offset += local.length + file.data.length;
  }
  const centralSize = central.reduce((sum, item) => sum + item.length, 0);
  const end = new Uint8Array(22);
  const endView = new DataView(end.buffer);
  endView.setUint32(0, 0x06054b50, true);
  endView.setUint16(8, files.length, true);
  endView.setUint16(10, files.length, true);
  endView.setUint32(12, centralSize, true);
  endView.setUint32(16, offset, true);
  return new Blob([...chunks, ...central, end] as BlobPart[], { type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" });
}

const xml = (value: string) => value
  // eslint-disable-next-line no-control-regex
  .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F  ]/g, "")
  .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

const columnName = (index: number) => {
  let name = "";
  for (let value = index + 1; value > 0; value = Math.floor((value - 1) / 26)) name = String.fromCharCode(65 + ((value - 1) % 26)) + name;
  return name;
};

function sheet(rows: string[][], widths: number[], rtl: boolean) {
  const cells = rows.map((row, rowIndex) => `<row r="${rowIndex + 1}">${row.map((value, columnIndex) => `<c r="${columnName(columnIndex)}${rowIndex + 1}" t="inlineStr" s="${rowIndex === 0 ? 1 : 2}"><is><t xml:space="preserve">${xml(value.slice(0, 32000))}</t></is></c>`).join("")}</row>`).join("");
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"${rtl ? ' rightToLeft="1"' : ""}><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>${widths.map((width, index) => `<col min="${index + 1}" max="${index + 1}" width="${width}" customWidth="1"/>`).join("")}</cols><sheetData>${cells}</sheetData></worksheet>`;
}

const sheetName = (value: string) => value.replace(/[\\/?*[\]:]/g, " ").slice(0, 31) || "Sheet";

export function comparisonXlsx(table: ExportTable): Blob {
  const encoder = new TextEncoder();
  const summary = [[table.labels.paper, ...table.columns.map((column) => column.label)], ...table.rows.map((row) => [row.title, ...table.columns.map((column) => row.cells[column.key]?.value || "")])];
  const evidence = [[table.labels.paper, table.labels.column, table.labels.value, table.labels.quote, table.labels.source, table.labels.confidence], ...table.rows.flatMap((row) => table.columns.map((column) => {
    const cell = row.cells[column.key];
    return [row.title, column.label, cell?.value || "", cell?.quote || "", cell?.source || "", cell?.confidence || ""];
  }))];
  const names = [sheetName(table.labels.sheetTable), sheetName(table.labels.sheetEvidence)];
  if (names[0] === names[1]) names[1] = `${names[1].slice(0, 29)} 2`;
  const files = [
    { name: "[Content_Types].xml", text: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>` },
    { name: "_rels/.rels", text: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>` },
    { name: "xl/workbook.xml", text: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="${xml(names[0])}" sheetId="1" r:id="rId1"/><sheet name="${xml(names[1])}" sheetId="2" r:id="rId2"/></sheets></workbook>` },
    { name: "xl/_rels/workbook.xml.rels", text: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>` },
    { name: "xl/styles.xml", text: `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF1ECE4"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>` },
    { name: "xl/worksheets/sheet1.xml", text: sheet(summary, [44, ...table.columns.map(() => 32)], table.rtl) },
    { name: "xl/worksheets/sheet2.xml", text: sheet(evidence, [40, 22, 32, 70, 26, 14], table.rtl) },
  ];
  return zip(files.map((file) => ({ name: file.name, data: encoder.encode(file.text) })));
}

// ---------- Printable report (Save as PDF) ----------

const html = (value: string) => value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export function comparisonReportHtml(table: ExportTable) {
  const head = `<tr><th>${html(table.labels.paper)}</th>${table.columns.map((column) => `<th>${html(column.label)}</th>`).join("")}</tr>`;
  const body = table.rows.map((row) => `<tr><th scope="row">${html(row.title)}</th>${table.columns.map((column) => `<td>${html(row.cells[column.key]?.value || "")}</td>`).join("")}</tr>`).join("");
  const evidence = table.rows.map((row) => {
    const items = table.columns.filter((column) => row.cells[column.key]?.quote).map((column) => {
      const cell = row.cells[column.key];
      return `<li><b>${html(column.label)}:</b> ${html(cell.value)}<blockquote>${html(cell.quote)}</blockquote><small>${html(cell.source)} · ${html(cell.confidence)}</small></li>`;
    }).join("");
    return items ? `<section><h3>${html(row.title)}</h3><ul>${items}</ul></section>` : "";
  }).join("");
  return `<!doctype html><html lang="${html(table.language)}" dir="${table.rtl ? "rtl" : "ltr"}"><head><meta charset="utf-8"><title>${html(table.title)}</title><style>
@page{size:A4 landscape;margin:14mm}
body{font:11px/1.45 "Noto Sans","Noto Nastaliq Urdu","Segoe UI",Arial,sans-serif;color:#1d1b18;margin:0}
h1{font-size:20px;margin:0 0 4px}h2{font-size:15px;margin:18px 0 6px}h3{font-size:12px;margin:14px 0 4px}
.meta{color:#6b645a;margin:0 0 4px}.note{color:#6b645a;font-size:10px;margin:0 0 12px}
table{border-collapse:collapse;width:100%;table-layout:fixed}th,td{border:1px solid #d9d2c6;padding:5px 6px;vertical-align:top;text-align:start;overflow-wrap:anywhere}
thead th{background:#f1ece4}tbody th{font-weight:600;width:18%}tr{break-inside:avoid}
ul{padding-inline-start:16px;margin:0}li{margin:0 0 8px;break-inside:avoid}blockquote{margin:3px 0;padding-inline-start:8px;border-inline-start:3px solid #d13a12;color:#3b362f}small{color:#6b645a}
</style></head><body><h1>${html(table.labels.reportTitle)}</h1><p class="meta"><b>${html(table.title)}</b> · ${html(table.labels.generated)}</p><p class="note">${html(table.labels.note)}</p>
<table><thead>${head}</thead><tbody>${body}</tbody></table><h2>${html(table.labels.sheetEvidence)}</h2>${evidence}</body></html>`;
}

/** Opens the browser's print dialog for the report (the user picks “Save as PDF”). No pop-up window is needed. */
export function printComparisonReport(table: ExportTable) {
  document.getElementById("cmp-print-frame")?.remove();
  const frame = document.createElement("iframe");
  frame.id = "cmp-print-frame";
  frame.setAttribute("aria-hidden", "true");
  frame.title = table.labels.reportTitle;
  frame.style.cssText = "position:fixed;inset-inline-end:0;bottom:0;width:0;height:0;border:0;visibility:hidden";
  frame.srcdoc = comparisonReportHtml(table);
  frame.onload = () => {
    try {
      frame.contentWindow?.focus();
      frame.contentWindow?.print();
    } catch {
      /* printing blocked by the browser; the frame stays for a retry */
    }
  };
  document.body.appendChild(frame);
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
