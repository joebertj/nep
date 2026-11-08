#!/usr/bin/env python3
"""Build only the historical project-repeat page and its data asset."""
from build_repeats_split import build_repeats_historical_page as render_historical_page
from pathlib import Path

ROOT=Path(__file__).resolve().parent
STATIC=ROOT.parent/'open-data-visualization/static/nep-preview'
OUT=ROOT/'analysis_output'

if __name__ == '__main__':
    result=render_historical_page()
    html=result.pop('html').rstrip()+'\n'
    data=result.pop('data')
    data_name=result.pop('dataFilename')
    (STATIC/'repeats-historical.html').write_text(html,encoding='utf-8')
    (OUT/'repeats-historical.html').write_text(html,encoding='utf-8')
    (STATIC/data_name).write_text(data,encoding='utf-8')
    (OUT/data_name).write_text(data,encoding='utf-8')
    print(result)
