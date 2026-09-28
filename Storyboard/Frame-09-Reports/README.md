# Frame 09 - Compliance Reports (Deeply Enhanced)

## Purpose

Executive overview of compliance with trend visibility and export options for monthly reporting.

## Visual Narrative

The header is civic and calm. A summary row presents headline numbers. A simple line chart shows the compliance trend across six months. A status breakdown card shows counts and thin bars. A structured table by certificate type anchors the bottom. The page feels like a report ready to export.

## Composition and Measurements

- Canvas: 1440x900.
- Summary card row: 3 cards.
- Chart card: 400px tall.

## Key Components and Microcopy

- Date range selector: Month / Quarter / Year.
- Export button: “Export CSV” and dropdown “Export XLSX.”
- Summary cards:
- Overall Compliance: 92%.
- Total Employees: 146.
- Total Requirements: 512.
- Trend chart: Jan–Jun with a line rising from 86% to 92%.
- Status breakdown tiles: Compliant 402, Due Soon 61, Overdue 33, Waived 16.
- By Type table with compliance rate badges.

## System States

- Loading: chart skeleton and table placeholder.
- Empty: “No requirements in the selected period.”

## Interactions

- Date range updates chart and table.
- Export triggers download.

## Accessibility and Keyboard

- Chart includes a textual summary below: “Compliance increased 6% over 6 months.”
- Buttons and selectors keyboard accessible.

## Responsive Behavior

- At 768px: cards stack, chart becomes full width.

## Spec Alignment

- Supports monthly reporting and compliance computation.

## Branding

- City crest: `CityOfLaredoLogos/CityOfLaredoLogo.png` placed in the header (left).
- Public Health logo: `CityOfLaredoLogos/CityOfLaredoPublicHealthLogo.png` placed near the title or right side.
- If the source logo has a dark background, place it on a white pill with 8px padding to preserve contrast.

## Design System Reference

See `Storyboard/Design-System.md` for shared tokens.

## Nano Banana Meta Prompt

```text
Create a flat, modern compliance reports UI mockup (no device). Canvas 1440x900. Light theme with soft blue background (#f5f7fb), deep navy accents (#1a365d), slate text (#4a5568). Header bar with blue gradient (#1a365d to #2c5282), left city seal, title “Compliance Reports,” right identity cluster. Add a date range selector (Month/Quarter/Year) and Export buttons (“Export CSV”, “Export XLSX”). Main content: three summary cards with the first highlighted in blue gradient showing “92% Overall Compliance.” Add a white line chart card labeled “Compliance Trend” with months Jan–Jun and a line rising from 86% to 92%. Add a white “Status Breakdown” card with four tiles and slim progress bars. Final white card with “By Certificate Type” table and compliance rate badges. Official, calm, minimal.
Use these exact logo images: CityOfLaredoLogo.png (crest) and CityOfLaredoPublicHealthLogo.png (Public Health). Place the crest on the far left of the header and the Public Health logo near the title or right side; if a logo has a dark background, place it on a white pill with 8px padding.
```

## Nano Banana Meta Prompt (Dark Theme)

```text
Create a flat, modern compliance reports UI mockup (no device). Canvas 1440x900. Dark theme with background #0b1220 and charcoal cards #111827. Header bar with indigo gradient (#1e3a8a to #0f172a), left city seal, title “Compliance Reports,” right identity cluster. Add date range selector and Export buttons. Main content: three summary cards with the first highlighted in indigo gradient showing “92% Overall Compliance.” Add a dark chart card with a line rising from 86% to 92%. Add a “Status Breakdown” card with four tiles and slim progress bars. Final card with “By Certificate Type” table and compliance rate badges. Text in #f8fafc and #cbd5e1. Minimal, official, calm.
Use these exact logo images: CityOfLaredoLogo.png (crest) and CityOfLaredoPublicHealthLogo.png (Public Health). Place the crest on the far left of the header and the Public Health logo near the title or right side; if a logo has a dark background, place it on a white pill with 8px padding.
```
