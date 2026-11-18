# Crossroads — Continuous Playback Files

Long recordings of the Crossroads episodes, split into chunks of about
2 hours each, so playback keeps going when a phone screen turns off.

## Why these exist

On a phone, a web page's JavaScript stops when the screen turns off, so
the normal player can't load the next episode when one ends — playback
stops at the end of the episode. Spotify doesn't have this problem because
it's a native app. These files work around it: one file plays for ~2 hours
with no JavaScript needed at episode boundaries, so the phone just keeps
playing it. The player still shows the right episode title on the lock
screen as each episode starts inside a chunk (see `chunks.json`).

- All chunks are 44.1 kHz stereo MP3, 96 kbps (Episode 8's master was
  48 kHz — resampling here fixes that quirk inside the chunks).
- `chunks.json` is the manifest: per chunk, the file, season, part,
  episode numbers, titles, the second offset where each episode starts,
  and the chunk duration.
- The players fetch `chunks.json` every 5 minutes and pick up a rebuilt
  chunk list without a refresh, without interrupting playback.

## Files

- `continuous-s1-part1.mp3` … `continuous-s1-part4.mp3` — Season 1,
  Episodes 1–21 (~7 h 23 m total)
- `continuous-s2-part1.mp3` — Season 2, Episodes 22–25 (~2 h 06 m)

## When a new episode lands — REBUILD RULE (read this first)

1. Rebuild ONLY the last chunk of that episode's season, appending the
   new episode to the end of it. Never re-split or rebuild earlier
   chunks, and never change the episode order inside an existing chunk.
   Open player pages rely on the start offsets of already-published
   content staying the same.
2. If the rebuilt last chunk would pass ~95 MB (~7,900 s at 96 kbps),
   split it instead: keep the old chunk as-is and put the new
   episode(s) in a NEW part file (next part number). Never shrink the
   bitrate of an existing chunk.
3. Regenerate `chunks.json` from the rebuilt chunk(s) and update the
   embedded chunk list in the three player pages (Season 1 page, Season 2
   page, and the combined page via `player-deploy-all/build_combined.py`).
   The players' 5-minute `chunks.json` poll picks up the new list on its
   own, but the embedded list is what a freshly loaded page uses.
4. Rebuild command (from `~/workspace/crossroads`):
   `python3 /tmp/build_chunks.py` — it re-encodes only missing chunks
   and rewrites `chunks.json`. Verify each rebuilt chunk (duration,
   size, 44.1 kHz) and spot-transcribe its first 30 seconds before
   pushing.
