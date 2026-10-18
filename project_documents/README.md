# On-demand project documents

BetterGov owns this project and supplies the project API/document mirror.
There is no bulk replication or separate project listing scraper. The maintained
csiiiv index supplies exact proposal IDs; BetterGov supplies live metadata.

## Local use with a PH VPN

Connect the user's PH VPN on the local Mac, then run:

```sh
bash deployment/run_project_documents_local.sh 2027DPWH-Proposal-03421
```

Only the requested project's POW and geotagged-photo PDFs are fetched. An
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
- full photo-document page renders preserving captions/coordinates, or the
  original PDF opened directly by a PH-connected browser on request.

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
verified; the original PDF page has not yet been retrieved/identified. It is
kept separate from machine-extracted rows, and does not establish the full POW.

## Current access status

After the user switched the PH VPN, the isolated Chrome retry still returned
`ERR_HTTP2_PROTOCOL_ERROR` for both Burol PDFs. With HTTP/2 disabled, both
returned `ERR_EMPTY_RESPONSE`. The original DPWH portal returned HTTP 403 with
a “Just a moment...” challenge page in the isolated Chrome session. Metadata
access remains separate from PDF access. No original Burol PDF or photo page
has yet been retrieved, so automatic extraction/photo rendering remains
unverified. The two supplied-image rows are clearly identified separately.

The archive release `20dc32fea` is deployed. This worker/UI integration is a
new local change requiring the normal ODV commit/push and worker setup before
publication. It has not been deployed.

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
Record links open metadata only while the PDF host is unavailable; preparing
POW/photos remains an explicit action within the popup.
