# Frame 08 - Reject Extraction Modal (Deeply Enhanced)

## Purpose

Captures a formal rejection reason with standardized categories and detailed notes for auditability.

## Visual Narrative

The review screen fades under a charcoal veil. A clean white modal floats at center, with a bold title, a reason category selector, and a large textarea. The Reject button is intentionally strong red, while Cancel is subdued.

## Composition and Measurements

- Modal width: ~520px.
- Padding: 24px.
- Textarea height: ~120px.

## Key Components and Microcopy

- Title: “Reject Extraction.”
- Instruction: “Select a reason and add details for the audit log.”
- Reason dropdown options:
- Unreadable document.
- Wrong employee.
- Missing required fields.
- Duplicate submission.
- Other.
- Textarea placeholder: “Explain the issue and any follow‑up needed.”
- Buttons: Cancel (gray), Reject (red).

## System States

- Reject disabled until a category is chosen and text entered.
- Inline error under textarea if empty.
- Loading state: “Rejecting...”

## Interactions

- Clicking overlay or pressing Escape closes modal.
- Tab order: dropdown → textarea → Cancel → Reject.

## Accessibility and Keyboard

- Focus trapped within modal.
- Screen reader label for dropdown and textarea.

## Spec Alignment

- Ensures explicit rejection reasoning for auditability.

## Branding

- City crest: `CityOfLaredoLogos/CityOfLaredoLogo.png` placed in the header (left).
- Public Health logo: `CityOfLaredoLogos/CityOfLaredoPublicHealthLogo.png` placed near the title or right side.
- If the source logo has a dark background, place it on a white pill with 8px padding to preserve contrast.

## Design System Reference

See `Storyboard/Design-System.md` for shared tokens.

## Nano Banana Meta Prompt

```text
Create a flat, modern reject modal UI mockup (no device). Canvas 1440x900. Light theme background (#f5f7fb) with deep navy accents (#1a365d). The underlying review screen is dimmed by a dark translucent overlay. Center a white modal (~520px wide) with rounded corners and soft shadow. Title “Reject Extraction.” Instruction text “Select a reason and add details for the audit log.” Add a dropdown labeled “Reason” with options (Unreadable document, Wrong employee, Missing required fields, Duplicate submission, Other). Add a multiline textarea with placeholder “Explain the issue and any follow‑up needed.” Bottom right buttons: Cancel (gray) and Reject (red). Minimal, official, calm.
Use these exact logo images: CityOfLaredoLogo.png (crest) and CityOfLaredoPublicHealthLogo.png (Public Health). Place the crest on the far left of the header and the Public Health logo near the title or right side; if a logo has a dark background, place it on a white pill with 8px padding.
```

## Nano Banana Meta Prompt (Dark Theme)

```text
Create a flat, modern reject modal UI mockup (no device). Canvas 1440x900. Dark theme background #0b1220. Underlying review screen dimmed by a dark translucent overlay. Center a charcoal modal (#111827) with rounded corners and soft shadow. Title “Reject Extraction” in white. Instruction text in cool gray. Dropdown labeled “Reason” with options. Multiline textarea with border #1f2937 and blue focus glow #60a5fa. Bottom right buttons: Cancel (gray) and Reject (red #f87171). Minimal, official, calm.
Use these exact logo images: CityOfLaredoLogo.png (crest) and CityOfLaredoPublicHealthLogo.png (Public Health). Place the crest on the far left of the header and the Public Health logo near the title or right side; if a logo has a dark background, place it on a white pill with 8px padding.
```
