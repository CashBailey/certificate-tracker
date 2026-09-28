# Storyboard Design System (Shared)

## Purpose

Defines the shared visual rules and interaction patterns for all storyboard frames. Every screen references these tokens to keep the experience cohesive and professional.

## Color Tokens

Light Theme:

- Background: #f5f7fb
- Surface: #ffffff
- Primary Ink: #1a365d
- Secondary Ink: #4a5568
- Muted Ink: #6b7280
- Border: #e5e7eb
- Primary Gradient: #1a365d → #2c5282
- Success: #10b981
- Warning: #f59e0b
- Error: #dc2626
- Info: #3b82f6

Dark Theme:

- Background: #0b1220
- Surface: #111827
- Primary Ink: #f8fafc
- Secondary Ink: #cbd5e1
- Border: #1f2937
- Primary Gradient: #1e3a8a → #0f172a
- Success: #34d399
- Warning: #fbbf24
- Error: #f87171
- Info: #60a5fa

## Typography

- Display: 28–32px, bold, used for major page titles
- H1: 24px, semibold
- H2: 20px, semibold
- H3: 16–18px, semibold
- Body: 16px, regular
- Small: 14px, regular
- Caption: 12px, regular

## Spacing Scale

- 4, 8, 12, 16, 24, 32, 48
- Page padding: 24–32
- Card padding: 20–24
- Section gaps: 24–32

## Shape and Depth

- Card radius: 12px
- Input radius: 8px
- Button radius: 6–8px
- Shadow Small: 0 2px 8px rgba(0,0,0,0.08)
- Shadow Medium: 0 4px 12px rgba(0,0,0,0.12)
- Shadow Large: 0 8px 24px rgba(0,0,0,0.18)

## Buttons

- Primary: gradient fill, white text, strong emphasis
- Secondary: light gray fill, dark text
- Outline: transparent with white border (on dark header)
- Danger: solid red
- Disabled: muted gray fill and muted text

## Inputs

- Border: light gray
- Focus ring: 3px blue glow
- Disabled: light gray background

## Icons

- Simple line icons, 1.5px stroke, no heavy shading
- Use icons sparingly to keep the layout calm

## Layout Conventions

- Header height: 64px
- Centered content column: max 1200px
- Tables and grids live inside white cards
- Use breadcrumbs or back links at top-left of content

## Accessibility

- All interactive elements have visible focus rings
- Status is communicated by text and color
- Minimum contrast ratio 4.5:1 for body text
- Provide skip link on authenticated pages

## Responsive Guidance

- At 1024px: grid reduces to 2 columns
- At 768px: cards stack, tables scroll horizontally
- At 480px: header elements wrap, buttons become full width
