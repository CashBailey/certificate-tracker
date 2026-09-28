# Frame 13 - Unauthorized Access (Deeply Enhanced)

## Purpose

Blocks access to restricted routes and guides users back to safe areas, with a gentle path to request access.

## Visual Narrative

A single white card sits centered on the pale blue background. The red “Access Denied” title is clear but not harsh. The message is short and calm. A primary link returns to the dashboard, and a secondary link offers to request access.

## Composition and Measurements

- Card width: ~420px.
- Padding: 24–32px.

## Key Components and Microcopy

- Title: “Access Denied.”
- Message: “You do not have permission to view this page.”
- Primary link: “Return to Dashboard.”
- Secondary link: “Request Access.”
- Optional helper line: “If you believe this is an error, contact IT support.”

## System States

- None beyond static content.

## Interactions

- Return to Dashboard navigates to /.
- Request Access opens a mailto or support form.

## Accessibility and Keyboard

- Links are keyboard focusable with visible focus rings.

## Responsive Behavior

- Card expands to full width with 16px margins on mobile.

## Spec Alignment

- Reinforces role boundaries and Coordinator-only visibility.

## Branding

- City crest: `CityOfLaredoLogos/CityOfLaredoLogo.png` placed in the header (left).
- Public Health logo: `CityOfLaredoLogos/CityOfLaredoPublicHealthLogo.png` placed near the title or right side.
- If the source logo has a dark background, place it on a white pill with 8px padding to preserve contrast.

## Design System Reference

See `Storyboard/Design-System.md` for shared tokens.

## Nano Banana Meta Prompt

```text
Create a flat, modern unauthorized access UI mockup (no device). Canvas 1440x900. Light theme with soft blue background (#f5f7fb), deep navy accents (#1a365d), slate text (#4a5568). Center a white card (~420px wide) with rounded corners and soft shadow. Title “Access Denied” in red (#dc2626). Short message “You do not have permission to view this page.” Add a primary blue link-style button “Return to Dashboard” and a smaller secondary link “Request Access.” Optional helper line: “If you believe this is an error, contact IT support.” Minimal, official, calm.
Use these exact logo images: CityOfLaredoLogo.png (crest) and CityOfLaredoPublicHealthLogo.png (Public Health). Place the crest on the far left of the header and the Public Health logo near the title or right side; if a logo has a dark background, place it on a white pill with 8px padding.
```

## Nano Banana Meta Prompt (Dark Theme)

```text
Create a flat, modern unauthorized access UI mockup (no device). Canvas 1440x900. Dark theme with background #0b1220. Center a charcoal card (#111827) with rounded corners and soft shadow. Title “Access Denied” in red (#f87171). Short message in cool gray. Add a primary blue link-style button “Return to Dashboard” and a smaller secondary link “Request Access.” Optional helper line: “If you believe this is an error, contact IT support.” Minimal, official, calm.
Use these exact logo images: CityOfLaredoLogo.png (crest) and CityOfLaredoPublicHealthLogo.png (Public Health). Place the crest on the far left of the header and the Public Health logo near the title or right side; if a logo has a dark background, place it on a white pill with 8px padding.
```
