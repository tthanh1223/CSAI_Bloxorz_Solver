# GUI verification — 20 October 2026

- Default stack remains Pygame CE; no engine migration or solver algorithm edits.
- Forest uses the previous weathered-gold atlas again. Dream/Blueprint keep satin
  champagne and charcoal block contours. Tile seams use one subtle baked layer
  instead of repeated outlines on bevel faces.
- Full suite: 55 passed. Tests cover roll geometry, replay/save/load, solver worker,
  bridge/split, bevel winding, cached UI pixel equivalence and theme switching.
- Actual-window capture script completed 33 screenshots: 11 states × 3 themes.
  Every theme's solution/searching screenshots use the real worker solver.
- Screenshots are consolidated in [one folder](screenshots/README.md). Old concept,
  material comparison and nested screenshot folders were removed. Runtime assets,
  original UML diagrams and benchmark charts were preserved.
- Historical documents/scripts are retained in archive directories, clearly marked
  as superseded; active entry points are documented in the main README.

Latest CPU-only warm Forest sample: mean 11.588 ms, p95 14.850 ms, max 18.566 ms,
27 Python drawing primitives/frame. [Raw JSON](performance.json). This excludes
display latency and is not proof of stable 60 FPS on all laptops. GPU draw calls,
whole-process RAM delta, VRAM and physical input-to-photon were not measured.

See [handoff](GUI_HANDOFF.md) for remaining work and reproduction commands.
