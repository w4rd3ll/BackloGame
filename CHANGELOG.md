# Changelog

## 0.5.2 — 2026-10-04

- Show a large original-cover preview on hover in the SteamGridDB gallery, with a short delay and placement within the window. Hide it on pointer exit, scrolling or resizing.
- Apply a cover by double-clicking its gallery thumbnail or selected preview; prevent overlapping apply requests.

## 0.5.1 — 2026-10-04

- SteamGridDB searches selected content categories directly, so Adult and Humor covers appear without enabling Standard covers.
- Combine selected categories with deduplication and paginate matching artwork; cache results briefly for stable backward navigation.

## 0.5.0 — 2026-10-03

- Compare catalog fields without cross-catalog enrichment; Steam descriptions retain their original source. Remove the description-language warning and place the SteamGridDB apply button above the preview.

- Keep library and gallery images mounted when selecting a game or cover; reuse the library sort collator and index games when decorating rows.

- Clear stale gallery images and selected previews immediately when switching artwork orientation or loading another page.

- SteamGridDB numbered page navigation replaces cumulative load-more scrolling.
- Configurable 12/32/64/128 MiB cover download limit (64 MiB by default); large covers can still be compressed for HTML sharing.
- Animated WebM thumbnails use their original image for gallery previews; Standard/Adult/Humor content is selected with shared checkboxes.

- Persistent SteamGridDB gallery filters shared across games: Adult/NSFW, humor, sizes, style, animation, file format and flashing imagery. Filters refresh the gallery automatically.

## 0.4.1 — 2026-10-02

- Show the app window after portable updates, including updates launched by older helpers using a hidden startup window.
- Keep explicit --hidden smoke-test launches hidden.

## 0.4.0 — 2026-10-02

- Share the current filtered category as a standalone offline HTML file with embedded local covers and optional personal notes. Covers are resized to at most 224 × 300 pixels and compressed as WebP without changing library originals.

- Compare Steam, Metacritic and Wikipedia side by side when refreshing metadata.
- Select individual fields from different catalogs or retain their existing values; save the combined selection atomically.
- Independent catalog loading and errors, with automatic selection only for a unique exact title match.

- Explicit No series filter, placed last; missing series defaults to No series on game saves and imports.
- Choose notes, series or both in card details; vertically center list titles when details are hidden.
- Remove redundant help text, move catalog actions above descriptions and align the wordmark.

## 0.3.1 — 2026-10-02

- Wait for every running instance from the installation folder before replacing program files.
- Move runtime directories atomically so a locked DLL cannot leave a partially moved installation.
- Preserve rollback errors and avoid starting another instance when an existing one blocks an update.
- Add regression checks for repeated failures with locked DLLs and a second running instance.

## 0.3.0 — 2026-10-02

- Full-card editing preserves unchanged original HLTB records, including their
  extra imported fields. Catalog metadata updates retain a thumbnail crop of an
  independently selected cover and invalidate crops only when their image changes.

- Uniform cards use a 2:3 artwork area with a blurred background for wide images
  and compact aligned details without note placeholders. Manual horizontal
  thumbnails work with catalog-selected covers and survive ordinary edits.

- SteamGridDB gallery with independent portrait and landscape covers, local
  image storage, reset per format and private API-key settings with instructions.
- Unified cover selection with SteamGridDB first, followed by Metacritic, Steam
  and Wikipedia. Removed the separate Steam cover refresh action and endpoint.
- Unused cover cleanup after deletion undo expires; shared artwork, merge
  snapshots and existing bounded backups are preserved.

- Alternative Steam, Metacritic and Wikipedia cover/detail selection, including
  HLTB imports. Catalog updates retain progress, notes and the original source.
- Missing-cover repair with catalog fallback and cancellable bulk series filling
  from explicit Wikidata relationships. Existing series are preserved.
- Right-click actions for catalog updates and merging two selected game cards.

- Explicit two-card merge preview, bounded backups and a reversible merge.
  Notes, tags, series, source references and original card metadata are retained.
- Playthroughs keep their own platform; planning a Steam replay preserves an
  earlier console completion. Imports recognize merged source IDs, and platform
  statistics count completions on their recorded platform.

- Remembered bars/pie switch for distribution charts, with colorful interactive
  donut segments, percentage legends and grouped smaller values.

- Replaying category and completion history, with additive dates and removable
  date chips. The latest remaining date drives library labels and sorting.
- Preserve legacy and HLTB playthrough dates; repeated imports merge dates
  without erasing local replays or multiplying already imported events.
- Themed statistics dialog: category/platform/date filters, unique completed
  games, dated playthroughs, yearly/monthly activity and genre/platform/release
  distributions. Chart clicks open the corresponding games.

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
