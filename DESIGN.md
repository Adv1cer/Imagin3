---
name: Computational Logic
colors:
  surface: '#031427'
  surface-dim: '#031427'
  surface-bright: '#2a3a4f'
  surface-container-lowest: '#000f21'
  surface-container-low: '#0b1c30'
  surface-container: '#102034'
  surface-container-high: '#1b2b3f'
  surface-container-highest: '#26364a'
  on-surface: '#d3e4fe'
  on-surface-variant: '#c6c6cd'
  inverse-surface: '#d3e4fe'
  inverse-on-surface: '#213145'
  outline: '#909097'
  outline-variant: '#45464d'
  surface-tint: '#bec6e0'
  primary: '#bec6e0'
  on-primary: '#283044'
  primary-container: '#0f172a'
  on-primary-container: '#798098'
  inverse-primary: '#565e74'
  secondary: '#5de6ff'
  on-secondary: '#00363e'
  secondary-container: '#00cbe6'
  on-secondary-container: '#00515d'
  tertiary: '#d0bcff'
  on-tertiary: '#3c0091'
  tertiary-container: '#1e0052'
  on-tertiary-container: '#9162fc'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#dae2fd'
  primary-fixed-dim: '#bec6e0'
  on-primary-fixed: '#131b2e'
  on-primary-fixed-variant: '#3f465c'
  secondary-fixed: '#a2eeff'
  secondary-fixed-dim: '#2fd9f4'
  on-secondary-fixed: '#001f25'
  on-secondary-fixed-variant: '#004e5a'
  tertiary-fixed: '#e9ddff'
  tertiary-fixed-dim: '#d0bcff'
  on-tertiary-fixed: '#23005c'
  on-tertiary-fixed-variant: '#5516be'
  background: '#031427'
  on-background: '#d3e4fe'
  surface-variant: '#26364a'
typography:
  headline-xl:
    fontFamily: Inter
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 48px
    letterSpacing: -0.02em
  headline-xl-mobile:
    fontFamily: Inter
    fontSize: 30px
    fontWeight: '700'
    lineHeight: 36px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-mono:
    fontFamily: Geist
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.05em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  base: 4px
  gutter: 16px
  margin-desktop: 32px
  margin-mobile: 16px
  sidebar-width: 280px
  toolbar-width: 64px
---

## Brand & Style

The design system is engineered for "Computational Logic"—a design philosophy that balances the immovable reliability of enterprise infrastructure with the fluid potential of generative AI. The brand personality is authoritative, precise, and high-performance. It is designed to feel like a high-end workstation: professional, distraction-free, and remarkably robust.

The style is **Corporate / Modern** with a **Minimalist** edge. It utilizes a structured grid, high-fidelity iconography, and subtle kinetic feedback. The interface avoids unnecessary decorative elements, favoring clarity and functional density to support complex workflows in on-premise AI environments.

## Colors

The palette is anchored in a "Compute Plane" philosophy. The background and primary surfaces use Deep Navy and Slate to signify the stability of the local hardware. 

- **Primary (Deep Navy/Slate):** Used for structural elements like sidebars, headers, and modal backdrops. It provides a grounded, low-fatigue environment for long design sessions.
- **Accent (Electric Cyan/Purple):** These "Innovation" colors are used sparingly for active states, primary actions, and AI-driven process indicators. 
- **Status Tones:** Standardized Success, Warning, and Error colors are saturated to ensure high visibility against the dark UI, essential for QA reports and hardware monitoring.

## Typography

This design system utilizes **Inter** for its exceptional legibility in dense data environments and **Geist** for technical labels and monospaced data readouts.

- **Headlines:** Bold and tight, conveying a sense of impact and hierarchy.
- **Body:** Sized for long-form reading of logs and prompt descriptions.
- **Labels:** We use a monospaced font for status labels, coordinates, and technical metadata to evoke a "developer-tool" precision.
- **Scaling:** Headlines shift significantly on mobile to maintain viewport efficiency, while body text remains stable to preserve readability.

## Layout & Spacing

The layout follows a **Fixed Grid** model for the core canvas and a **Fluid Grid** for dashboard views. 

- **The Canvas:** Centered with a fixed-width toolbar (64px) docked to the left or right. 
- **The Dashboard:** A 12-column grid with 24px gutters on desktop, collapsing to a single column on mobile.
- **The Sidebar:** A consistent 280px width to accommodate complex navigation trees and property inspectors.

Rhythm is maintained through a 4px baseline. All padding and margins must be multiples of 4 (e.g., 8, 16, 24, 32). Large negative spaces are used to separate "Management" areas (Sidebars) from "Creation" areas (Canvas).

## Elevation & Depth

To maintain a professional, "on-premise" feel, we use **Tonal Layers** rather than heavy shadows.

- **Level 0 (Background):** The darkest slate color, representing the core system.
- **Level 1 (Containers/Cards):** A slightly lighter shade of navy with a subtle 1px border (#1E293B) to define boundaries.
- **Level 2 (Popovers/Modals):** Floating elements use a subtle ambient shadow (0px 8px 24px rgba(0,0,0,0.5)) and a brighter border to indicate they are in the foreground.
- **Interaction:** Active inputs and focused states utilize a 2px "Electric Cyan" outer glow (2px blur) to simulate the glow of high-performance hardware indicators.

## Shapes

The design system employs **Soft** (Level 1) roundedness. 

- **Standard Components:** 4px (0.25rem) corner radius for buttons and inputs, providing a modern look that still feels disciplined and architectural.
- **Cards & Large Containers:** 8px (0.5rem) to slightly soften the enterprise density.
- **Icons:** Squircle or sharp geometric shapes are preferred over fully circular containers to maintain the "precision instrument" aesthetic.

## Components

- **Buttons:** Primary buttons use a solid Electric Cyan with dark text. Secondary buttons are ghost-style with slate borders.
- **Progress Steppers:** Use a thin 2px line. Completed steps glow in Cyan; pending steps are muted Slate.
- **Sidebar Navigation:** High-density list items. Active states are indicated by a vertical Cyan bar on the left edge and a subtle background tint.
- **Canvas Toolbars:** Compact, icon-only buttons with tooltips. Grouped by function with subtle dividers.
- **Card-based Galleries:** Images are displayed in a "Masonry" or "Square Grid." Metadata (Prompt, Seed, Sampler) appears on hover using a glassmorphic overlay.
- **Input Fields:** Darker than the container background. Label is placed above the input in the `label-mono` font style.
- **QA Chips:** Small, pill-shaped badges with high-contrast status colors (e.g., "Pass" in Success Green) to highlight model performance metrics.