# Operation Sandstorm 1.6 - a new mission for IGI 2: Covert Strike

Download the release (`Setup.exe` + `Sandstorm.dat`), run `Setup.exe`, pick your IGI 2 folder, Install. Sandstorm comes after
the original missions and is unlocked. This repository is the source; it contains no game files.

## Works with
IGI 2: Covert Strike with the **GOG `igi2.exe` build (version 1.3)**: the GOG release, GOG with the widescreen patch, and community
exes of the same build (the 1.3 / Neonix / MPA exes), any game language. The mission needs its engine fixes, so Setup checks your
`igi2.exe` byte by byte first: an exe it cannot fix (retail CD exes, other builds) is refused before anything changes, with its
hash - send that to 1QDeath (Discord) to get it supported. Setup builds the mission from your own game files and says exactly what
is missing if something is.

## Before you run Setup
- Extract the whole zip first (Setup.exe and Sandstorm.dat must be in the same folder).
- If Windows says the file is blocked: right-click the zip > Properties > Unblock, then extract again.
- Game in Program Files? Right-click Setup.exe > Run as administrator, or move the game folder (for example to C:\Games).
- If something goes wrong, Setup names the step and writes `%TEMP%\Sandstorm_Setup.log` - send that file to 1QDeath (Discord).

## Resolution and frame rate
- Options > Graphics: 16 sizes, applied at the next start. Or `dgVoodoo.conf` `[DirectX]` `Resolution = h:1920, v:1080`.
- Frame rate: capped at 60 by default. For more, change `FPSLimit` in `dgVoodoo.conf` `[GeneralExt]` (0 = no cap), or use `dgVoodooCpl.exe`.

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
