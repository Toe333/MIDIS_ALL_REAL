# PHONE HANDOFF — for a fresh Claude in the `work` (phone-synced) tmux session

Written by the desktop Claude 2026-06-17. You are the **phone-synced** Claude. A separate
**desktop** Claude also runs OUTSIDE tmux — don't both edit the same files at once; the
**annotation work below is YOUR lane**. Read this, then do the tasks in order.

## 0. Orient (5 min)
- **`STATE.md`** (project root) = single source of truth. Read CURRENT STATUS + the top
  session-log entry. Short version: the build pipeline is **DONE / vectorized** —
  `SIGNATURES_DATA/signatures_ext.npy` (N×74) + cosine `knn_cosine.pkl`; catalog 459,805×148.
- Memories worth loading: `[[human-annotation-plan]]`, `[[rhythm-is-priority]]`,
  `[[project-state-file]]`, `[[feedback-no-stale-docs]]`, `[[phone-notify-remote-setup]]`.
- The annotation tool spec is **`ANNOTATOR_SPEC.md`** (NinjaStar-8, 8 sliders, 8-bit UI).

## 1. ⚠️ TOP PRIORITY — recover the user's annotations (data at risk)
The user says they "annotated with the other Claude" — but the desktop Claude could **NOT
find any ratings file or annotator app**. Already checked (don't repeat): `_work/`
(no `ninjastar8_ratings.parquet`), project root, parent `/mnt/2FAST/`, `~`, and running
servers (only the old `webplayer` on `:8765`, not a NinjaStar app). So the ratings may be
unsaved or in a non-obvious spot. **Find them before anything else:**
- Check **this tmux session's scrollback / your own shell history** (`history`) for what was
  built/run and any output path.
- `find / -mmin -240 -iname '*ninja*' -o -iname '*rating*' -o -iname '*annot*' 2>/dev/null`
  (and look for any `.csv/.parquet/.json/.db` written in the last few hours).
- Check the **imac** (`ssh t@imac`) — the annotating may have happened there.
- Look for a Flask/Streamlit/http app the previous context wrote (likely under the project
  or `~`), and whatever file it appends to.

**Then:**
- If ratings exist → verify they're **`md5`-keyed** and valid (each row a real catalog md5,
  values in 0–5), and consolidate to **`_work/ninjastar8_ratings.parquet`** (the spec's
  target). Confirm they left-merge onto the catalog by `md5` (un-rated rows = NaN). Do NOT
  write into the catalog directly.
- If NinjaStar-8 was **never actually built / nothing saved** → build it per
  `ANNOTATOR_SPEC.md` (spec is complete: 8 sliders, audio pool = the 109 clips in
  `_stats/audio_sanity_wav/`, output `_work/ninjastar8_ratings.parquet`) and have the user
  re-rate. **Make it append-on-each-rating + resumable** so this can't lose data again.

## 2. Fix STATE.md (the user hates stale docs — see `[[feedback-no-stale-docs]]`)
- **Stale number:** GROUND TRUTH table (~line 79) says `metadata.parquet … (now 76) cols`.
  It's **148** everywhere else. Fix it.
- Once the annotation state is resolved, **add a Session Log entry** (newest first) covering
  what was found/built/saved. NinjaStar-8 is currently logged as "Not yet built" (~line 228)
  — update that to reality.

## 3. Conventions
- Long-running step? Ping the user's phone: `notify-when-done 'PATTERN' 'Label'` (detached)
  or `notify "msg" "title"`. (ntfy → iPhone; see `[[phone-notify-remote-setup]]`.)
- Backups before mutating shared data; non-destructive column adds; verify after.
- After the annotator: the big forward task is **Phase 11 #1 — empty-space hunt** over the
  74-D space (`CODE/27_*`); see STATE.md ROADMAP. But annotations first.
