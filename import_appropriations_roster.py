#!/usr/bin/env python3
"""Recover only numbered/date-bearing roster facts from official indexed pages."""
import json
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
DATA=ROOT/'analysis_output'

def build():
    source=json.loads((DATA/'appropriations_indexed_sources.json').read_text())
    members={}
    for snapshot in source:
        for block in snapshot['text'].split('--------------------------------------------------------------------------------'):
            url=re.search(r'^Committees .*?\((https://[^\s)]+)\)',block.strip())
            if not url or '/committee/view/0504' not in url[1]:continue
            for m in re.finditer(r'(?:^|\n)(\d+)\.\s*(.+?)\s*\(Date Elected: (\d{4}-\d{2}-\d{2})\)',block):
                num=int(m[1]); name=m[2].strip()
                role='Chairperson' if num==1 else 'Sr. Vice-Chairperson' if num==2 else 'Vice-Chairperson' if num<=58 else 'Member for the Majority' if num<125 else 'Member for the Minority'
                member={'number':num,'officialName':name,'role':role,'elected':m[3],'source':url[1]}
                if num in members and members[num]['officialName']!=name:
                    # Different official spelling variants require review;
                    # preserve both observations without duplicate people.
                    member['otherObservedNames']=list(set([members[num]['officialName'],*members[num].get('otherObservedNames',[])]))
                members[num]=member
    document={'source':'https://www.congress.gov.ph/committees/committee/view/0504','asOf':'2026-10-11','dateBasis':'Indexed official roster retrieved on this date; not a certified historical snapshot of the reading date.',
              'complete':False,'expectedNumberedMembers':136,'missingNumbers':sorted(set(range(1,137))-set(members)),
              'members':[members[n] for n in sorted(members)]}
    (DATA/'appropriations_roster_raw.json').write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n')
    print('Recovered:',len(members),'Missing:',document['missingNumbers'])
if __name__=='__main__':build()
