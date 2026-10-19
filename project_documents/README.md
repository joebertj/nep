# On-demand project documents

BetterGov owns this project and supplies the project API/document mirror.
The maintained csiiiv index supplies exact proposal IDs; BetterGov supplies live metadata.
The requested background queue caches selected POW and RDC PDFs, plus downloadable geotagged-photo files in their source formats, on T5 EVO. Tables keep the original photo URLs.

## Local use with a PH VPN

Connect the user's PH VPN on the local Mac, then run:

```sh
bash deployment/run_project_documents_local.sh 2027DPWH-Proposal-03421
```

Only the requested project's POW and RDC PDFs are fetched; photos remain direct links. An
isolated `.venv-documents` environment is created if needed. Original PDFs,
OCR/table evidence, extracted candidates and rendered photo pages are cached
under `data_sources/dpwh_project_documents/on_demand/<proposal-code>/`.
That directory is ignored by Git. The command exits with an error if either
source cannot be retrieved or processed; metadata access is not PDF access.

For a long-running on-demand worker:

```sh
bash deployment/run_project_documents_local.sh serve
```

The worker listens only on `127.0.0.1:8879`. A PH HTTP proxy can alternatively
be configured with the standard `HTTPS_PROXY` environment variable. TLS
verification remains enabled by default. Proxy credentials are never written to reports.
The existing local VPN need not be configured inside Python if it routes the
terminal's traffic through PH.

## ODV integration

`build_project_document_view.py` copies the static view and worker sources to
ODV. The new `/api/nep-documents/{code}` routes proxy to the optional worker,
configurable with `DOCUMENT_SERVICE_URL`. The isolated worker can run as:

```sh
cd open-data-visualization/analysis
python -m project_documents.service --port 8879
```

Install that directory's requirements in its own environment, not the existing
ODV application's environment. A Linux worker needs the `tesseract` executable
and English language data for scanned POWs. A Mac worker uses local Apple
Vision OCR when needed. No external OCR service receives the PDFs.

`static/nep-preview/project-documents.html?project=2027DPWH-Proposal-03421`
opens the evidence view. It is linked internally from exact-title project rows,
not added to the main menu. Metadata is loaded only on request; POST `prepare`
requests this project's PDFs. Only two worker tasks execute concurrently.

The page shows:

- largest recovered bill rows, quantities, original units and amounts;
- calculated shares of the explicitly named **NEP allocation** denominator;
- printed unit cost versus calculated amount/quantity and arithmetic status;
- CSV exports and original PDF-page links;
- direct source links to geotagged photo files; downloaded copies stay external and are not published.

## Evidence rules

Only header-qualified bill tables are parsed. Unit-price-analysis pages and
recapitulation totals do not become another set of payable rows. Native table
extraction is preferred; image-only pages require OCR. Unknown quantities are
never supplied from allocation values. Candidate extraction does not claim a
complete or reconciled POW ledger. Repeated identical observations are grouped
with source pages rather than silently summed.

The Burol seed contains exactly two rows from the user-supplied image:
988,328 kg reinforcing steel / PHP 50,757,582.92 and 3,896.83 cubic meters of
structural concrete / PHP 37,537,183.76. Their subtotal is PHP 88,294,766.68,
58.8632% of the PHP 150M NEP allocation. The seed is clearly labeled as image-
verified; the original PDF page is now identified and cross-checked as page 2. It is
kept separate from machine-extracted rows, and does not establish the full POW.

## Current access status

The latest Burol retest succeeded using standard HTTPS with TLS verification
on. Both original PDFs are cached privately. The five-page POW contains an
itemized bill on page 2: 14 as-submitted direct-cost rows sum exactly to its
printed PHP 111,386,548.22 subtotal. Steel (988,328 kg / PHP 50,757,582.92)
and structural concrete (3,896.83 cubic meters / PHP 37,537,183.76) agree
with the supplied-image reference. The one-page geotagged photo PDF rendered.
The audit is `analysis_output/burol_document_retest.json`.

The mapped itemized layout separates submitted/evaluated quantities, direct
cost totals, direct unit costs and inclusive unit costs. Inclusive unit cost
must not be mistaken for a line total. Direct-cost reconciliation does not
reconcile markup, VAT, EAO or the complete POW. Raw native table cells remain
in `pow-native-tables.json` beside the cached PDF. The UI never adds submitted
and evaluated versions together. No bulk document download was performed.

The parser/UI changes are local; deploying static files does not install or
start the optional document-processing worker.

## Explicit PDF-host TLS bypass

At the user's request, the local command supports:

```sh
bash deployment/run_project_documents_local.sh 2027DPWH-Proposal-03421 --allow-unverified-pdf-tls
```

This bypass is restricted to `s3.infrawatch.ph` public PDF fetches and does not
extend to redirects to other hosts. API metadata retains TLS verification.
Each cached document records `transportTlsVerified`. For the worker service,
set `DPWH_DOCUMENT_ALLOW_UNVERIFIED_TLS=1` explicitly. The default is off.

## Browser retrieval and project popups

With local Google Chrome installed, use the browser transport on the PH VPN:

```sh
bash deployment/run_project_documents_local.sh 2027DPWH-Proposal-03421 --browser --allow-unverified-pdf-tls
```

For a browser-backed worker, set `DPWH_DOCUMENT_TRANSPORT=browser` and,
if explicitly needed, `DPWH_DOCUMENT_ALLOW_UNVERIFIED_TLS=1` before `serve`.
`DPWH_DOCUMENT_BROWSER_HTTP1=1` disables HTTP/2 for hosts reporting protocol
errors. The browser uses an isolated session; it does not read a personal Chrome
profile. Document navigation and redirects are restricted to the selected host.
Google Chrome must be installed on the worker, or set
`DPWH_DOCUMENT_BROWSER_CHANNEL` to an installed Playwright browser channel.

A table link opens a named project popup with `prepare=1`; that explicit click
requests only the selected project's POW/photos. Opening the view with just a
project code loads metadata and any cached results. No other documents are
queued. Popup blocking falls back to the normal link.

RDC signatory extraction (DE and Governor) is deferred until POW extraction
and photo rendering have been demonstrated with original PDFs.

## Transparency document coverage column

`transparency_status.py` derives coverage from the pinned csiiiv transparency
snapshot and its retained NEP/API reconciliation. No PDFs or new live API calls
are needed. The public index carries matching provenance, retrieval timestamp,
counts and methodology. The detailed audit is retained as
`analysis_output/dpwh_transparency_document_coverage.json`.

DPWH FY2027 project tables receive one `DPWH transparency` column. Unmatched
has highest precedence, including unresolved candidate/ambiguous matches.
Otherwise show the number of listed documents; fewer than five is incomplete
under the requested screening threshold. Comparison rows with multiple FY2027
projects show unmatched if any project is unmatched, otherwise the lowest
count, with individual details in the tooltip. Historical GAA rows are excluded.
FAP records outside the domestic NEP listing are labelled outside scope.
Five documents does not certify the document mix, availability or contents.
Record links open metadata and cached results; preparing
POW/photos remains an explicit action within the popup.


## External storage and background queue

Raw documents, OCR evidence and intermediate results live on `/Volumes/T5 EVO/bettergov-research/nep/data_sources/dpwh_project_documents`.
The repository's ignored `data_sources/dpwh_project_documents` path is a symlink there.
Only curated parsed values belong in published assets; do not copy PDFs into ODV.

`download_pow_rdc_queue.py` processes the existing indexed project queue sequentially,
with a three-second pause between projects, checkpointing `queue-status.json`.
It downloads POW/RDC only and resumes completed cached entries. Errors are counted;
a later run retries failed projects. It refuses an unmounted external volume.
Background logs and process IDs are in `/Volumes/T5 EVO/bettergov-research/jobs/`.

`python3 storage/external_storage.py large` moves regular files of **100,000,000 bytes or larger**
from both repositories to their corresponding external repository directories.
It excludes Git internals and security/configuration directories, does not follow symlinks,
and verifies SHA-256 before atomically replacing each original file with a symlink.
The external `migration.jsonl` records the original path, destination, bytes and hash.
Tracked large files may appear as file-to-symlink changes: review those before committing;
the original data are retained on the external disk. Git history is unchanged.

The external background queue stores downloadable geotagged-photo attachments as-is without format validation. Photo display remains a direct source link; no image assets or PDFs are copied into either public repository.


## DPWH Indepth publication

Run `python3 build_project_document_view.py` then `python3 uniform_report_menu.py`
to refresh `dpwh.html`, its parsed-evidence JSON and the consistent site menu.
The standalone generator is `build_dpwh_indepth.py`. It whitelists bill fields,
source checksums/page references and signatory candidates; it never copies raw
PDFs, image pages, OCR dumps or local cache paths into the public assets.

The page works from static `dpwh-in-depth-data.json`, without an online worker.
It has project/basis selection, cost-driver bars, search/sort, ten-project pagination,
all-row detail dialogs and CSV exports. DE and RDC signatories occupy separate
columns. All financial bases and reconciliation limits remain visible.

The PH VPN retry on 2026-10-18 returned HTTP 200 for the Burol and proposal-00001
POW PDFs via curl with standard TLS verification. The background queue now uses
that same transport, runs sequentially, and stops on HTTP 429 or three consecutive
failed projects. It does not automatically launch repeated Chrome retries.
The running queue must be stopped before switching transport or storage.

## Offline PDF watcher

Run with the document environment:

```sh
/private/tmp/nep-document-env/bin/python watch_project_documents.py --interval 30
```

Use `--once` for a single processing/publication pass. The watcher has **no network
requests**, does not commit or deploy, and runs as a single instance. It watches
metadata-identified POW and RDC PDF files in the external
cache; `.part` files and unrelated PDFs are excluded. A project being handled
by the downloader is deferred, and project-level locks prevent concurrent writes
with new worker instances.

Completed downloader parsing is reused. A PDF without parsed evidence is hashed
and parsed; unchanged files are skipped. Parser-code changes trigger a new parse
on the next pass. Failed parsing is recorded once and retried when the file or
parser changes, rather than on every poll. Photos are registered with their
checksum and original source link, without rendering or publishing their PDF.

Changes refresh only `dpwh.html`, `dpwh-in-depth-data.json` and
`dpwh-in-depth.js` in `analysis_output` and ODV `static/nep-preview`, plus shared
presentation assets used by the builder. Publication uses atomic file replacement.
Raw evidence, watcher fingerprints and logs stay on T5 EVO. Git stages and the
live site are untouched. Pause the watcher when freezing files for a commit if a
stable publication snapshot is required.

Progress: `data_sources/dpwh_project_documents/watcher-state.json` (ignored,
external). Log: `/Volumes/T5 EVO/bettergov-research/jobs/indepth-watcher.log`.
Unmounting T5 EVO stops work; there is no internal-disk fallback.
