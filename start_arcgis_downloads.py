#!/usr/bin/env python3
"""Persistent queue for selected JSON downloads; at most two active workers."""
import argparse
import fcntl
import os
import signal
import subprocess
import sys
import time
import json
from pathlib import Path
from download_arcgis_inventory import ARCHIVE,ROOT,now,read,write

SELECTIONS=ROOT/'data_sources/arcgis_dpwh/selections.json'

def jobs():
    records=read(SELECTIONS)['downloads']
    result=[(r['profile'],r['script']) for r in records]
    if len({r[0] for r in result})!=len(result):raise ValueError('Duplicate download profile')
    for profile,script in result:
        if not profile.replace('_','').isalnum() or Path(script).name!=script or not script.startswith('download_') or not (ROOT/script).is_file():
            raise ValueError('Invalid selected downloader')
    return result


def directory(profile):return ARCHIVE if profile=='catalog' else ARCHIVE/'selected'/profile

def process(pid,script):
    # Avoid shelling out to `ps`: some managed runtimes deny subprocess
    # inspection even though starting the worker itself is allowed. PID files
    # are written only after this scheduler starts the named local script.
    try:os.kill(pid,0)
    except ProcessLookupError:return False
    except PermissionError:return True
    return True

def active(root,script):
    path=root/'worker.pid'
    if not path.exists():return None
    pid=int(path.read_text());return pid if process(pid,script) else None

def completed(root):
    path=root/'status.json'
    return path.exists() and bool(read(path).get('finishedAt'))

def launch(profile,script):
    root=directory(profile);root.mkdir(parents=True,exist_ok=True)
    with (root/'worker.log').open('a') as log:
        child=subprocess.Popen([sys.executable,'-u',str(ROOT/script),*(['all'] if profile=='catalog' else []),'--delay','3','--batch-size','200'],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    (root/'worker.pid').write_text(str(child.pid)+'\n')
    print(now(),'Started',profile,'PID',child.pid,flush=True)
    return child

def stop_workers():
    pending=[]
    for profile,script in jobs():
        pid=active(directory(profile),script)
        if pid:os.kill(pid,signal.SIGINT);pending.append((pid,script))
    for _ in range(50):
        if not any(process(pid,script) for pid,script in pending):return
        time.sleep(.2)
    raise RuntimeError('A downloader is still stopping; rerun shortly. No process was force-killed.')

def supervise():
    ARCHIVE.mkdir(parents=True,exist_ok=True)
    with (ARCHIVE/'scheduler.lock').open('a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        (ARCHIVE/'scheduler.pid').write_text(str(os.getpid())+'\n')
        children={};attempted=set();failures={}
        while True:
            for profile,child in list(children.items()):
                code=child.poll()
                if code is not None:
                    if code:failures[profile]=f'Worker exited {code}; inspect worker.log'
                    del children[profile]
            running={profile:active(directory(profile),script) for profile,script in jobs()}
            running={k:v for k,v in running.items() if v}
            running.update({k:v.pid for k,v in children.items()})
            for profile,script in jobs():
                if len(running)>=2:break
                root=directory(profile)
                if profile in running or completed(root) or profile in attempted:continue
                child=launch(profile,script);children[profile]=child;attempted.add(profile);running[profile]=child.pid
            queued=[profile for profile,script in jobs() if profile not in running and not completed(directory(profile)) and profile not in attempted]
            report={'updatedAt':now(),'maxActiveDownloads':2,'running':running,'queued':queued,
                'finished':[profile for profile,_ in jobs() if completed(directory(profile))], 'workerFailures':failures,
                'note':'Layer-level failed/unavailable records remain in each profile status.json; finished does not guarantee every endpoint was accessible.'}
            write(ARCHIVE/'scheduler-status.json',report)
            if not running and not queued:return
            time.sleep(3)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--foreground',action='store_true');parser.add_argument('--status',action='store_true');parser.add_argument('--reload-queue',action='store_true',help='Restart only the scheduler; active downloads continue')
    parser.add_argument('--restart-bulk',action='store_true',help='Gracefully checkpoint existing workers before adopting the two-worker queue')
    parser.add_argument('--include-bulk',action='store_true',help='Compatibility option; catalog is already included last')
    args=parser.parse_args()
    if args.status:
        path=ARCHIVE/'scheduler-status.json';print(json.dumps(read(path) if path.exists() else {},indent=2));return
    if args.foreground:supervise();return
    path=ARCHIVE/'scheduler.pid'
    if path.exists() and process(int(path.read_text()),'start_arcgis_downloads.py'):
        if not args.reload_queue:
            print('Scheduler already running; selections reload automatically.');return
        pid=int(path.read_text());os.kill(pid,signal.SIGTERM)
        for _ in range(25):
            if not process(pid,'start_arcgis_downloads.py'):break
            time.sleep(.2)
        if process(pid,'start_arcgis_downloads.py'):raise RuntimeError('Scheduler is still stopping')
    if args.restart_bulk:stop_workers()
    ARCHIVE.mkdir(parents=True,exist_ok=True)
    with (ARCHIVE/'scheduler.log').open('a') as log:
        child=subprocess.Popen([sys.executable,'-u',str(ROOT/'start_arcgis_downloads.py'),'--foreground'],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    path.write_text(str(child.pid)+'\n');print('Started two-worker queue; scheduler PID:',child.pid)

if __name__=='__main__':main()
