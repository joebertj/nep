#!/usr/bin/env python3
"""Refresh shared popup assets/evidence while preserving every report menu."""
import hashlib
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parent
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'


def main():
    import build_project_evidence
    import report_table_presentation
    build_project_evidence.main()
    versions=report_table_presentation.publish_assets()
    map_version=hashlib.sha256((STATIC/'mpb-location-map.js').read_bytes()).hexdigest()[:12]
    changed=0
    for root in (STATIC,ROOT/'analysis_output'):
        for path in root.rglob('*.html'):
            old=path.read_text();text=old
            menus=re.findall(r'<nav\b[^>]*class="report-nav"[^>]*>.*?</nav>',old,re.S)
            for suffix in ('js','css'):
                pattern=r'((?:src|href)=["\'][^"\']*report-table-readability\.'+suffix+r')(?:\?v=[^"\']*)?'
                text=re.sub(pattern,lambda m:m[1]+'?v='+versions[suffix],text)
            text=re.sub(r'((?:src|href)=["\'][^"\']*mpb-location-map\.js)(?:\?v=[^"\']*)?',lambda m:m[1]+'?v='+map_version,text)
            scripts=list(re.finditer(r'<script\b[^>]*\bsrc=["\'][^"\']*report-table-readability\.js(?:\?[^"\']*)?["\'][^>]*>\s*</script>',text,re.S))
            if len(scripts)>1:
                keep=next((s for s in scripts if 'id=' in s[0]),scripts[0])
                for script in reversed(scripts):
                    if script.start()!=keep.start():text=text[:script.start()]+text[script.end():]
            if re.findall(r'<nav\b[^>]*class="report-nav"[^>]*>.*?</nav>',text,re.S)!=menus:
                raise ValueError('Refusing to change menu: '+str(path))
            if text!=old:path.write_text(text);changed+=1
    print(json.dumps({'updatedAssetReferences':changed,'menuChanges':0,'detailsScriptVersion':versions['js']}))


if __name__=='__main__':main()
