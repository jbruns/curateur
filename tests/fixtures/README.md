# Test Fixtures

Curateur test resources modeled after No-Intro and Redump naming conventions. These files are intentionally small placeholders; only filenames and directory structures matter.

## Directory Layout
- `roms/nes/`
  - `Example Adventure (USA).zip`
  - `Prototype Fighter (Europe) (Rev 1).zip`
  - `Dual Strike (USA, Europe).zip`
  - `Trio Dash (USA, Europe, Japan).zip`
  - `World Explorer (World).zip`
  (multi-region examples ensure `World` remains a standalone tag when present)
- `roms/psx/`
  - `Sample Saga.m3u` referencing discs in `.multidisc/`
  - `.multidisc/Sample Saga (Disc 1|2).cue/bin`
  - `Game Name '98 (USA) (En,Fr,De,Es,It,Nl) (RE).cue`
- `roms/dreamcast/`
  - `Demo Orbit (Disc 1).cue/` disc-subdirectory containing matching `.cue`, `.gdi`, and data tracks

## es_systems.xml
`tests/fixtures/es_systems.xml` maps the three systems above using relative paths so tests can parse and traverse without additional setup.

Use these fixtures in unit/integration tests for filename parsing, disc-subdir detection, and media naming.
