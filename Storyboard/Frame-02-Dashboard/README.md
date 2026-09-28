# Frame 02 - Dashboard (Deeply Enhanced)

## Purpose

This is the authenticated home screen and operational hub. It confirms identity and role, surfaces urgent work, and provides immediate access to primary workflows.

## Visual Narrative

A calm civic banner spans the top. The left side shows a subtle city seal and system title, while the right shows the user identity cluster. Below, the dashboard feels like an organized desk: a welcome card, a row of quick stats, a “Today’s Tasks” list, and a grid of navigation cards arranged with generous spacing.

## Composition and Measurements

- Canvas: 1440x900.
- Header: 64px tall gradient bar.
- Content column: max width 1200px, centered.
- Card radius: 12px, padding: 24px.

## Key Components and Microcopy

- Welcome card: “Welcome, Carla” with email, role, employee number.
- Quick Stats: 3 cards showing “Pending Reviews: 6”, “Overdue Requirements: 3”, “Expiring Certificates: 5”.
- Today’s Tasks list (5 items):
- “Review Extraction #551 — due today.”
- “Overdue: CPR Renewal — Ana Ruiz.”
- “Expiring in 30 days: HazMat — Jorge Silva.”
- “Quarantined email: unknown sender.”
- “Upload exception: paper copy received.”
- Navigation cards with subtitles:
- My Requirements — “View assigned certifications.”
- Configuration — “Manage certificate types, templates, and alerts.”
- Review Queue — “Review pending extractions.”
- Compliance Reports — “View department status.”
- Templates — “Review extraction templates.”
- Employees — “Manage roles and access.”

## System States

- Banner slot above welcome card for system alerts.
- Skeleton loading placeholders for cards.
- Empty tasks message: “No urgent tasks today.”

## Interactions

- Quick stats are clickable and link to filtered views.
- Cards lift slightly on hover.

## Accessibility and Keyboard

- Skip link to main content.
- High contrast header text.
- Focus rings on cards and buttons.

## Responsive Behavior

- At 1024px: navigation grid becomes 2 columns.
- At 768px: stats and tasks stack vertically.
- At 480px: header wraps; Sign Out becomes icon + label.

## Spec Alignment

- Emphasizes Coordinator responsibilities and rapid access to reporting and review.

## Branding

- City crest: `CityOfLaredoLogos/CityOfLaredoLogo.png` placed in the header (left).
- Public Health logo: `CityOfLaredoLogos/CityOfLaredoPublicHealthLogo.png` placed near the title or right side.
- If the source logo has a dark background, place it on a white pill with 8px padding to preserve contrast.

## Design System Reference

See `Storyboard/Design-System.md` for shared tokens.

## Nano Banana Meta Prompt

```text
Create a flat, modern dashboard UI mockup (no device frame). Canvas 1440x900. Light theme with soft blue background (#f5f7fb) and deep navy accents (#1a365d). Header bar (64px tall) with blue gradient (#1a365d to #2c5282). Left: small monochrome city seal and title “City of Laredo Certificate Management” in white. Right: circular avatar “CA,” name “Carla Morgan,” role pill “Coordinator,” outline Sign Out button. Main content centered (max width 1200px). First card: “Welcome, Carla” with email, role, employee number. Row of three stat cards: Pending Reviews 6, Overdue Requirements 3, Expiring Certificates 5. “Today’s Tasks” card with 5 items and short due notes. Below: grid of six white navigation cards with short subtitles for My Requirements, Configuration, Review Queue, Compliance Reports, Templates, Employees. Include a slim system alert banner slot at top of content. Minimal, official, calm.
Use these exact logo images: CityOfLaredoLogo.png (crest) and CityOfLaredoPublicHealthLogo.png (Public Health). Place the crest on the far left of the header and the Public Health logo near the title or right side; if a logo has a dark background, place it on a white pill with 8px padding.
```

## Nano Banana Meta Prompt (Dark Theme)

```text
Create a flat, modern dashboard UI mockup (no device). Canvas 1440x900. Dark theme with deep midnight background (#0b1220) and charcoal cards (#111827). Header bar with indigo gradient (#1e3a8a to #0f172a). Left: monochrome city seal and title “City of Laredo Certificate Management” in white. Right: avatar “CA,” name “Carla Morgan,” role pill “Coordinator,” outline Sign Out button. Main content centered. Welcome card in charcoal with white text and cool gray details. Row of three stat cards: Pending Reviews 6, Overdue Requirements 3, Expiring Certificates 5. “Today’s Tasks” card with 5 items. Grid of six navigation cards with short subtitles. Include a slim system alert banner slot at the top of content. Text in #f8fafc and #cbd5e1. Minimal, official, calm.
Use these exact logo images: CityOfLaredoLogo.png (crest) and CityOfLaredoPublicHealthLogo.png (Public Health). Place the crest on the far left of the header and the Public Health logo near the title or right side; if a logo has a dark background, place it on a white pill with 8px padding.
```
