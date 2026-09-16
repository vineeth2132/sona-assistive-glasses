# Working on Sona together

Small team, few days, one demo: `main` must always run. Everything else is lightweight.

## The loop
1. `git pull --rebase origin main`, then branch: `git switch -c feat/short-name` (or `fix/…`).
2. Commit small and often. Message = what changed and why, one line is fine.
3. Before opening the PR: `.venv/bin/ruff check sona scripts && .venv/bin/python scripts/selftest.py`.
4. Open a pull request on GitHub. Say what you tested and *how* (with the array? mock? wav replay?).
5. CI runs lint + the hardware-free selftests. Green + one teammate's OK (or your own if nobody is
   awake and it's small) → **Squash and merge**, delete the branch.
6. Tiny hotfixes during a demo rehearsal: push straight to `main`, tell the group.

## Testing without hardware
- `python -m sona.app --wav sona_stt/whisper.cpp/samples/jfk.wav` replays audio; the mirror at
  http://localhost:8765 shows exactly what the glasses would render.
- `scripts/selftest.py --quick` runs the pure-Python tests (what CI runs);
  without `--quick` it also exercises YAMNet, whisper and the speaker model.

## Don'ts
- Don't commit models, whisper.cpp, `.venv`, or anything in `out/` (settings, voice profiles).
  They're gitignored — the setup scripts recreate them.
- Don't run two instances of the app at once: the second fails with "port 8765 in use".
- Keep `sona/config.py` edits minimal and commented; it's where merge conflicts happen.

## Where things live
`sona/` app · `scripts/` tools · `pi/` Raspberry Pi provisioning + hardware playbook ·
`firmware/`, `tools/` ReSpeaker flashing/control kit (Seeed's files fetched, not committed) · `models/` downloaded models (ignored).
