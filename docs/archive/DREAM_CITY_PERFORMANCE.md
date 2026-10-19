# Dream City: performance pass

## Pipeline and implementation

The default renderer is still Pygame CE 2.5.8, CPU projected isometric geometry,
with a static image background. The engine and solver algorithms are unchanged.
There is no new rendering engine or default dependency.

Before: every frame projected all tiles, rebuilt the island shadow, allocated a
full-viewport contact shadow, made a shadow mask for each tile, sorted all faces,
and rendered every UI label/gradient again. Material stamps alone were cached.

After:

- Stage, visible bridge mask, camera, zoom, pan and contrast invalidate one baked
  board layer and one combined tile-top shadow mask. Ordinary movement does not.
- The board, island shadow, goal rim/walls and switch markings are baked together.
  Pygame Surface compositing provides batching; GPU instancing is not available in
  this software pipeline. GPU draw-call/state-change counters are not available.
- Block and tile use a shared cached 26-face bevel topology. Moving vertices are
  transformed from a cached template. Geometry does not influence engine rules.
- Tile material stamps are bounded; moving block grain uses a reusable quantized
  palette of 64 × 64 textures rather than a new texture for every roll angle.
- Only block geometry and the small projected contact-shadow footprint are updated
  during a roll. That shadow is clipped once to the combined tile-top mask, with
  the goal opening excluded. Static tile faces are never projected in that path.
- UI composition is cached independently from block motion. Unchanged idle frames
  skip drawing and display flip in the app loop. Modal content, hover/pressed states,
  solver results, settings, resize and replay invalidate the UI correctly. The
  busy indicator redraws at 10 Hz rather than recreating a full scene at 60 Hz.
- A one-action keyboard buffer preserves a direction pressed during a manual roll.
  The engine validates it after the roll; restart/stage changes/menu opening clear
  it. Replay does not receive buffered manual movement. Solver work still uses the
  existing spawned process; gameplay remains intentionally locked during search,
  while cancel, menus, input handling and window events remain responsive.

No particles, ray tracing, volumetrics, SSR or heavy post-processing were added.
No three-level quality selector was added: the common visual path already fits the
measured local budget; introducing three material variants was not necessary.

## Measurements

1180 × 800, Windows, Python 3.13.11, Pygame CE 2.5.8. Each scenario warms 12 frames,
then measures 90 frames. Animation traverses 60 roll poses; times include Python
primitive instrumentation. These are short local measurements, not cross-device
guarantees or a sustained thermal/stress test.

| Same dummy-SDL CPU scenario | Before | After |
|---|---:|---:|
| Animated GUI mean | 49.967 ms | 8.887 ms |
| Animated GUI p95 | 64.880 ms | 9.871 ms |
| Python drawing primitives/frame | 396.6 | 24.8 |
| Idle GUI mean | 51.462 ms | 0.007 ms (draw skipped) |

Final **live-window render + display flip** measurement: mean **12.228 ms**, p95
**17.123 ms**, maximum **19.594 ms**. Its uncapped processing throughput was 81.8
frames/s; the interactive app still targets 60. This supports the local 60 FPS
target on average, but does not prove every frame meets 16.67 ms. A prior live run
measured 16.918 ms mean and 23.459 ms p95, showing machine-load variation.

Synthetic accepted key handling (engine action + animation scheduling) measured
0.331 ms mean / 0.663 ms maximum in the final live run. Mouse event dispatch was
0.009 ms mean. Physical keyboard latency, OS queue delay and input-to-photon latency
were not measured. The original run measured only synthetic mouse dispatch, so
there is no before/after comparison for accepted move scheduling.

The measured renderer retained approximately 8.1 MiB in board/frame/mask/material/
block-texture caches. These caches replace repeated allocations and are bounded;
the UI also retains one screen snapshot and one board Surface. Whole-process RAM
delta and VRAM were not measured, so no claim is made about their improvement.

Raw data: `performance_before.json`, `performance_after.json`,
`performance_live_after.json`. The baseline is CPU-only; there is no live-window
baseline, and CPU-only timing must not be compared directly to live timing.

Reproduce:

```
python scripts/benchmark_gui.py --output docs/performance_after.json
python scripts/benchmark_gui.py --live --output docs/performance_live_after.json
python -m pytest -q -p no:cacheprovider
python scripts/capture_gui.py
```

Screenshots: `screenshots/01_play.png` through `06_compact.png`; these capture the
real window, real solver result, replay, settings and compact layout.
The complete suite passed 50 tests, including animation cache reuse, full-versus-
cached UI pixel equivalence, bridge-mask invalidation, split rendering and buffered
input reset behavior.

## Remaining limits

Changing camera/zoom or bridges triggers a cold bake and can cost more than a warm
animation frame, especially on large maps. Static-layer caching does not provide
perspective-correct textures or physically based lighting. The warm timings above
do not cover continuous zoom/drag, cold loading, every map, concurrent solver load,
or the separate optional OpenGL Forest renderer.

Pygame APIs used: [Surface compositing](https://www.pygame.org/docs/ref/surface.html)
and [textured polygons](https://pyga.me/docs/ref/gfxdraw.html).
