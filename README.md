# Operation Sandstorm 1.1 - a new mission for IGI 2: Covert Strike

Download the release (`Setup.exe` + `Sandstorm.dat`), run `Setup.exe`, pick your IGI 2 folder, Install. Sandstorm comes after
the original missions and is unlocked. This repository is the source; it contains no game files.

## Works with
Any IGI 2: Covert Strike (GOG, retail / CD with the official patches, other stores, community patches, any language).
Setup builds the mission from your own game files and says exactly what is missing if something is.

On an `igi2.exe` of the common build (GOG, GOG with the widescreen patch, the community 1.3 exe ...) Setup applies the mission's
engine fixes; every byte it changes is checked first. On any other exe the mission installs without them and you lose: the
freeze fix after a mission, Alt+Enter and taskbar handling, DPI / resolution handling, the reload / animation speed fix and the
credits page. Setup logs your exe hash in `_Sandstorm_backup\manifest.txt` - send it to 1QDeath (Discord) to get it supported.

## Resolution and frame rate
- Options > Graphics: 16 sizes, applied at the next start. Or `dgVoodoo.conf` `[DirectX]` `Resolution = h:1920, v:1080`.
- Frame cap: `dgVoodoo.conf` `[GeneralExt]` `FPSLimit = 60` (0 = none), or `dgVoodooCpl.exe`.

## Uninstall
Windows Settings > Apps > Operation Sandstorm. Every changed file comes back, igi2.exe included.

## Known issues
- In the ending cutscene, enemies may snap between animations.

## Source layout
`installer/` Setup.exe source (C#, .NET 4.5) and a tiny ASI loader; `release/` the release tooling; `builder/` the mission builder.

## Credits
Made by 1QDeath - Discord: 1QDeath - github.com/1QDeath. IGI 2: Covert Strike (c) Innerloop Studios / Codemasters. dgVoodoo 2 by Dege.

## Licence
See `LICENSE`.
