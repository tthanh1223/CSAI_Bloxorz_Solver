# Optional Forest Ruins preview

The original renderer remains the default: `python main_test.py`.
The legacy experimental OpenGL Forest is opt-in: `python main_test.py --forest`.
The newer cached Pygame Forest is `python main_test.py --theme forest`, or
double-click `run_forest.cmd`; it does not require ModernGL.

Install in the same Python environment used to launch the game:

```
python -m pip install -r requirements-forest.txt
```

Requires OpenGL 3.3 and a working graphics driver. No external assets or downloads
are used by the renderer. All stone grain, moss, ruins and vegetation are generated
locally. This is a stylized prototype, not a reproduction of a supplied concept.

The board and player are depth-tested 3D geometry driven by the existing game state
and roll animation. The scene uses a directional shadow map, procedural stone/moss
shading, distance fog, ruined colonnades and tree silhouettes. Controls, replay,
solver, saves, stage selection, pan and zoom use the existing application.

For compatibility, an offscreen ModernGL framebuffer is copied into the Pygame UI.
Unchanged frames are cached. GPU readback during animation adds overhead; a future
fully GPU-composited UI would avoid that cost. The scene has no volumetric light,
PBR textures, organic tree models or bevelled player mesh yet.
The 3D viewport renders at 65% resolution and is upscaled; UI stays full resolution.

Capture and render smoke check: `python scripts/capture_forest.py`.
Output: `docs/screenshots/forest_opengl.png` at 1180 × 800.
This also exercises roll poses, resized targets, zoom, pan and every stage.

## Local verification

- AMD Radeon(TM) Graphics successfully created the OpenGL context.
- All 33 stages rendered with `GL_NO_ERROR`.
- Existing suite: 46 passed.
- Final animation smoke benchmark: 320.1 ms/frame for 20 frames (about 3 FPS).
  This prototype is currently too slow for smooth animation on the tested setup;
  cached stationary frames do not incur that render cost. Do not treat this preview
  as a production replacement for the default renderer.
