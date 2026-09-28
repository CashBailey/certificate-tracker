# Frame 11 - Employee Management (Deeply Enhanced)

## Purpose

Manages employee accounts and roles with strong governance cues. It should read like an official roster.

## Visual Narrative

A clean toolbar sits under the civic header. The table card feels like a formal registry with subtle row dividers. A small “Audit Log” link reinforces accountability.

## Composition and Measurements

- Canvas: 1440x900.
- Toolbar height: 56px.
- Table card width: content column.

## Key Components and Microcopy

- Search placeholder: “Search name, email, or employee #.”
- Filters: Role (All, Admin, Coordinator, Employee), Status (Active, Inactive).
- Buttons: “Add Employee” (green), “Bulk Import.”
- Table columns: Employee #, Name, Email, Role, Status, Actions.
- Row examples:
- 1023 — Carla Morgan — Coordinator — Active.
- 1148 — Ana Ruiz — Employee — Active.
- 1202 — Jorge Silva — Employee — Inactive.
- Actions: Edit, Deactivate or Reactivate.
- Pagination: “Showing 1–20 of 84.”

## System States

- Loading skeleton rows.
- Empty state: “No employees match your filters.”
- Error banner above table.

## Interactions

- Deactivate prompts confirmation.
- Self‑deactivation disabled.

## Accessibility and Keyboard

- Table rows keyboard focusable.
- Role badges include text labels.

## Responsive Behavior

- Table becomes horizontally scrollable at 768px.
- Actions stack vertically on mobile.

## Spec Alignment

- Supports role-based access and controlled provisioning.

## Branding

- City crest: `CityOfLaredoLogos/CityOfLaredoLogo.png` placed in the header (left).
- Public Health logo: `CityOfLaredoLogos/CityOfLaredoPublicHealthLogo.png` placed near the title or right side.
- If the source logo has a dark background, place it on a white pill with 8px padding to preserve contrast.

## Design System Reference

See `Storyboard/Design-System.md` for shared tokens.

## Nano Banana Meta Prompt

```text
Create a flat, modern employee management UI mockup (no device). Canvas 1440x900. Light theme with soft blue background (#f5f7fb), deep navy accents (#1a365d), slate text (#4a5568). Header bar with blue gradient (#1a365d to #2c5282), left city seal, title “Employee Management,” right identity cluster. Toolbar row below with a search input (“Search name, email, or employee #”), role filter dropdown, status filter dropdown, green “Add Employee” button, and “Bulk Import” button. Main white table card with columns Employee #, Name, Email, Role, Status, Actions. Show 5 rows with role badges and status badges. Include small “Audit Log” link near the table title. Bottom pagination bar: “Showing 1–20 of 84” with Previous/Next. Clean, official, minimal.
Use these exact logo images: CityOfLaredoLogo.png (crest) and CityOfLaredoPublicHealthLogo.png (Public Health). Place the crest on the far left of the header and the Public Health logo near the title or right side; if a logo has a dark background, place it on a white pill with 8px padding.
```

## Nano Banana Meta Prompt (Dark Theme)

```text
Create a flat, modern employee management UI mockup (no device). Canvas 1440x900. Dark theme with background #0b1220 and charcoal cards #111827. Header bar with indigo gradient (#1e3a8a to #0f172a), left city seal, title “Employee Management,” right identity cluster. Toolbar row with search input, role filter, status filter, green “Add Employee” button, and “Bulk Import.” Main table card in charcoal with columns Employee #, Name, Email, Role, Status, Actions. Show 5 rows with role badges and status badges. Include a small “Audit Log” link near the table title. Bottom pagination bar: “Showing 1–20 of 84.” Text in #f8fafc and #cbd5e1. Minimal, official, calm.
Use these exact logo images: CityOfLaredoLogo.png (crest) and CityOfLaredoPublicHealthLogo.png (Public Health). Place the crest on the far left of the header and the Public Health logo near the title or right side; if a logo has a dark background, place it on a white pill with 8px padding.
```
