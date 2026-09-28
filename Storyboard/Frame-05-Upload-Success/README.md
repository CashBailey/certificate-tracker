# Frame 05 - Upload Success (Deeply Enhanced)

## Purpose

Confirms receipt and shows pipeline status with clear next steps. It should read like a stamped receipt.

## Visual Narrative

A green checkmark badge sits above the success title. A pale gray detail box lists IDs. Below, a three‑step progress strip shows the document moving through the system. A short line indicates that processing may take a few minutes. Two buttons provide the next action.

## Composition and Measurements

- Canvas: 1440x900.
- Success card: 500px wide, vertically centered.

## Key Components and Microcopy

- Title: “Upload Successful!”
- Body: “Your document has been received and is being processed.”
- Details: “Document ID: 1024” and “Extraction ID: 551.”
- Progress strip: Received (green), Extracting (green), Ready for Review (gray).
- Note: “Processing may take a few minutes.”
- Buttons: “Upload Another” (secondary), “View Extraction” (primary).
- Optional line: “Email confirmation sent to `carla.morgan@ci.laredo.tx.us`.”

## System States

- If extraction fails, a yellow warning banner appears with “We couldn’t extract all fields. Review required.”

## Interactions

- Upload Another returns to form.
- View Extraction navigates to review detail.

## Accessibility and Keyboard

- Status conveyed in text + icon.
- Buttons are keyboard accessible.

## Responsive Behavior

- Buttons stack vertically on mobile.

## Spec Alignment

- Reinforces the human review gate with a direct path to review.

## Branding

- City crest: `CityOfLaredoLogos/CityOfLaredoLogo.png` placed in the header (left).
- Public Health logo: `CityOfLaredoLogos/CityOfLaredoPublicHealthLogo.png` placed near the title or right side.
- If the source logo has a dark background, place it on a white pill with 8px padding to preserve contrast.

## Design System Reference

See `Storyboard/Design-System.md` for shared tokens.

## Nano Banana Meta Prompt

```text
Create a flat, modern upload success UI mockup (no device). Canvas 1440x900. Light theme with soft blue background (#f5f7fb), deep navy accents (#1a365d), slate text (#4a5568). Header bar with blue gradient (#1a365d to #2c5282), left city seal, title “Upload Certificate,” right identity cluster. Centered white success card (~500px wide). Green circular badge with checkmark. Title “Upload Successful!” and text “Your document has been received and is being processed.” Pale gray details box listing “Document ID: 1024” and “Extraction ID: 551.” Below, a three‑step progress strip: Received (green), Extracting (green), Ready for Review (gray). Add a small note “Processing may take a few minutes.” Buttons at bottom: “Upload Another” (gray) and “View Extraction” (blue gradient). Add a small line: “Email confirmation sent to carla.morgan@ci.laredo.tx.us.” Clean, official, minimal.
Use these exact logo images: CityOfLaredoLogo.png (crest) and CityOfLaredoPublicHealthLogo.png (Public Health). Place the crest on the far left of the header and the Public Health logo near the title or right side; if a logo has a dark background, place it on a white pill with 8px padding.
```

## Nano Banana Meta Prompt (Dark Theme)

```text
Create a flat, modern upload success UI mockup (no device). Canvas 1440x900. Dark theme with background #0b1220 and charcoal card #111827. Header bar with indigo gradient (#1e3a8a to #0f172a), left city seal, title “Upload Certificate,” right identity cluster. Centered success card (~500px wide). Green circular badge with checkmark (#34d399). Title “Upload Successful!” in white. Body text in cool gray. Pale dark details box (#1f2937) listing “Document ID: 1024” and “Extraction ID: 551.” Progress strip with three steps: Received (green), Extracting (green), Ready for Review (gray). Note: “Processing may take a few minutes.” Buttons at bottom: “Upload Another” (gray) and “View Extraction” (indigo gradient). Minimal, official, calm.
Use these exact logo images: CityOfLaredoLogo.png (crest) and CityOfLaredoPublicHealthLogo.png (Public Health). Place the crest on the far left of the header and the Public Health logo near the title or right side; if a logo has a dark background, place it on a white pill with 8px padding.
```
