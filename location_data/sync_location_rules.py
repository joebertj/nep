#!/usr/bin/env python3
"""Export the PH location DB text helper to ODV's static build tooling."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def main():
    source=ROOT/'location_text.py';dest=ROOT.parent.parent/'open-data-visualization/analysis/ph_location_text.py'
    dest.write_bytes(source.read_bytes())
    report={'source':str(source),'destination':str(dest),'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'policy':'One shared geographic text normalizer; no database, server address or boundary claims copied to public repo.'}
    (ROOT/'location_rules_export.json').write_text(json.dumps(report,indent=2)+'\n');print('Exported PH location text helper to ODV analysis.')
if __name__=='__main__':main()
