#!/usr/bin/env python3
"""Move large workspace files to T5 EVO, retaining verified symlinks and a journal."""
import argparse, hashlib, json, os, shutil, time
from pathlib import Path
DRIVE=Path('/Volumes/T5 EVO')
BASE=DRIVE/'bettergov-research'
REPOS=[Path('/Users/joebertj/nep'),Path('/Users/joebertj/open-data-visualization')]
EXCLUDE={'.git','.agents','.codex','.aws'}
def guard():
    if not os.path.ismount(DRIVE):raise RuntimeError('T5 EVO is not mounted; refusing internal-disk fallback')
    if shutil.disk_usage(DRIVE).free<2_000_000_000:raise RuntimeError('External drive has less than 2 GB free')
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while b:=f.read(8*1024*1024):h.update(b)
    return h.hexdigest()
def move_file(src,dst,journal):
    guard();before=src.stat();dst.parent.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(DRIVE).free<before.st_size+2_000_000_000:raise RuntimeError('Insufficient external space')
    part=dst.with_name(dst.name+'.moving')
    if dst.exists():
        if digest(src)!=digest(dst):raise RuntimeError(f'Destination differs: {dst}')
    else:
        shutil.copy2(src,part)
        if digest(src)!=digest(part):raise RuntimeError(f'Checksum differs: {src}')
        part.replace(dst)
    after=src.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise RuntimeError(f'File changed during copy: {src}')
    guard();link=src.with_name(src.name+'.external-link')
    link.symlink_to(dst);os.replace(link,src)
    with journal.open('a') as f:f.write(json.dumps({'source':str(src),'destination':str(dst),'bytes':before.st_size,'sha256':digest(dst),'time':time.time()})+'\n')
    print(json.dumps({'moved':str(src),'bytes':before.st_size}),flush=True)
def migrate_cache():
    guard();src=REPOS[0]/'data_sources/dpwh_project_documents';dst=BASE/'nep/data_sources/dpwh_project_documents'
    if src.is_symlink():
        if src.resolve()!=dst:raise RuntimeError('Existing cache link points elsewhere')
        return
    dst.mkdir(parents=True,exist_ok=True)
    journal=BASE/'migration.jsonl'
    # Cache is moved before any background writer starts.
    for root,dirs,files in os.walk(src):
        for name in files:
            p=Path(root)/name
            if p.is_symlink():raise RuntimeError('Unexpected cache symlink')
            move_file(p,dst/p.relative_to(src),journal)
    # Files now have external links; remove only these links and empty directories.
    for root,dirs,files in os.walk(src,topdown=False):
        for name in files:
            p=Path(root)/name
            if not p.is_symlink():raise RuntimeError('Cache changed during migration')
            p.unlink()
        Path(root).rmdir()
    src.symlink_to(dst,target_is_directory=True)
    print('Document cache linked to '+str(dst),flush=True)
def migrate_large():
    guard();journal=BASE/'migration.jsonl';total=0;count=0
    for repo in REPOS:
        for root,dirs,files in os.walk(repo,followlinks=False):
            dirs[:]=[d for d in dirs if d not in EXCLUDE and not (Path(root)/d).is_symlink()]
            for name in files:
                p=Path(root)/name
                if p.is_symlink() or not p.is_file():continue
                size=p.stat().st_size
                if size>=100_000_000:
                    move_file(p,BASE/repo.name/p.relative_to(repo),journal);total+=size;count+=1
    print(json.dumps({'complete':True,'files':count,'bytesFreed':total}),flush=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['cache','large']);args=parser.parse_args()
    migrate_cache() if args.action=='cache' else migrate_large()
