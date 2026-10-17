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
application. This opens the basic 2D GUI for testing gameplay. It starts with
stage 01; press Enter after winning to continue through stages 02 and 03. The
GUI is a simple test view, not the finished game presentation.

## Project layout

- `levels/`: JSON stage definitions shared by the game and solvers.
- `data/`: generated benchmark CSV files and comparison charts.
- `src/engine/`: state, stage loading, transitions, and tile mechanics.
- `src/solvers/`: search algorithms, profiling, and benchmark runner.
- `src/gui/`: Pygame application.
- `tests/`: automated checks for engine, stages, solvers, and integration.
