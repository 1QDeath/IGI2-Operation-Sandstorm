# Operation Sandstorm - a custom single-player mission for IGI 2: Covert Strike

Made by 1QDeath - Discord: 1QDeath

Operation Sandstorm is a new mission for the GOG version of *Project IGI 2: Covert Strike* (plain or with a widescreen patch).
This repository holds the **source**: the mission builder, the release tooling and the installer. It holds **no game file**:
IGI 2 is a commercial game (Innerloop Studios / Codemasters) and every asset the mission uses comes from the player's own copy.

## Play it
Download the add-on release (`Setup.exe` + `Sandstorm.dat`), run `Setup.exe` and pick your IGI 2 folder. Setup
- builds the mission folder from your own game files (the multiplayer map Sandstorm) plus the mission's own data,
- rebuilds the mission's texture / model / sound packs from your game files (it ships only "recipes" + our own chunks),
- patches your own `igi2.exe` with the mission's engine fixes (it checks the exe before and after, and backs it up),
- adds Sandstorm after the 19 original missions, unlocked, and backs up every file it changes.
Uninstall from Windows Settings > Apps: every changed file comes back from the backup.

## Layout
| folder | what |
|---|---|
| `installer/Setup.cs` | the installer / uninstaller (C# 5, .NET Framework 4.5 WinForms, built with the Framework's own `csc.exe`) |
| `installer/asiloader/` | a tiny ASI loader (`version.dll`) for optional add-ons |
| `release/` | the release tooling: `release2.py` (payload + recipes + exe patch + packing), `recipe.py`, helpers |
| `builder/` | the mission builder: `build_sandstorm.py` and the modules it imports (`tools/`) |

The builder needs the game installed and the mission's own assets (music, voices, pictures), which are not in this repository.
Paths in the scripts point at the author's machine; adjust them for yours.

## Requirements
- *Project IGI 2: Covert Strike*, GOG version - with or without community patches (Setup detects the base).
- Windows 10 / 11. Nothing else to install (.NET Framework 4.5+ ships with Windows).

## Resolution and aspect
- In game: Options > Graphics offers 16 sizes (854x480 up to 3840x2160, 4:3 / 16:9 / 16:10 / 21:9). The choice applies at the next start.
- By hand: in `dgVoodoo.conf` (game folder), section `[DirectX]`, set `Resolution = h:1920, v:1080` (your width / height), or `max`
  for the desktop size. The game writes this line itself when you change the size in the menu.

## Frame rate
- `dgVoodoo.conf`, section `[GeneralExt]`: `FPSLimit = 60` (or 120, 144 ...; 0 = no limit), or use `dgVoodooCpl.exe` in the game folder.

## Uninstall
Windows Settings > Apps > **Operation Sandstorm** > Uninstall. Every file Setup changed comes back from its backup, including
`igi2.exe`, the mission list, the texts and your profile's mission position.

## Known issues
- In the ending cutscene, enemies may snap between animations.

## Credits
- Operation Sandstorm: **Made by 1QDeath** - Discord: **1QDeath** - github.com/1QDeath
- IGI 2: Covert Strike (c) Innerloop Studios / Codemasters.
- dgVoodoo 2 by Dege.

## Licence
See `LICENSE` (placeholder - to be chosen by the author).
