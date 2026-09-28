# Frame 07 - Review Detail (Deeply Enhanced)

## Purpose

Evidence‑first verification screen where the Coordinator compares extracted data to the document, corrects errors, and explicitly approves or rejects.

## Visual Narrative

The left panel is a dark inspection surface with a bright document page and translucent highlights. The right panel is a clean, stacked checklist with a sticky action bar at the top. The experience feels like a professional review station rather than a generic form.

## Composition and Measurements

- Canvas: 1440x900.
- Left panel: 55% width, dark background.
- Right panel: 45% width, white cards.
- Sticky action bar: 56px height.

## Key Components and Microcopy

Left panel:

- Toolbar with page arrows, page input, zoom select.
- Document page centered with soft shadow.
- Colored bounding boxes and labels.
- Thumbnail strip for page navigation.

Right panel:

- Sticky action bar: “6 of 8 fields confirmed.” Buttons: Approve (disabled), Reject.
- Extraction Info card with:
- Status: Pending Review.
- Document ID: 1024.
- Template: CPR_FirstAid v3.
- Created: Feb 2, 2026 10:14 AM.
- Review Required card listing reasons.
- Extracted Fields list with rows:
- Certificate Holder Name (92% confidence) value “Ana Ruiz.”
- Certificate Type (88%) value “CPR / First Aid.”
- Issue Date (74%) value “01/15/2026.”
- Expiration Date (68%) value “01/15/2028.”
- Each row has Confirm and Edit buttons and candidate chips.
- Field audit link: “View provenance.”

## System States

- Document loading spinner.
- Error banner if document fails to load.
- Approved/Rejected state locks fields and shows decision timestamp.

## Interactions

- Clicking field highlights bounding box.
- Clicking highlight scrolls to field.
- Approve enables only when all fields confirmed.

## Accessibility and Keyboard

- Keyboard shortcuts: N/P for page, A for approve, R for reject.
- Visible focus rings on fields and buttons.

## Responsive Behavior

- At 1024px: panels stack, document panel becomes 50vh.
- Sticky action bar remains visible.

## Spec Alignment

- Implements evidence‑rich side‑by‑side review with human approval gate.

## Branding

- City crest: `CityOfLaredoLogos/CityOfLaredoLogo.png` placed in the header (left).
- Public Health logo: `CityOfLaredoLogos/CityOfLaredoPublicHealthLogo.png` placed near the title or right side.
- If the source logo has a dark background, place it on a white pill with 8px padding to preserve contrast.

## Design System Reference

See `Storyboard/Design-System.md` for shared tokens.

## Nano Banana Meta Prompt

```text
Create a flat, modern review detail UI mockup (no device). Canvas 1440x900. Light theme background (#f5f7fb) with deep navy accents (#1a365d). Header bar with blue gradient (#1a365d to #2c5282), left city seal, title “Review Extraction #551,” right identity cluster. Two-column layout. Left: dark document viewer (charcoal #1a1a2e) with toolbar (page arrows, page number input, zoom dropdown), a centered PDF page with translucent colored bounding boxes and small labels, and a thumbnail strip below. Right: white stacked cards and a sticky action bar at top reading “6 of 8 fields confirmed.” Buttons: Approve (disabled, blue) and Reject (red). Info card with status, document ID, template, created date. Warning card “Review Required.” Extracted Fields list with confidence badges and Confirm/Edit buttons plus small candidate chips. Official, calm, minimal.
Use these exact logo images: CityOfLaredoLogo.png (crest) and CityOfLaredoPublicHealthLogo.png (Public Health). Place the crest on the far left of the header and the Public Health logo near the title or right side; if a logo has a dark background, place it on a white pill with 8px padding.
```

## Nano Banana Meta Prompt (Dark Theme)

```text
Create a flat, modern review detail UI mockup (no device). Canvas 1440x900. Dark theme background #0b1220 with deep navy accents. Header bar with indigo gradient (#1e3a8a to #0f172a), left city seal, title “Review Extraction #551,” right identity cluster. Two-column layout. Left: dark document viewer (#111827) with toolbar, centered PDF page, translucent colored bounding boxes, and a thumbnail strip. Right: stacked charcoal cards and a sticky action bar at top reading “6 of 8 fields confirmed.” Buttons: Approve (disabled, indigo) and Reject (red #f87171). Info card with status, document ID, template, created date. Warning card. Extracted Fields list with confidence badges and Confirm/Edit buttons plus candidate chips. Text in #f8fafc and #cbd5e1. Minimal, official, calm.
Use these exact logo images: CityOfLaredoLogo.png (crest) and CityOfLaredoPublicHealthLogo.png (Public Health). Place the crest on the far left of the header and the Public Health logo near the title or right side; if a logo has a dark background, place it on a white pill with 8px padding.
```
