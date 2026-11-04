# FY2019 GAA Volume IA OCR

`pages.jsonl` is a page-by-page OCR transcript of the official DBM FY2019 GAA
Volume IA PDF. Each row records the source page, OCR lines, confidence scores,
and the scope label. It is written incrementally and can be resumed safely.

This is a scanned-document transcription, not a normalized full-year budget
table. Volume IA is only one volume, OCR can misread text and amounts, and it
must not be represented as the complete FY2019 GAA or a DPWH project list.
Review extracted rows against the source PDF before using them for published
totals.

Run from the repository root with the single-thread PaddleOCR environment:

```sh
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 FLAGS_cpu_num_threads=1 \
  .venv-paddle/bin/python parse_fy2019_gaa_volume_ia.py
```

Use `--start-page`, `--end-page`, or `--limit` for a bounded pass. Completed
pages are skipped on subsequent runs.
