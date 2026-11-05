"""Per-agent token usage and messaging for one agent-team session.

Usage: python3 .claude/team/usage.py ~/.claude/projects/<project>/<session-id> [--since 2026-10-31T21:20:00Z]
--since counts only entries at or after that UTC time (one session can span several sprints).
--context prints, per agent, where its new context came from: tool-result characters by kind
(shortcut, Agent results, board, source reads, html reports, check/pg, git, other bash). P10.
--cold prints, per agent, the cold-cache calls: a cache write above 20k tokens and above 40% of
the context, i.e. a wake after the sub-agent's 5-minute cache expired. P12 (target < 1.5 per sprint).
Reads <session-id>.jsonl (main session) and <session-id>/subagents/*.jsonl.
"""
import json,sys,glob,os,collections
SINCE=sys.argv[sys.argv.index('--since')+1] if '--since' in sys.argv else ''
def kind(name, cmd):
    if name != 'Bash': return 'shortcut' if 'shortcut' in name else name
    if '.html' in cmd: return 'html reports'
    if 'board.py' in cmd: return 'board'
    if 'check.py' in cmd or 'pg.py' in cmd or 'mutate.py' in cmd: return 'check/pg'
    if any(s in cmd for s in ('backend/', 'wcl_agent/', 'frontend/src')) and any(s in cmd for s in ('sed -n', 'grep', 'cat ')): return 'source reads'
    if 'git ' in cmd: return 'git'
    return 'other bash'
def stats(path):
    inp=cc=cr=out=calls=0; sends=0; sendchars=0; tools=collections.Counter(); seen=set()
    ids={}; ctx=collections.Counter(); cold=[0,0]
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
                w=u.get('cache_creation_input_tokens',0); r=u.get('cache_read_input_tokens',0)
                if w>20000 and w>0.4*(w+r): cold[0]+=1; cold[1]+=w
            for c in m.get('content') or []:
                if isinstance(c,dict) and c.get('type')=='tool_use':
                    tools[c['name']]+=1
                    ids[c.get('id')]=kind(c['name'], (c.get('input') or {}).get('command','') if c['name']=='Bash' else '')
                    if c['name']=='SendMessage':
                        sends+=1; sendchars+=len(json.dumps(c.get('input',{})))
        if d.get('type')=='user' and isinstance(m,dict) and isinstance(m.get('content'),list):
            for c in m['content']:
                if isinstance(c,dict) and c.get('type')=='tool_result':
                    ctx[ids.get(c.get('tool_use_id'),'?')]+=len(json.dumps(c.get('content')))
    return dict(calls=calls,inp=inp,cc=cc,cr=cr,out=out,cold=cold,sends=sends,sendchars=sendchars,tools=tools,ctx=ctx)
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
if '--context' in sys.argv:
    print('\nnew context by kind (tool-result chars, share):')
    for n,s in rows:
        tot=sum(s['ctx'].values()) or 1
        print(f"{str(n)[:40]:40} {tot:8} " + ', '.join(f"{k} {100*v/tot:.0f}%" for k,v in s['ctx'].most_common(5)))
if '--cold' in sys.argv:
    print('\ncold-cache calls (weighted at 1.25x the rewrite):')
    tot=0
    for n,s in rows:
        if s['cold'][0]:
            w=s['cold'][1]*1.25/1e6; tot+=w
            print(f"{str(n)[:40]:40} {s['cold'][0]:3} calls {w:6.2f}")
    print(f"{'TOTAL cold weight':40} {tot:16.2f}")
