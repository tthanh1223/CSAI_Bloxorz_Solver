# Runtime GUI assets

The interactive GUI uses locally bundled OpenAI imagegen assets created for this
project: wide_dreamy_fantasy_landscape_scene_pastel_pink.png (Dream background),
dream_city_background.png (fallback), forest_ruins_background.png,
forest_materials.png. No third-party stock texture website was used. Blueprint
paper, drafting lines, UI, playable geometry and satin brass grain are
code-rendered. No network is needed at runtime.

## Fonts

`assets/fonts/` bundles Outfit (Regular/Medium/Bold), JetBrains Mono
(Regular/Bold) and Space Grotesk (Medium), all under the SIL Open Font License.
If a file is missing the GUI falls back to installed system fonts.

## Music and sound effects

Source and license still need to be recorded for:

- `bgm/the_mountain-retro-game-593063.mp3`
- `bgm/cheerful_puzzle.wav` (fallback track)
- `sfx/roll.wav`, `sfx/fall.mp3`, `sfx/win.mp3`
