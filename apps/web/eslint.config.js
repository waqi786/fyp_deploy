import js from "@eslint/js";
import tseslint from "typescript-eslint";
import react from "eslint-plugin-react";
import hooks from "eslint-plugin-react-hooks";
import a11y from "eslint-plugin-jsx-a11y";
import globals from "globals";

const hardcodedUiText = {
  meta: { type: "suggestion", docs: { description: "Flag literal user-facing JSX text for catalog review" }, schema: [] },
  create(context) {
    return {
      JSXText(node) {
        const text = node.value.replace(/\s+/g, " ").trim();
        if (!text || !/[A-Za-z\u00C0-\u024F\u0600-\u06FF\u0900-\u097F\u4E00-\u9FFF]/u.test(text)) return;
        context.report({ node, message: "Move user-visible text to a UI catalog (or add an i18n-ignore comment for proper nouns)." });
      },
      JSXAttribute(node) {
        if (!["aria-label", "placeholder", "title", "alt"].includes(node.name.name)) return;
        if (node.value?.type !== "Literal" || typeof node.value.value !== "string") return;
        if (!/[A-Za-z\u00C0-\u024F\u0600-\u06FF\u0900-\u097F\u4E00-\u9FFF]/u.test(node.value.value)) return;
        context.report({ node, message: "Move user-visible attribute text to a UI catalog." });
      },
    };
  },
};

const resora = { rules: { "hardcoded-ui-text": hardcodedUiText } };
export default tseslint.config(
  { ignores: ["dist/**", "test-results/**", "artifacts/**"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.{js,jsx,ts,tsx}"],
    plugins: { react, "react-hooks": hooks, "jsx-a11y": a11y, resora },
    settings: { react: { version: "detect" } },
    rules: {
      ...react.configs.recommended.rules,
      ...hooks.configs.flat.recommended.rules,
      ...a11y.configs.recommended.rules,
      "react/react-in-jsx-scope": "off",
      "react/prop-types": "off",
      "@typescript-eslint/no-unused-vars": "warn",
      "no-constant-condition": "warn",
      "no-useless-escape": "warn",
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/purity": "warn",
      ...Object.fromEntries(Object.keys(a11y.configs.recommended.rules).map((rule) => [rule, "warn"])),
      "resora/hardcoded-ui-text": "off",
    },
    languageOptions: {
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
  },
  {
    files: ["src/components/ui/**/*.{js,jsx,ts,tsx}"],
    plugins: { resora },
    rules: { "resora/hardcoded-ui-text": "warn" },
  },
);
