"""Use the shared research header and table controls for the numbered questions."""
import re
from uniform_report_menu import apply_page

QUESTIONS = [
    ('amendment-access.html', 'Infrastructure and access'),
    ('questions.html', 'Hearings and budget lines'),
    ('contractor-workload.html', 'Contractor track records'),
    ('road-handover.html', 'Roads after handover'),
]


def render_report(text, filename):
    sections = []
    for number, (path, title) in enumerate(QUESTIONS, 1):
        href = path + ('#question-2' if number == 2 else '')
        current = ' aria-current="page"' if path == filename else ''
        sections.append(f'<a href="{href}"{current}>Question {number} · {title}</a>')
    nav = '<nav class="questions-menu" aria-label="Research questions">' + ''.join(sections) + '</nav>'
    related = re.search(r'<nav aria-label="Related research">.*?</nav>', text, re.S)
    text = apply_page(text, filename)
    text = re.sub(r'<main\b[^>]*>', lambda _: '<main class="question-report">' + nav, text, count=1)
    if related:
        text = text.replace('</main>', related[0] + '</main>', 1)
    return text.replace('</head>', '<link rel="stylesheet" href="report-table-readability.css">'
                        '<link rel="stylesheet" href="question-reports.css">'
                        '<script defer src="report-table-readability.js"></script>'
                        '<script defer src="question-charts.js"></script></head>', 1)
