#!/usr/bin/env python3
"""Publish the local DPWH evidence snapshot as a small index and JSON shards."""
import hashlib
import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'analysis_output' / 'dpwh-in-depth-data.json'
STATIC = ROOT.parent / 'open-data-visualization' / 'static' / 'nep-preview'
SHARD_DIR = 'dpwh-in-depth-shards'
# Keep each published data shard at or below 10 MB (decimal).
MAX_SHARD_BYTES = 10_000_000


def atomic_bytes(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_bytes(payload)
    temporary.replace(path)


def encode_shard(items):
    return (json.dumps(items, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')


def split_array(key, items, static):
    """Write an array to <=10 MB files and return a compact shard manifest."""
    shards = []
    chunk = []
    chunk_bytes = 2  # []

    def flush():
        nonlocal chunk, chunk_bytes
        if not chunk:
            return
        number = len(shards) + 1
        filename = f'{key}-{number:03d}.json'
        payload = encode_shard(chunk)
        if len(payload) > MAX_SHARD_BYTES:
            raise ValueError(f'{key} shard exceeds {MAX_SHARD_BYTES} bytes: {len(payload)}')
        atomic_bytes(static / SHARD_DIR / filename, payload)
        shards.append({
            'path': f'{SHARD_DIR}/{filename}',
            'itemCount': len(chunk),
            'sizeBytes': len(payload),
            'sha256': hashlib.sha256(payload).hexdigest(),
        })
        chunk = []
        chunk_bytes = 2

    for item in items:
        item_bytes = len(json.dumps(item, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
        additional = item_bytes + (1 if chunk else 0)
        if chunk and chunk_bytes + additional > MAX_SHARD_BYTES:
            flush()
            additional = item_bytes
        if chunk_bytes + additional > MAX_SHARD_BYTES:
            raise ValueError(f'One {key} item exceeds {MAX_SHARD_BYTES} bytes: {item_bytes}')
        chunk.append(item)
        chunk_bytes += additional
    flush()
    return shards


def publish(source=SOURCE, static=STATIC):
    source = Path(source)
    static = Path(static)
    snapshot = json.loads(source.read_text(encoding='utf-8'))

    arrays = {}
    for key in ('projects', 'powPeers', 'summaryPeerGroups', 'hgabPowResults', 'costUnitHgabResults'):
        values = snapshot.pop(key, [])
        arrays[key] = split_array(key, values, static)
        snapshot[f'{key[:-1] if key.endswith("s") else key}Count'] = len(values)

    snapshot['arrayShards'] = arrays
    snapshot['splitFormatVersion'] = 2
    index_payload = (json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    if len(index_payload) >= 5_000_000:
        raise ValueError(f'DPWH index should remain small; got {len(index_payload)} bytes')
    # Publish the index last so it never refers to shards that have not been written.
    atomic_bytes(static / 'dpwh-in-depth-data.json', index_payload)

    retained = {entry['path'].split('/')[-1] for group in arrays.values() for entry in group}
    shard_dir = static / SHARD_DIR
    for old in shard_dir.glob('*.json'):
        if old.name not in retained:
            old.unlink()

    # Remove the old project-only shard directory after the v2 shards are in place.
    old_dir = static / 'dpwh-in-depth-projects'
    if old_dir.exists():
        for old in old_dir.glob('part-*.json'):
            old.unlink()
        try:
            old_dir.rmdir()
        except OSError:
            pass

    return {
        'arrayCounts': {key: sum(shard['itemCount'] for shard in value) for key, value in arrays.items()},
        'indexBytes': len(index_payload),
        'shardCount': sum(len(value) for value in arrays.values()),
        'largestShardBytes': max((shard['sizeBytes'] for value in arrays.values() for shard in value), default=0),
        'publishedFiles': [shard['path'] for value in arrays.values() for shard in value],
    }


if __name__ == '__main__':
    print(json.dumps(publish(), ensure_ascii=False, indent=2))
