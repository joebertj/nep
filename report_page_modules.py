"""Shared, in-memory section modules for owner-controlled page builders."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULES = ROOT / 'analysis_output/investigation-page-sections.json'


def reset_page_modules():
    MODULES.parent.mkdir(parents=True, exist_ok=True)
    MODULES.write_text(json.dumps({'pages': {}}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def queue_page_section(page, section_id, html):
    try:
        payload = json.loads(MODULES.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        payload = {'pages': {}}
    pages = payload.setdefault('pages', {})
    sections = pages.setdefault(page, {})
    sections[section_id] = html
    MODULES.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def apply_page_modules(html, page):
    """Return one page with its queued shared sections; never write the file."""
    try:
        sections = json.loads(MODULES.read_text(encoding='utf-8')).get('pages', {}).get(page, {})
    except (OSError, ValueError):
        return html
    for section_id, replacement in sections.items():
        pattern = rf'<section\b[^>]*\bid="{re.escape(section_id)}"[^>]*>.*?</section>'
        if re.search(pattern, html, re.S):
            html = re.sub(pattern, lambda _m, value=replacement: value, html, flags=re.S)
        else:
            html = html.replace('</main>', replacement + '</main>', 1)
    return html
