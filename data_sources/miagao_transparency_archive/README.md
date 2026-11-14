# Miagao official transparency archive

Built with `../../crawl_miagao_transparency.py` from the Municipality of
Miagao's public WordPress API on 10 November 2026.

The crawl covers the Transparency category and its descendants, all Full
Disclosure Policy pages, and every link or embedded source URL in those posts
and pages. It found 28 transparency categories, 366 transparency posts dated
2010-01-04 through 2026-10-07, 11 Full Disclosure pages, and 1,139 unique
linked URLs. It downloaded 844 of 846 linked files under the official site's
`wp-content/uploads` directory (about 205 MiB). The files are named by a hash
of their source URL; the inventory maps each one back to its official URL and
the post or page where it appeared.

Inventory: `../../analysis_output/miagao-transparency-source-inventory.json`.

The recurring downloader is `../../watch_miagao_transparency.py`. Run it once
with `python3 ../../watch_miagao_transparency.py --once` to refresh the catalog,
download new uploads, parse newly found PDF/JPEG files with the Miagao OCR
supervisor, and publish `/historical`. Run it without `--once` as a long-lived
process to check the official site every six hours (configurable with
`--interval-seconds`). Keep it running under the host's service manager for
automatic checks after reboot. A failed crawl is logged and retried on the next
cycle; downloads and inventory updates are written atomically.

Two official links returned HTTP 404 during the crawl:

- `LDRRMF-Utilization-March-2019.xlsx` — the related post also links to PDF
  and scanned-image copies, which are included in this archive.
- `Manpower-complement-3rd-quarter-2025.xlsx` — no replacement for this exact
  quarter was found in the official media library. The official site has
  neighboring 2025 quarter files, but those are not substitutes.

The inventory keeps both broken links and their originating posts visible.
This is a source capture, not a claim that the files have been parsed or
reconciled. Rerun the crawler to refresh the archive; existing files are
reused by URL hash.
