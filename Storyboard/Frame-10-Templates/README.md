# Frame 10 - Template Registry (Deeply Enhanced)

## Purpose

Displays active extraction templates, versions, and zones. It should be precise, technical, and trustworthy, like a system registry.

## Visual Narrative

The registry hash strip reads like a system fingerprint. A search bar and filter row allow quick narrowing. Cards stack vertically, each expanding to reveal zone tables with normalized coordinates. A Preview button opens a modal showing the template overlay on a sample certificate.

## Composition and Measurements

- Canvas: 1440x900.
- Card width: content column (1200px).
- Expanded table height: ~260px.

## Key Components and Microcopy

- Registry hash: “9f8a1c3b7a2e...”
- Template count: “3 templates.”
- Search placeholder: “Search templates or certificate types.”
- Filter dropdown: Certificate Type.
- Template card header:
- Name: “CPR / First Aid.”
- Template ID: “cpr_firstaid.”
- Version badge: “v3.”
- Expanded content:
- Description: “Standard City of Laredo CPR/First Aid certificate.”
- Zones table with Field Name, BBox [x1,y1,x2,y2], Required.
- Created and Updated timestamps.
- Button: “Preview Template.”

## System States

- Empty: “No templates configured.”
- Error: red banner if registry fails.

## Interactions

- Expand/collapse cards.
- Preview opens overlay modal with sample document and zones.

## Accessibility and Keyboard

- Expand toggle and preview button are keyboard accessible.

## Responsive Behavior

- Zones table scrolls horizontally on small screens.

## Spec Alignment

- Supports versioned, runtime-loaded template registry.

## Branding

- City crest: `CityOfLaredoLogos/CityOfLaredoLogo.png` placed in the header (left).
- Public Health logo: `CityOfLaredoLogos/CityOfLaredoPublicHealthLogo.png` placed near the title or right side.
- If the source logo has a dark background, place it on a white pill with 8px padding to preserve contrast.

## Design System Reference

See `Storyboard/Design-System.md` for shared tokens.

## Nano Banana Meta Prompt

```text
Create a flat, modern template registry UI mockup (no device). Canvas 1440x900. Light theme with soft blue background (#f5f7fb), deep navy accents (#1a365d), slate text (#4a5568). Header bar with blue gradient (#1a365d to #2c5282), left city seal, title “Template Registry,” right identity cluster. Below, a white info strip showing “Registry Hash: 9f8a1c3b7a2e...” and “3 templates.” Add a search input (“Search templates or certificate types”) and a certificate type filter dropdown. Main area: vertical list of white template cards. One card expanded showing description, zones table with Field Name, BBox, Required, timestamps, and a “Preview Template” button. Template ID displayed in monospace. Clean, technical, official.
Use these exact logo images: CityOfLaredoLogo.png (crest) and CityOfLaredoPublicHealthLogo.png (Public Health). Place the crest on the far left of the header and the Public Health logo near the title or right side; if a logo has a dark background, place it on a white pill with 8px padding.
```

## Nano Banana Meta Prompt (Dark Theme)

```text
Create a flat, modern template registry UI mockup (no device). Canvas 1440x900. Dark theme with background #0b1220 and charcoal cards #111827. Header bar with indigo gradient (#1e3a8a to #0f172a), left city seal, title “Template Registry,” right identity cluster. Below, a dark info strip showing “Registry Hash: 9f8a1c3b7a2e...” and “3 templates.” Add a search input and certificate type filter. Main area: vertical list of dark template cards. One card expanded showing description, zones table with Field Name, BBox, Required, timestamps, and a “Preview Template” button. Template ID in monospace. Text in #f8fafc and #cbd5e1. Clean, technical, official.
Use these exact logo images: CityOfLaredoLogo.png (crest) and CityOfLaredoPublicHealthLogo.png (Public Health). Place the crest on the far left of the header and the Public Health logo near the title or right side; if a logo has a dark background, place it on a white pill with 8px padding.
```
