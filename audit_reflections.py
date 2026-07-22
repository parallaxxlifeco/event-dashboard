#!/usr/bin/env python3
"""
GIVE IT ALL — Reflection backfill audit.

Finds members who are tagged `profile-complete` but have NO `latest_reflection`
on their GHL contact — i.e. they finished their deep profile but were never sent
their AI reflection (the reflections paused June 25 -> July 21 2026 when Make ran
out of credits, and Make drops webhooks when out of ops, so those never recover
on their own).

Run it from the GHL-Dashboard folder (it reuses secrets.json):
    cd "~/Documents/Claude Code/GHL-Dashboard"
    python3 audit_reflections.py

Read-only. It writes nothing to GHL. It just prints who needs a manual re-send.
"""
import json, os, time, urllib.request, urllib.error
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SECRETS = json.load(open(os.path.join(HERE, "secrets.json")))
TOKEN = SECRETS["api_token"]
LOC = SECRETS["location_id"]
VER = "2021-07-28"
SEARCH = "https://services.leadconnectorhq.com/contacts/search"
CFDEF = f"https://services.leadconnectorhq.com/locations/{LOC}/customFields"

# Reflection outage window (Make credit exhaustion). Anyone who completed their
# profile in this window did NOT get a reflection generated.
OUTAGE_START = "2026-06-25"
OUTAGE_END = "2026-07-21"

def H():
    return {"Authorization": f"Bearer {TOKEN}", "Version": VER,
            "Content-Type": "application/json", "Accept": "application/json",
            "User-Agent": "Mozilla/5.0"}

def req(url, method="GET", body=None):
    r = urllib.request.Request(url, method=method, headers=H(),
                               data=(json.dumps(body).encode() if body else None))
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read().decode())

# field id -> bare key
id2key = {}
for f in (req(CFDEF).get("customFields") or []):
    k = str(f.get("fieldKey") or f.get("name") or "").split(".")[-1].strip().lower()
    if f.get("id") and k:
        id2key[f["id"]] = k

def custom(c):
    out = {}
    for cf in (c.get("customFields") or []):
        if not isinstance(cf, dict):
            continue
        key = str(cf.get("key") or "").split(".")[-1].strip().lower() or id2key.get(cf.get("id"), "")
        if not key:
            continue
        v = cf.get("value")
        if v is None:
            v = cf.get("field_value")
        if isinstance(v, list):
            v = ", ".join(str(x) for x in v)
        out[key] = "" if v is None else str(v)
    return out

def search(tag):
    res, page, seen = [], 1, set()
    while True:
        p = req(SEARCH, "POST", {"locationId": LOC, "pageLimit": 100, "page": page,
                "filters": [{"field": "tags", "operator": "contains", "value": tag}]})
        items = p.get("contacts") or []
        for c in items:
            if c.get("id") in seen:
                continue
            seen.add(c.get("id"))
            res.append(c)
        if not items or len(items) < 100:
            break
        page += 1
        if page > 50:
            break
        time.sleep(0.2)
    return res

pc = search("profile-complete")
rows = []
for c in pc:
    cf = custom(c)
    fn, ln = (c.get("firstName") or "").strip(), (c.get("lastName") or "").strip()
    name = (c.get("contactName") or (fn + " " + ln)).strip()
    tags = [t.lower() for t in (c.get("tags") or [])]
    refl = (cf.get("latest_reflection") or "").strip()
    done = (cf.get("profile_completed_at") or "").strip()
    rows.append({
        "name": name, "email": (c.get("email") or "").strip().lower(),
        "id": c.get("id"),
        "completed_at": done, "added": (c.get("dateAdded") or "")[:10],
        "has_refl": len(refl) > 20,
        "attending": "attending-next-event" in tags,
    })

rows.sort(key=lambda r: (r["completed_at"] or r["added"] or ""))
missing = [r for r in rows if not r["has_refl"]]

print(f"\nprofile-complete contacts: {len(rows)}   |   missing a reflection: {len(missing)}\n")
print("MEMBERS TAGGED profile-complete BUT WITH NO latest_reflection")
print("(these are the people to re-send — resubmit their profile or replay the webhook)\n")
print(f"{'completed/added':16} {'attending #16':13} {'name':26} email")
print("-" * 90)
for r in missing:
    when = r["completed_at"][:10] if r["completed_at"] else ("~" + r["added"] if r["added"] else "—")
    print(f"{when:16} {('YES' if r['attending'] else ''):13} {r['name'][:26]:26} {r['email']}")

gap = [r for r in missing if OUTAGE_START <= (r["completed_at"][:10] if r["completed_at"] else r["added"]) <= OUTAGE_END]
if gap:
    print(f"\nOf those, {len(gap)} completed during the outage window "
          f"({OUTAGE_START} to {OUTAGE_END}) — the clearest credit-pause casualties.")
print()
