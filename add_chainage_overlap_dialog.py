#!/usr/bin/env python3
"""OBSOLETE: viewer injection is now limited to the owning page builders."""
import json


def build():
    raise RuntimeError(
        'add_chainage_overlap_dialog.py is obsolete; use chainage_overlap_module '
        'from the dpwh-hgab, dpwh-OO2-hgab, and repeats page builders.'
    )


if __name__ == '__main__':
    print(json.dumps({'status': 'obsolete', 'pageWrites': 0}))
