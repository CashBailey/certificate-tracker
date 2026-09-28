# Frame 04 - Upload Certificate (Deeply Enhanced)

## Purpose

Provides the manual upload path and highlights safe validation. It should visibly reinforce that email is the primary intake path and this is for exceptions.

## Visual Narrative

A large dashed drop zone sits on the left like a clean tray. On the right, a vertical checklist confirms file eligibility. A slim info callout below the button reminds users that email submission is preferred. The overall tone is reassuring and deliberate.

## Composition and Measurements

- Canvas: 1440x900.
- Card width: ~700px, split 60/40 (drop zone/checklist).
- Drop zone height: 260px.

## Key Components and Microcopy

- Drop zone text: “Drag and drop your certificate here, or browse.”
- Hint line: “Supported formats: PDF, JPEG, PNG, TIFF (max 20MB).”
- Checklist items:
- “File type accepted.”
- “File size under 20MB.”
- “Virus scan complete.”
- File preview row: “CPR_2026.pdf — 1.2 MB.”
- Remove file icon (x).
- Upload button text: “Upload Document.”
- Info callout: “Primary submission is via city email; upload is for exceptions.”

## System States

- Drag‑over: blue border + faint blue fill.
- File selected: green border + preview row.
- Uploading: progress bar (0–100%).
- Error: red banner with details.

## Interactions

- Drop zone accepts drag and drop.
- Browse opens file picker.
- Remove clears selection.

## Accessibility and Keyboard

- Browse link is keyboard accessible.
- Validation messages are text‑based.

## Responsive Behavior

- At 768px: drop zone and checklist stack vertically.

## Spec Alignment

- Manual upload is explicitly labeled as an exception path.

## Branding

- City crest: `CityOfLaredoLogos/CityOfLaredoLogo.png` placed in the header (left).
- Public Health logo: `CityOfLaredoLogos/CityOfLaredoPublicHealthLogo.png` placed near the title or right side.
- If the source logo has a dark background, place it on a white pill with 8px padding to preserve contrast.

## Design System Reference

See `Storyboard/Design-System.md` for shared tokens.

## Nano Banana Meta Prompt

```text
Create a flat, modern upload UI mockup (no device). Canvas 1440x900. Light theme with soft blue background (#f5f7fb), deep navy accents (#1a365d), slate text (#4a5568). Header bar with blue gradient (#1a365d to #2c5282), left city seal, title “Upload Certificate,” right identity cluster. Centered white card (~700px wide) split into two columns. Left: large dashed drop zone (260px tall) with icon and text “Drag and drop your certificate here, or browse” (browse underlined). Hint line: “Supported formats: PDF, JPEG, PNG, TIFF (max 20MB).” Right: vertical checklist with green check icons: File type accepted, File size under 20MB, Virus scan complete. Below, show a file preview row “CPR_2026.pdf — 1.2 MB” and a small remove icon. Add a blue “Upload Document” button and a thin progress bar below it. Add a light gray info callout: “Primary submission is via city email; upload is for exceptions.” Clean, official, minimal.
Use these exact logo images: CityOfLaredoLogo.png (crest) and CityOfLaredoPublicHealthLogo.png (Public Health). Place the crest on the far left of the header and the Public Health logo near the title or right side; if a logo has a dark background, place it on a white pill with 8px padding.
```

## Nano Banana Meta Prompt (Dark Theme)

```text
Create a flat, modern upload UI mockup (no device). Canvas 1440x900. Dark theme with background #0b1220 and charcoal card #111827. Header bar with indigo gradient (#1e3a8a to #0f172a), left city seal, title “Upload Certificate,” right identity cluster. Centered card (~700px wide) split into two columns. Left: large dashed drop zone (260px tall) with icon and text “Drag and drop your certificate here, or browse” (browse in blue #60a5fa). Hint line: “Supported formats: PDF, JPEG, PNG, TIFF (max 20MB).” Right: checklist with green check icons (#34d399). Below, file preview row “CPR_2026.pdf — 1.2 MB” and a small remove icon. Add a blue indigo “Upload Document” button and a thin progress bar below. Add a muted gray callout: “Primary submission is via city email; upload is for exceptions.” Text in #f8fafc and #cbd5e1. Minimal, official, calm.
Use these exact logo images: CityOfLaredoLogo.png (crest) and CityOfLaredoPublicHealthLogo.png (Public Health). Place the crest on the far left of the header and the Public Health logo near the title or right side; if a logo has a dark background, place it on a white pill with 8px padding.
```
