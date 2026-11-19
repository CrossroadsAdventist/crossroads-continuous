#!/usr/bin/env python3
"""Build continuous ~2h chunk MP3s from the player deploy episode files.
Resample everything to 44.1 kHz (fixes Ep8's 48 kHz), concat in episode
order, encode libmp3lame 96k stereo. Chunks <= 7200 s. Writes chunks.json
manifest with per-episode start offsets (cumulative source durations).
Kept in this repo so the rebuild is versioned with the chunks; see
README.md for the rebuild rule (append-only: only the last chunk of a
season is rebuilt when a new episode lands). Run from anywhere:
  python3 build_chunks.py
Already-built chunks are skipped (checked by file existence), so a
re-run only encodes what's new."""
import json, pathlib, subprocess, sys, hashlib

BASE = pathlib.Path("/home/hatch/workspace/crossroads")
OUT = BASE / "player-deploy-continuous"
OUT.mkdir(parents=True, exist_ok=True)
MAX_S = 7200.0

def dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(p)], capture_output=True, text=True, check=True)
    return float(r.stdout.strip())

def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def fmt(s):
    s = int(round(s)); return f"{s//3600}:{(s%3600)//60:02d}:{s%60:02d}"

seasons = {}
for season, dep in [("s1", "player-deploy-s1"), ("s2", "player-deploy-s2")]:
    eps = json.loads((BASE / dep / "episodes.json").read_text())
    items = []
    for e in eps:
        p = BASE / dep / e["file"]
        items.append({"n": e["n"], "title": e["title"], "file": str(p), "dur": dur(p)})
    seasons[season] = items

manifest = []
for season in ["s1", "s2"]:
    items = seasons[season]
    # greedy split into <= MAX_S chunks, never splitting an episode
    chunks, cur, cur_d = [], [], 0.0
    for it in items:
        if cur and cur_d + it["dur"] > MAX_S:
            chunks.append(cur); cur, cur_d = [], 0.0
        cur.append(it); cur_d += it["dur"]
    if cur: chunks.append(cur)
    # Ep25 note: a season that splits into exactly 2 chunks stays ONE chunk
    # if the combined total is <= 7900 s (~95 MB at 96k) — keeps S2 (22-25,
    # 7577 s, ~91 MB) as a single file instead of a 1h44m + 22m split.
    if len(chunks) == 2 and sum(sum(it["dur"] for it in ch) for ch in chunks) <= 7900.0:
        chunks = [chunks[0] + chunks[1]]
    # APPEND-ONLY (Ep27): never re-split existing chunks. If chunks.json
    # exists, keep its episode sets exactly; new episodes join the last
    # chunk only if the rebuilt total stays <= 7900 s (~95 MB), else they
    # become a new part file. Chunks whose episode set changed are
    # re-encoded (the file-exists skip must not serve stale audio).
    rebuild = set()
    mf = OUT / "chunks.json"
    if mf.exists():
        ex = [c for c in json.loads(mf.read_text()) if c["season"] == season]
        if ex:
            pinned = [[it for it in items if it["n"] in c["episodes"]] for c in ex]
            seen = {it["n"] for ch in pinned for it in ch}
            new = [it for it in items if it["n"] not in seen]
            if new:
                # Greedy fill (batch chain, 2026-11-19): episodes join the
                # last chunk one at a time while the rebuilt total stays
                # <= 7900 s; the first episode that would overflow starts
                # a new part file (and later episodes fill that one).
                for it in new:
                    last = pinned[-1]
                    if sum(x["dur"] for x in last) + it["dur"] <= 7900.0:
                        last.append(it)
                    else:
                        pinned.append([it])
            for j, ch in enumerate(pinned, 1):
                old = ex[j - 1] if j - 1 < len(ex) else None
                if old is None or [it["n"] for it in ch] != old["episodes"]:
                    rebuild.add(f"continuous-{season}-part{j}.mp3")
            chunks = pinned
    for i, ch in enumerate(chunks, 1):
        name = f"continuous-{season}-part{i}.mp3"
        out = OUT / name
        lst = OUT / f"_concat_{season}_part{i}.txt"
        lst.write_text("".join(f"file '{it['file']}'\n" for it in ch))
        starts, t = [], 0.0
        for it in ch:
            starts.append(round(t, 2)); t += it["dur"]
        total = t
        print(f"== {name}: eps {[it['n'] for it in ch]} total {fmt(total)} ({total:.1f}s)", flush=True)
        if not out.exists() or name in rebuild:
            r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                                "-i", str(lst), "-ar", "44100", "-ac", "2", "-b:a", "96k",
                                str(out)], capture_output=True, text=True)
            if r.returncode != 0:
                print("FFMPEG FAILED", name, r.stderr[-2000:]); sys.exit(1)
        ad = dur(out)
        sr = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate",
                             "-of", "csv=p=0", str(out)], capture_output=True, text=True, check=True).stdout.strip()
        size = out.stat().st_size
        print(f"   built: dur {ad:.1f}s (expect {total:.1f}s, diff {ad-total:+.2f}s) sr={sr} size={size} ({size/1048576:.1f} MB) md5={md5(out)}", flush=True)
        assert sr == "44100", f"sample rate {sr}"
        assert abs(ad - total) < 5.0, f"duration drift {ad-total}"
        assert size < 100 * 1024 * 1024, "over GitHub 100MB limit"
        manifest.append({"file": name, "season": season, "part": i,
                         "episodes": [it["n"] for it in ch],
                         "titles": [it["title"] for it in ch],
                         "starts": starts, "dur": round(ad, 2)})
        lst.unlink()
(OUT / "chunks.json").write_text(json.dumps(manifest, indent=1))
print("== manifest =="); print(json.dumps(manifest, indent=1))
