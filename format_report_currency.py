#!/usr/bin/env python3
"""OBSOLETE: currency formatting now runs in shared modules used by page builders."""
import json


def apply():
    raise RuntimeError(
        'format_report_currency.py is obsolete; page builders apply '
        'report_currency_module.format_tables to their own rendered HTML.'
    )


if __name__ == '__main__':
    print(json.dumps({'status': 'obsolete', 'pageWrites': 0}))
