# Bloxorz Solver

Project for rebuilding Bloxorz with a playable GUI and search algorithms
(BFS, DFS/IDS, UCS, and A*).
## Setup

Create and activate a project-local virtual environment from the repository root.

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Run

```powershell
python main_test.py
```

The GUI dependency is `pygame-ce`; it provides the `pygame` import used by the
application. This opens the isometric 3D-style desktop GUI. The Stage selector
lists all `levels/stage_*.json` files. Gameplay rules and solvers are reused
from the engine and solver packages.

- Arrows/WASD: roll; Space: switch cube; Z: undo; R: restart.
- Find a solution runs BFS, IDS, UCS or A* in a separate process (30 second limit).
  Select current/start state, or use Hint for the next action from the current state.
- Watch solution opens replay controls below the board: Play/Pause, Next,
  Back, speed and clickable timeline. Exit replay allows manual play from the
  displayed state. Replay my moves is available in Settings.
- Mouse wheel over board: zoom; right-drag: pan; Home: reset camera.
- F5/F9: save/load `data/gui_session.json`, including replay position and view
  preferences. A loaded replay remains paused. One local save slot is provided.
- Save/load, animation, sound, contrast, text size and reset camera are in Settings.
  Audio is optional; it is disabled when no audio device is available.
- Help contains controls and tile symbols. Result details expands solver metrics.
- Escape: close the current menu, or quit the application.

- V (or Settings > View): switch between the **front view** (default: Up moves
  away from you, Down toward you, Left/Right move left/right on screen) and the
  classic isometric view.
- Falling: rolling off the board, onto a closed bridge, or standing upright on a
  fragile tile makes the block topple over the edge and drop (game over); the
  stage then restarts automatically.
- Winning (manual play): the block sinks into the goal hole and the next stage
  loads automatically. Watching a solution replay stays on the current stage.
- Sound effects: put `roll`, `switch`, `split`, `fall`, `win` (.wav/.ogg/.mp3)
  in `assets/sfx/` (see `assets/sfx/README.md`). Missing files fall back to
  tones generated in `src/gui/sfx.py`. Settings > Sound turns them on/off.

The renderer uses Pygame polygons, not a free-rotation 3D engine. Falls are
detected by `BloxorzProblem.fall_result()` / `GameSession.fall()`; solvers still
only use `get_successors()`, so falling never appears in a solution. IDS is the
existing implementation named `DFS` internally.

## Editing the GUI

- `src/gui/renderer3d.py`: geometry, colors, projection, tile symbols, camera.
- `src/gui/theme.py`: shared colors, spacing, font family and three type sizes.
- `src/gui/ui.py`: reusable buttons with hover/pressed/disabled/selected states.
- `src/gui/presentation.py`: state-dependent layout, solver panel and menus.
- `src/gui/app.py`: input and game/solver/replay integration.
- `src/gui/animation.py`: animation duration and progress.
- `src/gui/replay.py`: playback cursor and state transitions.
- `src/gui/solver_gateway.py`: background processes, timeout and cancellation.
- `src/gui/contracts.py`: shared interfaces; coordinate changes across modules.

Run `python main_test.py` after editing. All current live-window screenshots are
in `docs/screenshots/`; regenerate all three themes and their interactive states
with `python scripts/capture_themes.py` (opens a desktop window and runs the real solver).
Run `python -m pytest -q -p no:cacheprovider` for engine,
GUI integration, geometry, replay, save/load and real solver-worker checks.

## Project layout

- `levels/`: JSON stage definitions shared by the game and solvers.
- `data/`: generated benchmark CSV files and comparison charts.
- `src/engine/`: state, stage loading, transitions, and tile mechanics.
- `src/solvers/`: search algorithms, profiling, and benchmark runner.
- `src/gui/`: Pygame application.
- `tests/`: automated checks for engine, stages, solvers, and integration.

## Themes and screenshots

Dream City is the default. Click the theme name beside the logo to cycle themes,
or launch one directly:

```
python main_test.py --theme blueprint
python main_test.py --theme forest
```

Windows shortcuts: `run_blueprint.cmd`, `run_forest.cmd`. These use the optimized
Pygame renderer and require no extra dependencies. Dream/Blueprint have champagne
brass blocks with charcoal contours; Forest uses a weathered gold texture. Static
board/material/shadow layers and UI are cached. No gameplay or solver algorithm is
reimplemented by the themes.

The older experimental OpenGL scene remains optional: install
`requirements-forest.txt`, then run `python main_test.py --forest`. It is separate
from `--theme forest` and is not the recommended renderer.

See [GUI handoff](docs/GUI_HANDOFF.md), [verification report](docs/GUI_REPORT.md),
and [screenshot index](docs/screenshots/README.md). Sound is currently an optional
movement beep; dedicated SFX/music and saved theme preferences remain unfinished.
