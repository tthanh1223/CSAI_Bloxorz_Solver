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
python main.py
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
- Escape: close the current menu or the solver panel; otherwise open/close the main menu.
  Tab: show/hide the solver panel.

- V (or Settings > View): switch between the **original view** (default: the
  Flash game's front-left perspective camera; Up moves away from you, Left/Right
  move left/right on screen) and the classic isometric view.
- Falling: rolling off the board, onto a closed bridge, or standing upright on a
  fragile tile makes the block drop (game over); a fragile tile vanishes under
  it. The stage then restarts automatically.
- Winning (manual play): the block sinks into the goal hole, then a dialog
  offers Replay my moves (P) or Next stage (Enter). Watching a solution replay
  stays on the current stage.
- Sound effects: put `roll`, `switch`, `split`, `fall`, `win` (.wav/.ogg/.mp3)
  in `assets/sfx/` (see `assets/sfx/README.md`). Missing files fall back to
  tones generated in `src/gui/sfx.py`. Settings > Sound turns them on/off.

The renderer uses Pygame polygons, not a free-rotation 3D engine. Falls are
detected by `BloxorzProblem.fall_result()` / `GameSession.fall()`; solvers still
only use `get_successors()`, so falling never appears in a solution. IDS is the
existing implementation named `DFS` internally.

## Tests

Run from the repository root with the virtual environment activated:

```powershell
python -m pytest -q                                  # all tests (~25 s)
python -m pytest -q --ignore=tests/test_gui.py       # engine and solvers only (~1 s)
python -m pytest -q tests/test_roll_block.py         # one file
```

- `test_state`, `test_roll_block`, `test_validate`, `test_switches`, `test_problem`:
  game state, rolling/splitting, valid moves, switches, falls.
- `test_solvers`: BFS, IDS, UCS and A* find correct solutions and stop on unsolvable stages.
- `test_gui`: rendering, caches, replay, save/load and the real solver worker.

## Editing the GUI

- `src/gui/renderer3d.py`: geometry, colors, projection, tile symbols, camera.
- `src/gui/theme.py`: shared colors, layout sizes and fonts.
- `src/gui/themes.py`: Dream City / Blueprint / Forest palettes and theme switching.
- `src/gui/ui.py`: reusable buttons with hover/pressed/disabled/selected states.
- `src/gui/presentation.py`: state-dependent layout, solver panel and menus.
- `src/gui/app.py`: input and game/solver/replay integration.
- `src/gui/animation.py`: animation duration and progress.
- `src/gui/replay.py`: playback cursor and state transitions.
- `src/gui/solver_gateway.py`: background processes, timeout and cancellation.
- `src/gui/contracts.py`: shared interfaces; coordinate changes across modules.

Run `python main.py` and the tests after editing.

## Benchmark

```powershell
python -m src.solvers.benchmark                  # all test stages, 60 s limit per run
python -m src.solvers.benchmark --time-limit 30
python -m src.solvers.benchmark --plot-only      # redraw charts from the CSV
```

Results go to `data/benchmark_results.csv` and `data/chart_*.png`; see
[benchmark notes](docs/benchmark.md).

## Project layout

- `levels/`: JSON stage definitions shared by the game and solvers.
- `data/`: generated benchmark CSV files and comparison charts.
- `assets/`: backgrounds, fonts, music and sound effects used by the GUI.
- `docs/`: benchmark notes and UML diagrams (`docs/uml/`).
- `src/engine/`: state, stage loading, transitions, and tile mechanics.
- `src/solvers/`: search algorithms, profiling, and benchmark runner.
- `src/gui/`: Pygame application.
- `tests/`: automated checks for engine, stages, solvers, and integration.

## Themes

Dream City is the default. Click the theme name beside the logo (or press T in
the main menu) to cycle through Dream City, Forest Ruins and Paper Blueprint.

All themes use the same Pygame renderer and need no extra dependencies. Static
board/material layers and UI are cached. No gameplay or solver algorithm is
reimplemented by the themes. The chosen theme is not saved between sessions yet.

## Credits

Background images, fonts, music and sound effects are listed with their sources
and licenses in [assets/ATTRIBUTION.md](assets/ATTRIBUTION.md).
