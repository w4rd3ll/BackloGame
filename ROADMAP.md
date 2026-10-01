# Next release checklist

## Required before the next release

- [x] Manual update: Settings → Check for updates, version and changelog preview.
- [x] Automatic update checking, configurable in settings.
- [x] Safe application update: preserve `data`, close the running EXE, verify the
      downloaded package, apply on restart, and keep one rollback copy.
- [x] Handle offline checks, interrupted downloads and failed updates.
- [x] Check the updater against the actual GitHub release, not only mock tests.

Verified the actual v0.1.0 ZIP download and GitHub SHA256 digest. The PowerShell
replacement and failed-file rollback were tested with isolated fixtures and
preserved data. The compiled 0.2.0 EXE passed real WebView startup, clean/discard/cancel close
checks and native close-update-relaunch on a separate portable copy. The game,
notes and settings were preserved, with one rollback folder. Replacement was
tested with the 0.2.0 bundle itself; 0.1.0 requires a first manual update.

## Library integrations in progress

- [x] Steam owned-game import with selectable covers and duplicate detection.
- [x] HLTB public-profile import, with its official CSV export as fallback.
- [x] Repeated import preserves local notes, favorites, covers and manual order;
      replacing existing values requires explicit field selection.
- [ ] Bidirectional HLTB sync: confirm catalog matches before creating remote
      entries, track acknowledged statuses separately on each side, and preview
      pulls, pushes and conflicts. Never propagate deletions automatically.
- [ ] Verify authenticated HLTB writes and login/session handling before exposing
      remote-write controls. Browser access to HLTB login was blocked during
      development; remote writes have not been tested or implemented.

`sync_plan.py` implements status reconciliation without network or database
writes. It is not yet connected to the interface and does not establish a
working bidirectional integration.

Updates and library synchronization are different features. Release 0.2.0 supports updates and read-only imports;
authenticated bidirectional HLTB writes remain unsupported.
