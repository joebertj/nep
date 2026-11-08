"""Publish large top-level JSON arrays as small static shards plus a manifest."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
LOADER_SOURCE = ROOT.parent / 'open-data-visualization/static/nep-preview/report-json-shards.js'
MAX_SHARD_BYTES = 4_000_000
MAX_INDEX_BYTES = 6_000_000


def _encoded(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def write_sharded_json(path: Path, payload: dict[str, Any]) -> Path:
    """Write a compact ``*-index.json`` and shards for arrays exceeding budget.

    The original JSON file is left intact for builder inputs and explicit full
    exports. Page loaders should fetch the returned manifest instead.
    """
    if not isinstance(payload, dict):
        raise TypeError('sharded JSON root must be an object')
    index = dict(payload)
    collections: dict[str, dict[str, Any]] = {}
    directory = path.parent / f'{path.stem}-shards'
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True, exist_ok=True)

    def make_chunks(rows: list[Any], key: str) -> list[list[Any]]:
        chunks: list[list[Any]] = []
        current: list[Any] = []
        current_bytes = len(b'{"rows":[]}')
        for row in rows:
            row_bytes = len(_encoded(row)) + (1 if current else 0)
            if current and current_bytes + row_bytes > MAX_SHARD_BYTES:
                chunks.append(current)
                current = [row]
                current_bytes = len(b'{"rows":[]}') + len(_encoded(row))
            else:
                current.append(row)
                current_bytes += row_bytes
            if current_bytes > MAX_SHARD_BYTES:
                raise ValueError(f'{path.name}.{key} contains a single row larger than the shard limit')
        if current:
            chunks.append(current)
        return chunks

    # Keep metadata and small arrays in the index. Shard the largest arrays
    # until the manifest itself fits comfortably below GitHub's file warning.
    array_keys = [key for key, value in index.items() if isinstance(value, list)]
    array_keys.sort(key=lambda key: len(_encoded(index[key])), reverse=True)
    for key in array_keys:
        if len(_encoded(index)) <= MAX_INDEX_BYTES:
            break
        rows = index[key]
        if not rows:
            continue
        chunks = make_chunks(rows, key)
        files = []
        for number, chunk in enumerate(chunks, 1):
            name = f'{key}-{number:04d}.json'
            data = _encoded({'rows': chunk})
            (directory / name).write_bytes(data)
            files.append({'file': f'{directory.name}/{name}', 'rows': len(chunk), 'bytes': len(data)})
        collections[key] = {'rows': len(rows), 'files': files}
        del index[key]

    if collections:
        digest = hashlib.sha256(_encoded({k: v for k, v in payload.items()})).hexdigest()[:16]
        index['_shardedJson'] = {'schemaVersion': 1, 'version': digest, 'collections': collections}
    index_bytes = _encoded(index) + b'\n'
    if len(index_bytes) > MAX_INDEX_BYTES:
        raise ValueError(f'{path.name} metadata still exceeds {MAX_INDEX_BYTES:,} bytes after sharding')
    index_path = path.parent / f'{path.stem}-index.json'
    index_path.write_bytes(index_bytes)
    return index_path


def attach_loader(html: str, page_name: str) -> str:
    """Include the shared browser loader in a generated page, once."""
    if 'report-json-shards.js' in html:
        return html
    digest = hashlib.sha256(LOADER_SOURCE.read_bytes()).hexdigest()[:12]
    tag = f'<script src="report-json-shards.js?v={digest}"></script>'
    if '</head>' in html:
        return html.replace('</head>', tag + '</head>', 1)
    raise ValueError(f'{page_name} has no closing head tag for the shard loader')
