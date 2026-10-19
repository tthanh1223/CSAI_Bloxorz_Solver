# Dream City / default Pygame GUI

Run `python main_test.py`. No new dependencies are required for the default renderer.
The optional Forest OpenGL variant remains available through `--forest`.

The supplied peach architectural reference guided the composition: left playable
isometric board, tall ivory solver panel on the right, mauve typography, warm orange
block and action button. The environment is a locally bundled AI-generated image
(`assets/dream_city_background.png`), generated for this project with OpenAI imagegen.
It contains no board, block or controls. No remote assets are loaded at runtime.

Tiles and the moving block remain projected geometry from the engine's GameState
and MotionFrame. Their face materials use deterministic terrazzo flakes and subtle
orange grain. The renderer clips a soft projected block shadow to the tile tops;
the island casts a separate soft background shadow. Material stamps and scaled
backgrounds are cached. The goal has visible inset wall shading.

Reference differences addressed during screenshot review: background/header
readability, cream panel composition, fine versus coarse terrazzo flakes, overly
brown block sides, and the flat-looking goal. Remaining differences: the background
is a new environment rather than the exact reference scene, and lighting is painted
face shading rather than full 3D GI. Tile and player bevels now use a cached low-poly
26-face template; block grain uses a reusable quantized texture palette.

Verification: see `DREAM_CITY_PERFORMANCE.md`; `scripts/capture_gui.py` exercises a real
solver, solution playback, settings, and compact 960 × 720 layout. Main actual-window
capture is `docs/screenshots/01_play.png` (1180 × 800).
