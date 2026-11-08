#!/usr/bin/env python3
"""Build only the cost-matching report page and its shared data assets."""
import json

from build_cost_per_km import build


if __name__ == '__main__':
    data = build(target_page='cost-matching.html')
    print(json.dumps({'page': 'cost-matching.html', 'projects': len(data['projects'])}, indent=2))
