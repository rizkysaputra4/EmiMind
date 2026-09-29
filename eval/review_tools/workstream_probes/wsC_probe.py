import collections, json, random, re, sys, time
sys.path.insert(0, r"C:\Users\rizky\Documents\Code\EmiMind")
from services.mcp.periods import resolve_fiscal_period, _resolve_from_filename_tokens
SP = sys.argv[1]
names = [l.strip() for l in open(f"{SP}/wsC_names.txt", encoding="utf-8") if l.strip()]
t0 = time.time()
src = collections.Counter(); conflicts = []; errors = []; res = {}
for n in names:
    try:
        r = resolve_fiscal_period(n)
    except Exception as e:
        errors.append((n, repr(e))); continue
    if r is None:
        src["None"] += 1; continue
    src[r.source] += 1
    res[n] = r
    if r.conflict:
        conflicts.append((n, r.fiscal_period, r.conflicting_period))
print("total", len(names), "secs", round(time.time()-t0, 1))
print("by source", dict(src))
print("errors", len(errors), errors[:3])
print("conflicts", len(conflicts))
yr = sum(1 for c in conflicts if c[1][:4] != c[2][:4])
print("  year-differs", yr, "quarter-only", len(conflicts) - yr)
rng = random.Random(11)
print("--- 20 random conflicts")
for c in rng.sample(conflicts, 20): print("  ", c)
print("--- 20 random resolved (non-conflict)")
ok = [(n, r.fiscal_period, r.source) for n, r in res.items() if not r.conflict]
for c in rng.sample(ok, 20): print("  ", c)
# no-prefix names
print("--- non-prefix names")
for n in names:
    if not re.match(r"^[A-Za-z0-9]+_\d{4}_(TW1|TW2|TW3|AUDIT|ANNUAL)_", n, re.I):
        r = res.get(n); print("  ", n, r.fiscal_period if r else None, r.source if r else "")
# remainder-only resolution stats (how the free parser does on the remainders alone)
pre = re.compile(r"^[A-Za-z0-9]+_\d{4}_[A-Z0-9]+_[A-Z0-9]+_", re.I)
cmp = collections.Counter()
for n in names:
    m = pre.match(n)
    if not m: continue
    t = _resolve_from_filename_tokens(n[m.end():])
    r = res.get(n)
    cmp["remainder_unresolved" if t is None else ("agree" if r and t.fiscal_period == r.fiscal_period else "disagree")] += 1
print("remainder free-parse vs prefix", dict(cmp))
json.dump(conflicts, open(f"{SP}/wsC_conflicts.json", "w"), indent=0)
