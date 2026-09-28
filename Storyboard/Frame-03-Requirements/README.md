# Frame 03 - Requirements List (Deeply Enhanced)

## Purpose

Shows assigned requirements and makes urgency unmistakable. The screen should read like a clear, well‑ruled register with filters and a visible legend.

## Visual Narrative

Under the civic header, a clean control bar with search and filters appears, followed by a color legend explaining status badges. The table card feels like a ledger page, with consistent row spacing and a subtle right‑aligned “days remaining” pill for each row.

## Composition and Measurements

- Canvas: 1440x900.
- Header: 64px.
- Filters row: 56px height.
- Table card: full width of content column.

## Key Components and Microcopy

- Search field placeholder: “Search certificates, employee, or type.”
- Status filter: All, In Progress, Due Soon, Overdue, Satisfied, Waived.
- Export button: “Export CSV.”
- Legend chips with labels and colors.
- Table columns: Certificate Type, Due Date, Status, Assigned By, Actions, Days Left.

Sample rows:

- CPR / First Aid — Mar 15, 2026 — Due Soon — Dr. Morgan — Upload Certificate — “15 days”.
- Bloodborne Pathogens — Jan 20, 2026 — Satisfied — System — Completed — “—”.
- HazMat Awareness — Jan 05, 2026 — Overdue — Dr. Morgan — Upload Certificate — “Overdue by 29 days”.
- HIPAA Training — Apr 01, 2026 — In Progress — System — Upload Certificate — “58 days”.

## System States

- Loading: table skeleton rows.
- Empty: “No requirements assigned.”
- Error: red banner above filters.

## Interactions

- Filters update table in place.
- Row hover adds a light gray tint.
- Upload button opens the upload screen.

## Accessibility and Keyboard

- Status is text + color.
- Table supports keyboard row focus.

## Responsive Behavior

- At 768px: table scrolls horizontally; Days Left column collapses into Status.
- At 480px: actions stack under each row.

## Spec Alignment

- Reinforces due date tracking independent of expiration.

## Branding

- City crest: `CityOfLaredoLogos/CityOfLaredoLogo.png` placed in the header (left).
- Public Health logo: `CityOfLaredoLogos/CityOfLaredoPublicHealthLogo.png` placed near the title or right side.
- If the source logo has a dark background, place it on a white pill with 8px padding to preserve contrast.

## Design System Reference

See `Storyboard/Design-System.md` for shared tokens.

## Nano Banana Meta Prompt

```text
Create a flat, modern requirements table UI mockup (no device). Canvas 1440x900. Light theme with soft blue background (#f5f7fb), deep navy accents (#1a365d), slate text (#4a5568). Header bar with blue gradient (#1a365d to #2c5282), left city seal, title “Certification Requirements,” right identity cluster. Below, a white filter row with a search field (“Search certificates, employee, or type”), a status dropdown, and “Export CSV” button. Add a legend row with colored chips labeled In Progress, Due Soon, Overdue, Satisfied, Waived. Main white table card with columns Certificate Type, Due Date, Status, Assigned By, Actions, Days Left. Show 4 sample rows with realistic dates and status badges. Include right‑aligned days‑left pills (e.g., “15 days”, “Overdue by 29 days”). Clean, official, minimal.
Use these exact logo images: CityOfLaredoLogo.png (crest) and CityOfLaredoPublicHealthLogo.png (Public Health). Place the crest on the far left of the header and the Public Health logo near the title or right side; if a logo has a dark background, place it on a white pill with 8px padding.
```

## Nano Banana Meta Prompt (Dark Theme)

```text
Create a flat, modern requirements table UI mockup (no device). Canvas 1440x900. Dark theme with background #0b1220 and charcoal surfaces #111827. Header bar with indigo gradient (#1e3a8a to #0f172a), left city seal, title “Certification Requirements,” right identity cluster. Below, a dark filter row with a search field (“Search certificates, employee, or type”), status dropdown, and “Export CSV” button. Add a legend row with colored chips for In Progress, Due Soon, Overdue, Satisfied, Waived. Main table card in charcoal with a slightly lighter header row (#1f2937). Columns: Certificate Type, Due Date, Status, Assigned By, Actions, Days Left. Show 4 sample rows with status badges and right-aligned days-left pills. Text in #f8fafc and #cbd5e1. Minimal, official, calm.
Use these exact logo images: CityOfLaredoLogo.png (crest) and CityOfLaredoPublicHealthLogo.png (Public Health). Place the crest on the far left of the header and the Public Health logo near the title or right side; if a logo has a dark background, place it on a white pill with 8px padding.
```
