# Sound effects

Put sound files here, named after the event they play on:

| File name | Plays when |
|---|---|
| `roll`   | the block rolls one step |
| `switch` | a switch opens/closes a bridge |
| `split`  | the block splits into two cubes |
| `fall`   | the block falls off the board |
| `win`    | the block sinks into the goal |

Use `.wav`, `.ogg` or `.mp3`, e.g. `roll.wav`. Keep clips short (under 1 second;
`win` can be ~1-2 seconds). A missing file falls back to a tone generated in
`src/gui/sfx.py`, so you can add the files one at a time.

Sound is on at start-up; Settings > Sound turns it off. Volume: `SoundBank(volume=0.6)`
in `src/gui/sfx.py`.

Record each file's source and license in `assets/ATTRIBUTION.md`
(e.g. Kenney.nl or freesound.org, CC0).
