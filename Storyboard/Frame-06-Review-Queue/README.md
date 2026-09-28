# Frame 06 - Review Queue (Deeply Enhanced)

## Purpose

Acts as the Coordinator’s inbox. It should reveal urgency, workload, and document age at a glance.

## Visual Narrative

The header is stable and civic. A small summary strip displays counts for Pending, Approved, and Rejected. Below, a filter row includes search, status, confidence, and age sorting. The grid of cards feels like neatly arranged index cards, each clearly labeled with status, confidence, and days in queue.

## Composition and Measurements

- Canvas: 1440x900.
- Summary strip: 48px height.
- Filter row: 56px height.
- Card grid: 3 columns.

## Key Components and Microcopy

- Summary pills: Pending 6, Approved 18, Rejected 2.
- Search field: “Search by employee or certificate.”
- Dropdowns: Status, Confidence, Age in queue.
- Card content:
- ID: “#551.”
- Employee: “Ana Ruiz.”
- Certificate: “CPR / First Aid.”
- Status badge: “Pending Review.”
- Confidence: “82%.”
- Fields for review: “2.”
- Days in queue: “3 days.”
- Flag: “Name mismatch” (small amber tag).

## System States

- Loading: card skeletons.
- Empty: “No documents waiting for review.”
- Error: red banner above filters.

## Interactions

- Sorting updates the grid order.
- Cards open review detail.

## Accessibility and Keyboard

- Cards are focusable and have visible focus rings.

## Responsive Behavior

- On mobile, cards stack in one column.
- Filters collapse into an expandable panel.

## Spec Alignment

- Highlights the workload and priority signals for the review process.

## Branding

- City crest: `CityOfLaredoLogos/CityOfLaredoLogo.png` placed in the header (left).
- Public Health logo: `CityOfLaredoLogos/CityOfLaredoPublicHealthLogo.png` placed near the title or right side.
- If the source logo has a dark background, place it on a white pill with 8px padding to preserve contrast.

## Design System Reference

See `Storyboard/Design-System.md` for shared tokens.

## Nano Banana Meta Prompt

```text
Create a flat, modern review queue UI mockup (no device). Canvas 1440x900. Light theme with soft blue background (#f5f7fb), deep navy accents (#1a365d), slate text (#4a5568). Header bar with blue gradient (#1a365d to #2c5282), left city seal, title “Review Queue,” right identity cluster. Below, a slim summary strip with pills: Pending 6, Approved 18, Rejected 2. Next, a white filter row with a search field “Search by employee or certificate,” and dropdowns for Status, Confidence, Age in queue. Main area: 3‑column grid of white extraction cards. Each card shows ID #551, employee “Ana Ruiz,” certificate “CPR / First Aid,” yellow “Pending Review” badge, confidence 82%, fields for review 2, “3 days in queue,” and a small amber tag “Name mismatch.” Clean, official, minimal.
Use these exact logo images: CityOfLaredoLogo.png (crest) and CityOfLaredoPublicHealthLogo.png (Public Health). Place the crest on the far left of the header and the Public Health logo near the title or right side; if a logo has a dark background, place it on a white pill with 8px padding.
```

## Nano Banana Meta Prompt (Dark Theme)

```text
Create a flat, modern review queue UI mockup (no device). Canvas 1440x900. Dark theme with background #0b1220 and charcoal cards #111827. Header bar with indigo gradient (#1e3a8a to #0f172a), left city seal, title “Review Queue,” right identity cluster. Summary strip with pills: Pending 6, Approved 18, Rejected 2. Filter row with search field and dropdowns for Status, Confidence, Age in queue. Main area: 3-column grid of extraction cards. Each card shows ID #551, employee “Ana Ruiz,” certificate “CPR / First Aid,” yellow “Pending Review” badge, confidence 82%, fields for review 2, “3 days in queue,” and a small amber tag “Name mismatch.” Text in #f8fafc and #cbd5e1. Minimal, official, calm.
Use these exact logo images: CityOfLaredoLogo.png (crest) and CityOfLaredoPublicHealthLogo.png (Public Health). Place the crest on the far left of the header and the Public Health logo near the title or right side; if a logo has a dark background, place it on a white pill with 8px padding.
```
