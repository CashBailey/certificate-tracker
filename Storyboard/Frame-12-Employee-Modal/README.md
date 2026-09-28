# Frame 12 - Employee Create/Edit Modal (Deeply Enhanced)

## Purpose

Handles account creation and edits without leaving the roster. It should feel like a precise administrative form.

## Visual Narrative

The roster behind dims. The modal card is wide and balanced, with two-column rows and a small helper panel describing role permissions. The layout feels deliberate and authoritative.

## Composition and Measurements

- Modal width: ~640px.
- Form row gap: 16px.
- Helper panel width: ~220px.

## Key Components and Microcopy

- Title: “Add New Employee.”
- Required fields marked with asterisk.
- Fields: Employee Number, Role, First Name, Last Name, Email.
- Note below form: “A setup email with a one-time password link is sent automatically on create.”
- Role helper panel text:
- Coordinator: “Operational owner. Reviews certificates, manages employees, runs reports.”
- Admin: “IT safety net. Can assign or unassign the Coordinator role. No certificate access.”
- Employee: “Submit-only via email. No web login.”
- Buttons: Cancel, Create Employee.

## System States

- Error banner: “Email already exists.”
- Submit loading: “Saving...”.

## Interactions

- Role selection updates helper text.
- Escape closes modal.

## Accessibility and Keyboard

- Focus trap inside modal.
- Tab order follows form sequence.

## Responsive Behavior

- Helper panel collapses to accordion on mobile.

## Spec Alignment

- Supports controlled role provisioning.

## Branding

- City crest: `CityOfLaredoLogos/CityOfLaredoLogo.png` placed in the header (left).
- Public Health logo: `CityOfLaredoLogos/CityOfLaredoPublicHealthLogo.png` placed near the title or right side.
- If the source logo has a dark background, place it on a white pill with 8px padding to preserve contrast.

## Design System Reference

See `Storyboard/Design-System.md` for shared tokens.

## Nano Banana Meta Prompt

```text
Create a flat, modern employee modal UI mockup (no device). Canvas 1440x900. Light theme with soft blue background (#f5f7fb), deep navy accents (#1a365d), slate text (#4a5568). The underlying roster page is dimmed by a dark translucent overlay. Center a white modal (~640px wide) with rounded corners and soft shadow. Title “Add New Employee.” Two-column form rows: Employee Number + Role, First Name + Last Name, Email. Add a small note below the form: “A setup email with a one-time password link is sent automatically on create.” Include a narrow helper panel on the right listing role descriptions (Coordinator, Admin, Employee). Bottom right buttons: “Cancel” (gray) and “Create Employee” (blue). Official, calm, minimal.
Use these exact logo images: CityOfLaredoLogo.png (crest) and CityOfLaredoPublicHealthLogo.png (Public Health). Place the crest on the far left of the header and the Public Health logo near the title or right side; if a logo has a dark background, place it on a white pill with 8px padding.
```

## Nano Banana Meta Prompt (Dark Theme)

```text
Create a flat, modern employee modal UI mockup (no device). Canvas 1440x900. Dark theme with background #0b1220. Underlying roster page dimmed by a dark translucent overlay. Center a charcoal modal (#111827) with rounded corners and soft shadow. Title “Add New Employee” in white. Two-column form rows: Employee Number + Role, First Name + Last Name, Email. Add a small note: “A setup email with a one-time password link is sent automatically on create.” Include a narrow helper panel listing role descriptions (Coordinator, Admin, Employee). Bottom right buttons: Cancel (gray) and Create Employee (indigo gradient). Text in #f8fafc and #cbd5e1. Minimal, official, calm.
Use these exact logo images: CityOfLaredoLogo.png (crest) and CityOfLaredoPublicHealthLogo.png (Public Health). Place the crest on the far left of the header and the Public Health logo near the title or right side; if a logo has a dark background, place it on a white pill with 8px padding.
```
