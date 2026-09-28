# Frame 01 - Login (Deeply Enhanced)

## Purpose

The login screen is the public entry point and must immediately feel official, calm, and secure. It should be frictionless for the Coordinator while signaling that access is monitored and audited.

## Visual Narrative

Imagine a quiet civic lobby at dawn. The background is a soft diagonal blue gradient, deeper in the upper left and fading into pale mist near the bottom. In the center sits a crisp white card with rounded corners, like a clean letterhead on a desk. The city name is bold and confident. The fields are evenly spaced, and a single decisive blue button anchors the page.

## Composition and Measurements

- Canvas: 1440x900 (16:10) or 1440x900 equivalent.
- Header area: none, full‑screen card centered.
- Card width: 420px, height: ~520px.
- Card padding: 32px.
- Card radius: 12px, shadow: soft, cool.

## Typography and Microcopy

- Title: “City of Laredo” at 28px, semibold, deep navy.
- Subtitle: “Certificate Management System” at 14px, medium, slate.
- Labels: 13px, medium.
- Inputs: 44px tall, 14–16px text.
- Button text: 15–16px, semibold.
- Placeholder for email: "`name@ci.laredo.tx.us`".
- Password hint text: “Minimum 8 characters.”

## Key Components

- Email field with label and placeholder.
- Password field with label and visibility toggle icon.
- Primary “Sign In” button in blue gradient.
- Secondary links: “Forgot password” and “Need help?”.
- Trust note below button: “Access is monitored and audited.”

## System States

- Error banner: “Email or password incorrect. Try again or contact support.”
- Submitting: button text becomes “Signing in...” and fields disable.
- Disabled inputs: light gray background with muted text.

## Accessibility and Keyboard

- Visible focus ring on all inputs and links.
- Logical tab order: Email → Password → Sign In → Forgot → Help.
- Error banner announced on focus for screen readers.

## Responsive Behavior

- At 768px: card width becomes 90% with 16px margins.
- Links stack vertically under the button.

## Spec Alignment

- Enforces authenticated UI access.
- Preserves a quick, secure entry flow for the Coordinator.

## Branding

- City crest: `CityOfLaredoLogos/CityOfLaredoLogo.png` in the card header (left of the title).
- Public Health logo: `CityOfLaredoLogos/CityOfLaredoPublicHealthLogo.png` beneath the subtitle or aligned right.
- If the source logo has a dark background, place it on a white pill with 8px padding.

## Design System Reference

See `Storyboard/Design-System.md` for shared tokens.

## Nano Banana Meta Prompt

```text
Design a clean, modern civic login screen as a flat UI mockup (no device frame, no 3D). Canvas 1440x900. Light theme. Background: soft diagonal gradient from deep navy (#1a365d) in the upper left to cooler blue (#2c5282) fading into pale mist (#f5f7fb). Center a white card (420px wide, ~520px tall), 12px rounded corners, soft shadow. Inside card: title “City of Laredo” (28px, semibold, deep navy) and subtitle “Certificate Management System” (14px, slate #4a5568). Two labeled fields: Email and Password, inputs 44px tall with light gray borders and blue focus glow. Email placeholder "name@ci.laredo.tx.us". Add a small eye icon in the password field. Primary full‑width “Sign In” button in blue gradient. Below it, small links “Forgot password” and “Need help?” in blue. Add a tiny trust note: “Access is monitored and audited.” Include an error state banner above fields: pale rose background (#fef2f2) with red text (#dc2626) reading “Email or password incorrect. Try again or contact support.” Minimal, official, calm, no illustrations.
Use these exact logo images: CityOfLaredoLogo.png (crest) and CityOfLaredoPublicHealthLogo.png (Public Health). On the login screen, place the crest inside the card header to the left of the title and the Public Health logo beneath the subtitle or right-aligned; if a logo has a dark background, place it on a white pill with 8px padding.
```

## Nano Banana Meta Prompt (Dark Theme)

```text
Design a clean, modern civic login screen as a flat UI mockup (no device frame). Canvas 1440x900. Dark theme. Background: deep midnight (#0b1220) with a subtle diagonal gradient into near-black (#0f172a). Center a charcoal card (#111827), 12px rounded corners, soft shadow. Title “City of Laredo” in soft white (#f8fafc) and subtitle “Certificate Management System” in cool gray (#cbd5e1). Two labeled fields: Email and Password, inputs 44px tall with borders #1f2937 and blue focus glow #60a5fa. Email placeholder "name@ci.laredo.tx.us". Add a small eye icon in the password field. Primary full-width “Sign In” button in muted indigo gradient (#1e3a8a to #0f172a) with white text. Links below: “Forgot password” and “Need help?” in blue (#60a5fa). Add a small trust note: “Access is monitored and audited.” Include an error banner above fields: dark background (#1f2937) with red text (#f87171) reading “Email or password incorrect. Try again or contact support.” Minimal, official, calm.
Use these exact logo images: CityOfLaredoLogo.png (crest) and CityOfLaredoPublicHealthLogo.png (Public Health). On the login screen, place the crest inside the card header to the left of the title and the Public Health logo beneath the subtitle or right-aligned; if a logo has a dark background, place it on a white pill with 8px padding.
```
