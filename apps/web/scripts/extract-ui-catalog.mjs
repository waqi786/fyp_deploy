import fs from "node:fs";
import path from "node:path";
import ts from "typescript";

const root = path.resolve(import.meta.dirname, "..");
const src = path.join(root, "src");
const output = path.join(src, "i18n", "catalogs", "en.json");
const checkOnly = process.argv.includes("--check");
const messages = new Set();
const visibleAttributes = new Set(["aria-label", "title", "placeholder", "alt"]);
const visibleProperties = new Set(["label", "title", "description", "name", "placeholder", "error", "success", "message", "hint", "caption", "status", "emptyLabel", "helpText"]);

function filesUnder(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const target = path.join(directory, entry.name);
    return entry.isDirectory() ? filesUnder(target) : /\.[jt]sx?$/.test(entry.name) && !/\.(test|spec)\.[jt]sx?$/.test(entry.name) ? [target] : [];
  });
}

function add(value, allowWord = false) {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (!normalized || normalized.length < 2 || normalized.length > 500 || !/[\p{L}]/u.test(normalized)) return;
  if (/^(?:https?:\/\/|\/|#[\w-]+$)/i.test(normalized) || /^(?:GET|POST|PUT|PATCH|DELETE)\s/i.test(normalized)) return;
  if (!allowWord && /^[a-z][a-z\d]*(?:[_-][a-z\d]+)*$/.test(normalized)) return;
  if (/(?:Ã.|Ø.|Ù.|à¤|æ.|ä.)/.test(normalized)) return;
  if (/^[\w./:-]+$/.test(normalized) && !/[A-Z]/.test(normalized)) return;
  messages.add(normalized);
}

function literalValue(node) {
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return node.text;
  if (ts.isTemplateExpression(node)) {
    let value = node.head.text;
    node.templateSpans.forEach((span, index) => {
      const expression = span.expression;
      const name = ts.isIdentifier(expression) ? expression.text : `value${index + 1}`;
      value += `{${name}}${span.literal.text}`;
    });
    return value;
  }
  return undefined;
}

function propertyName(node) {
  if (ts.isIdentifier(node)) return node.text;
  if (ts.isStringLiteral(node) || ts.isNumericLiteral(node)) return node.text;
  return undefined;
}

function collectObjectValues(node) {
  if (!ts.isObjectLiteralExpression(node)) return;
  for (const property of node.properties) {
    if (!ts.isPropertyAssignment(property)) continue;
    const value = literalValue(property.initializer);
    if (value !== undefined) add(value, true);
    else collectObjectValues(property.initializer);
  }
}

for (const file of filesUnder(src)) {
  const source = fs.readFileSync(file, "utf8");
  const tree = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, file.endsWith(".tsx") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  function visit(node) {
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.initializer && ts.isObjectLiteralExpression(node.initializer)) {
      const variable = node.name.text;
      if (variable === "copy" || variable.endsWith("Copy") || variable.endsWith("Labels")) {
        const english = node.initializer.properties.find((item) => ts.isPropertyAssignment(item) && propertyName(item.name) === "en");
        if (english && ts.isPropertyAssignment(english)) collectObjectValues(english.initializer);
      }
      if (["exact", "terms", "moreTerms"].includes(variable)) {
        const collectKeys = (object) => {
          if (!ts.isObjectLiteralExpression(object)) return;
          for (const property of object.properties) {
            if (!ts.isPropertyAssignment(property)) continue;
            if (ts.isStringLiteral(property.name)) add(property.name.text, true);
            collectKeys(property.initializer);
          }
        };
        collectKeys(node.initializer);
      }
    }
    if (ts.isJsxText(node)) add(node.text, true);
    if (ts.isJsxAttribute(node) && node.initializer && ts.isStringLiteral(node.initializer) && visibleAttributes.has(propertyName(node.name) || "")) add(node.initializer.text, true);
    if (ts.isPropertyAssignment(node) && visibleProperties.has(propertyName(node.name) || "")) {
      const value = literalValue(node.initializer);
      if (value !== undefined) add(value, true);
    }
    if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node) || ts.isTemplateExpression(node)) {
      const parent = node.parent;
      const attribute = ts.isJsxAttribute(parent) ? propertyName(parent.name) : undefined;
      if (attribute === "className" || attribute === "id" || attribute === "key" || attribute === "data-testid") return ts.forEachChild(node, visit);
      if (ts.isJsxAttribute(parent) && !visibleAttributes.has(attribute || "")) return ts.forEachChild(node, visit);
      if (parent && (ts.isImportDeclaration(parent) || ts.isExportDeclaration(parent))) return ts.forEachChild(node, visit);
      const value = literalValue(node);
      if (value !== undefined && ts.isCallExpression(parent) && node === parent.arguments[0]) {
        const callee = parent.expression.getText(tree);
        if (/(?:setError|setNotice|setStatus|setSuccess|toast|alert|confirm|notify)/i.test(callee)) add(value, true);
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(tree);
}

const catalog = Object.fromEntries([...messages].sort((a, b) => a.localeCompare(b)).map((message) => [message, message]));
fs.mkdirSync(path.dirname(output), { recursive: true });
if (checkOnly) {
  const previous = JSON.parse(fs.readFileSync(output, "utf8"));
  const missing = Object.keys(catalog).filter((message) => !(message in previous));
  if (missing.length) {
    console.error(`Found ${missing.length} new hardcoded UI messages. Run npm run i18n:extract.`);
    console.error(missing.slice(0, 30).join("\n"));
    process.exitCode = 1;
  } else {
    console.log(`Hardcoded UI check passed (${messages.size} messages)`);
  }
} else {
  fs.writeFileSync(output, `${JSON.stringify(catalog, null, 2)}\n`, "utf8");
  console.log(`Extracted ${messages.size} source messages into ${path.relative(root, output)}`);
}
