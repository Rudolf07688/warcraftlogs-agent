"""Per-agent token usage and messaging for one agent-team session.

Usage: python3 .claude/team/usage.py ~/.claude/projects/<project>/<session-id> [--since 2026-10-31T21:20:00Z]
--since counts only entries at or after that UTC time (one session can span several sprints).
Reads <session-id>.jsonl (main session) and <session-id>/subagents/*.jsonl.
"""
import json,sys,glob,os,collections
SINCE=sys.argv[sys.argv.index('--since')+1] if '--since' in sys.argv else ''
def stats(path):
    inp=cc=cr=out=calls=0; sends=0; sendchars=0; tools=collections.Counter(); seen=set()
    for line in open(path):
        try: d=json.loads(line)
        except: continue
        if SINCE and (d.get('timestamp') or '') < SINCE: continue
        m=d.get('message') or {}
        if d.get('type')=='assistant' and isinstance(m,dict):
            mid=m.get('id')
            u=m.get('usage') or {}
            if mid and mid not in seen and u:
                seen.add(mid); calls+=1
                inp+=u.get('input_tokens',0); cc+=u.get('cache_creation_input_tokens',0); cr+=u.get('cache_read_input_tokens',0); out+=u.get('output_tokens',0)
            for c in m.get('content') or []:
                if isinstance(c,dict) and c.get('type')=='tool_use':
                    tools[c['name']]+=1
                    if c['name']=='SendMessage':
                        sends+=1; sendchars+=len(json.dumps(c.get('input',{})))
    return dict(calls=calls,inp=inp,cc=cc,cr=cr,out=out,sends=sends,sendchars=sendchars,tools=tools)
sess=sys.argv[1].rstrip('/').removesuffix('.jsonl')
rows=[]
main=stats(sess+'.jsonl'); rows.append(('main (team-lead)',main))
for f in sorted(glob.glob(sess+'/subagents/*.jsonl')):
    if SINCE and os.path.getmtime(f) < __import__('datetime').datetime.fromisoformat(SINCE.replace('Z','+00:00')).timestamp(): continue
    meta=f.replace('.jsonl','.meta.json'); name=os.path.basename(f)
    try: md=json.load(open(meta)); name=md.get('name') or md.get('description') or name
    except: pass
    rows.append((name,stats(f)))
T=collections.Counter()
print(f"{'agent':40} {'calls':>6} {'out':>8} {'cacheRd':>11} {'cacheWr':>10} {'sends':>6}")
for n,s in rows:
    print(f"{str(n)[:40]:40} {s['calls']:6} {s['out']:8} {s['cr']:11} {s['cc']:10} {s['sends']:6}")
    for k in ('calls','out','cr','cc','inp','sends'): T[k]+=s[k]
print('TOTAL',dict(T))
for n,s in rows: print(n, s['tools'].most_common(6))
