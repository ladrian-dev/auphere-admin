import subprocess,sys,time,re
root=int(sys.argv[1]); pat=re.compile(r'chrome-devtools-mcp|@playwright/mcp|higgsfield|mcp-server')
best=0; best_names=set()
for _ in range(400):
    try: out=subprocess.run(['ps','-Ao','pid,ppid,command'],capture_output=True,text=True).stdout
    except Exception: break
    kids={}; cmd={}
    for line in out.splitlines()[1:]:
        p=line.split(None,2)
        if len(p)<3: continue
        pid,ppid,c=int(p[0]),int(p[1]),p[2]
        kids.setdefault(ppid,[]).append(pid); cmd[pid]=c
    if root not in cmd: break
    seen=set(); stack=[root]
    while stack:
        x=stack.pop()
        if x in seen: continue
        seen.add(x); stack.extend(kids.get(x,[]))
    hits={cmd[p][:70] for p in seen if p in cmd and pat.search(cmd[p])}
    if len(hits)>best: best=len(hits); best_names=hits
    time.sleep(0.25)
print(best)
for n in sorted(best_names): print("   ",n)
