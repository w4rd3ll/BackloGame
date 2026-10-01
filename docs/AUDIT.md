# Code cleanup and portable packaging audit

First-party code reviewed: server.py, desktop.py, storage.py, all static JS,
HTML/CSS and application assets; build scripts, dependency declarations and tests.

- No hard-coded user API keys or active integrations for books, films, television,
  animation or comics found in current application code. Obsolete credential/media
  modules and historical snapshots are excluded from this source tree and packages.
- Steam, Wikipedia, Wikidata metadata and Metacritic remain active game sources.
  RuTracker is an external search link. The generated local library token is a
  request protection mechanism, not a third-party API credential.
- Removed unused front-end platform constant, obsolete deletion-confirmation CSS,
  implicit database migration and stale documentation describing removed features.
- Retained old browser preference keys and storage environment alias intentionally
  for compatibility. Negative tests for removed providers are regression checks.
- Native windows bind separate localhost ports. A public copy cannot attach to a
  running personal development server and display its library.
- Explicit data directories are resolved to absolute paths for WebView2 profiles.
- Windows uses shared system WebView2 Evergreen; no browser runtime is bundled.
  OS-specific setup lives in desktop_platform.py. Linux packaging is not yet tested.
- Build inputs are explicit: application code and static assets. No user
  database, saved game covers, API credentials, screenshots or test output are
  bundled. Build promotion targets only BackloGame-Release, never Personal.
- Public and development libraries start empty; English is the default.
- Personal snapshot preserves game payloads, dates, manual ordering, thumbnails,
  categories, platforms and supported settings. Unsupported settings are omitted
  and SQLite is compacted. A fresh full backup is made from the cleaned snapshot;
  historical databases and caches are not copied into the public package.

Validation: library/backup/provider regression tests, portable-storage tests,
filter/sort/localization JS checks, and real desktop-window startup checks for
the empty and populated EXE copies. Tested on Windows 11 x64.

Original development files remain outside this new source tree as a rollback
copy. They are not public-release inputs and must not be uploaded wholesale.
