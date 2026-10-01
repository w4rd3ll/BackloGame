# Changelog

## 0.2.0 — 2026-10-01

- GitHub update checks, optional startup notifications, verified ZIP downloads
  and Windows portable replacement on restart with one rollback bundle.
- Startup errors for Python.Runtime.Loader.Initialize explain ZIP unblocking
  instead of incorrectly suggesting WebView2 as the only cause.
- Eight persistent color themes with live previews, coordinated interface
  surfaces, wordmark colors, header icons and browser favicons.
- Steam imports match an existing App ID even when its title or platform was
  edited, avoiding duplicate-key failures during partial and repeated imports.
- A single local Steam history file tracks previously seen App IDs per profile.
  Show new filters each successful check against its previous saved list; the
  first check establishes a baseline. Failed checks do not replace history.
- Steam imports include the Steam tag; confirmed matches merge it with existing
  tags. Purchase-date sorting is unavailable through the public library API.
- Completion dates: calendar input, sorting, date below Completed in cards/list
  and beside it in the compact view.
- Independent sort direction, sort field and view for each category, persisted
  in the portable database.
- Aligned favorite buttons next to wrapped game titles.
- Public HLTB profile and CSV imports with status mapping, replay tags and
  explicit field selection for matches; apply or skip matches in bulk.
- Keep repeated HLTB playthroughs, with the latest completion date on the card.
- Steam library import uses a Cloudflare Worker on the Free plan, so users can
  import a public library without entering a personal Web API key. The shared
  key stays in Cloudflare Secrets; the app no longer displays a VPS address.
  A personal key remains optional and goes directly to Steam without being saved.
- Remote library responses support gzip with a bounded decompressed size.

HLTB imports are read-only; bidirectional synchronization is not supported.

## 0.1.0 — 2026-10-01

First public Windows x64 portable release.

- Game catalogs, locally saved covers, notes, tags, and multiple series.
- Favorites, progress tracking, custom categories and platforms.
- Cards, list and compact list, filtering, sorting, and manual ordering.
- Bulk edits, thumbnail crop, collapsible side panels, and bounded backups.
- English default interface with Russian available in settings.
- Shared system WebView2; no browser runtime included in the download.
- Fixed native-window close deadlock; unsaved changes can be kept or discarded.
- Separated OS-specific window setup for future Linux work.
