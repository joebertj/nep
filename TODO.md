# TODO

## Connectivity manual review

- [x] Deploy the `road-segment` and `connects-road-segments` green reasons; live UI and FastAPI now accept both.
- [x] Publish the latest normalized manual-green data generated from the ignored local annotation file. Verified all 243 local annotation records match the generated `connectivity-data.json` rows and the 10-row manual-red FMR export.

## Builder ownership audit

- [ ] Audit remaining build entry points and scheduled refresh order. Each page builder should write only its page and page-owned published data; shared transformations should be called as modules by the owning builder.
