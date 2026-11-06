# Resora Design System

## Current Active Theme

The active product theme follows the latest user override:

- page background: pure black
- panels: near-black
- primary text: white
- primary action/accent: neon orange
- intelligence/data accent: neon blue
- live/success accent: neon green
- danger/blocker/warning accent: neon red

This keeps the product in a high-contrast black/white SaaS shell while adding the requested neon orange, neon blue, neon green, and neon red accents.

No extra accent colors should be introduced outside black, white, neon orange, neon blue, neon green, and neon red.

## Token Contract

The canonical implementation lives in:

- `apps/web/tailwind.config.js`
- `apps/web/src/styles/tailwind.css`

Required tokens:

- `--ink`
- `--panel`
- `--panel-raised`
- `--panel-hi`
- `--paper`
- `--paper-ink`
- `--text`
- `--text-dim`
- `--text-faint`
- `--border`
- `--border-hi`
- `--gold`
- `--gold-soft`
- `--gold-text`
- `--teal`
- `--teal-soft`
- `--teal-text`
- `--coral`
- `--coral-soft`
- `--coral-text`

## Layout Contract

Authenticated screens use the Resora workbench structure:

- left icon rail
- center scrollable canvas
- contextual right panel where the screen needs one
- sticky topbar on non-search screens
- keyboard-visible focus rings

## Shared Components

- `TrustRing` is the single score/confidence ring implementation.
- `status-pill-*` classes provide status language.
- `source-badge` provides source/citation badges.
- `paper-quote` marks source-grounded passages.

## Accessibility Contract

- visible focus state on interactive elements
- high-contrast compatible token choices
- RTL toggle support through document direction
- neon effects are decorative and paired with readable text/borders
- no bare spinners for content-heavy states
- `prefers-reduced-motion` is respected for transitions and animations
