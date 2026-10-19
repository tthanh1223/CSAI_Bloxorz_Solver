# Five Bloxorz concepts

The production GUI is unchanged. All five images are 1180 x 800 and share stage_01,
block position (1,1), dimensions 1 x 1 x 2, projection and control functionality.
The board occupies the left 75% region; a compact solver study sits on the right.
English labels are used throughout.

## Render / open

From the repository root:

```powershell
.venv/Scripts/python.exe scripts/preview_concepts.py --all
.venv/Scripts/python.exe scripts/preview_concepts.py --concept 1 --show
```

Replace 1 with 2, 3, 4 or 5. In the viewer use Left/Right to compare and Escape to
close. Without `--show` only PNG files are generated. Outputs are in this folder;
`00_contact_sheet.png` compares all five, and `comparison.json` records the common
scene parameters.

## Rendered effects versus simulation

- Real code-rendered elements: every board face, continuous cuboid, recessed goal,
  glyph, control, texture speckle, wood grain, moss, terrazzo chip and decoration.
- Lighting is art-directed face shading. Soft shadows are projected silhouettes
  blurred in 2D; there is no ray tracing, PBR material or physically simulated sun.
- Forest haze, sun shafts, arches, clouds and stairs are procedural illustrations.
  Decorative geometry is not part of the playable map.
- Preview controls are illustrative, clearly labeled on every image. They do not
  run a solver, change stage, or play the game. Only preview switching works.
- Same geometry/camera is used in all five. Typography, surface treatment, shadow
  color/length and UI treatments intentionally vary.

See `assets/ATTRIBUTION.md` for procedural assets and system font provenance.
Choose a concept before applying it to the main app.
