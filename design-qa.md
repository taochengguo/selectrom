# Design QA

## Comparison target

- Source visual truth: `C:\Users\Eternal\.codex\skills\artifact-template-ui\assets\reference.png`
- Retained QA copy: `docs/verification/reference.png`
- Mobile implementation: `docs/verification/mobile-390x693.png`
- Standard mobile runtime capture: `docs/verification/mobile-390x844.png`
- Draw result state: `docs/verification/mobile-draw-result-390x844.png`
- Desktop management implementation: `docs/verification/management-1440x900.png`
- Full-view comparison: `docs/verification/mobile-reference-comparison.jpg`
- Focused hero and summary comparison: `docs/verification/mobile-focused-comparison.jpg`

## Viewport and normalization

- Source pixels: 941 x 1672.
- Source normalization: Lanczos downsample to 390 x 693, preserving the source aspect ratio.
- Comparison implementation: 390 x 693 CSS pixels, deviceScaleFactor 1.
- Standard mobile verification: 390 x 844 CSS pixels, deviceScaleFactor 1.
- Desktop verification: 1440 x 900 CSS pixels, deviceScaleFactor 1.
- State: authenticated assigned sampler on the random-sampling dashboard; desktop is an authenticated administrator dashboard. The draw capture shows the same task after its first result was locked and the task completed.

## Full-view evidence

The second full-view comparison shows the same blue-white palette, centered mobile title, right-weighted clipboard illustration, rounded cards, four-column task summary, prominent blue action button, recent task section, and fixed three-item bottom navigation. The implementation uses live demo data, so counts and recent-task copy intentionally differ from the static reference.

The 390 x 844 capture has no horizontal overflow: document, body, and viewport widths are all 390 pixels. The fixed bottom navigation occupies x=0, y=774, width=390, height=70 and remains entirely visible. The 1440 x 900 management capture also has matching document, body, and viewport widths of 1440 pixels.

## Focused region evidence

The focused comparison covers the hero, daily-task summary, and primary action at readable scale. It verifies the generated raster illustration is loaded rather than approximated with CSS art, the hero copy remains legible, the summary has four distinct semantic color blocks, and the main action keeps the reference's blue gradient emphasis.

## Required fidelity surfaces

- Fonts and typography: system Chinese sans-serif fallbacks are visually close to the reference; title, section heading, supporting copy, numeric hierarchy, weights, wrapping, and line height are readable at both tested mobile sizes. Small muted text and inactive navigation meet the project's 4.5:1 contrast contract.
- Spacing and layout rhythm: the mobile header, compact hero, four-column summary, action button, recent record, card radii, and shadows now follow the reference's information density. Desktop cards and tables align to a stable sidebar grid with no viewport overflow.
- Colors and tokens: blue-white surfaces, primary gradient, muted text, pastel status blocks, borders, shadows, and semantic completed state consistently reuse shared tokens.
- Image quality and asset fidelity: `static/img/sampling-hero.png` is a sharp 1833 x 858 raster asset in the same blue-white 3D clipboard/checklist art direction as the source. It loads successfully with HTTP 200.
- Copy and content: the core labels match the approved product flow: 随机抽样、今日抽样任务、开始抽样、最近抽样记录、任务提醒、个人中心. Counts, task names, and material numbers are live demo data rather than copied reference values.
- Icons: the custom hero illustration is a real raster asset. Bottom navigation remains text-first because the local project has no installed icon system; labels and active state remain unambiguous.
- Accessibility: landmarks and navigation labels are present, touch targets remain at least 44 pixels, keyboard-visible links/buttons are native controls, text contrast contracts pass, and no persistent control is clipped.
- Interactions: administrator login, one-time random personnel assignment, sampler login, initial draw, three persisted results, refresh lock verification, completion, and task audit event visibility were exercised in Chrome. Browser console and page errors: none.

## Findings

- No actionable P0, P1, or P2 findings remain.
- P3: the mobile hero illustration is cropped slightly tighter than the static reference at 390 pixels, but the subject, copy, and card hierarchy remain fully legible.
- P3: the reference includes decorative bottom-navigation icons and a quick-entry module; the approved demo keeps text-first navigation and the required core routes without adding an unrequested icon dependency or non-functional shortcuts.

## Comparison history

1. Initial browser pass: P2 muted text and inactive navigation contrast were below WCAG AA. Fix: changed the shared muted token to `#60708b` and reused it for inactive navigation. Post-fix evidence: automated contrast contract passes above 4.5:1.
2. First rendered comparison: P2 hero illustration was visually absent. Root cause: the higher-specificity generic section `background` shorthand reset hero background position and size. Fix: raised the hero selector specificity and added a regression contract. Post-fix evidence: Chrome loaded the raster asset with HTTP 200 and the illustration became visible.
3. First rendered comparison: P2 mobile density drifted from the source because 390 pixels still used a two-column summary and an oversized hero. Fix: introduced the four-column common-phone breakpoint, compacted the dashboard hero and summary card, preserved 44+ pixel interaction targets, and added density contracts. Post-fix evidence: the second 390 x 693 comparison shows hero, summary, primary action, and recent record in the source's above-the-fold rhythm.
4. Browser console pass: P2 login-page resource 404. Root cause: Chrome requested `/favicon.ico`. Fix: declared the existing raster hero asset as the favicon and added a root favicon redirect plus contracts. Post-fix evidence: final end-to-end run reports an empty console error list.

## Implementation checklist

- [x] Source and implementation opened in one normalized comparison.
- [x] Full-view and focused-region evidence inspected.
- [x] P0/P1/P2 findings fixed and re-captured.
- [x] Mobile and desktop overflow checked.
- [x] Core sampling interaction and locked result persistence verified.
- [x] Console and page errors checked.

final result: passed
