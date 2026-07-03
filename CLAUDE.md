# Viscera Cleanup Detail project conventions

This file is the source of truth for code-quality standards across the Viscera
Cleanup Detail Archipelago project: the apworld Python (`VCD_AP/apworld/`), the
`VCArchipelago` UnrealScript mod (`.uc`), and, later, a tracker pack. The
`code-reviewer` subagent enforces these rules. A `Stop` hook makes that review
run automatically before any turn that changed apworld Python or mod source
finishes.

`V1_PLAN.md` holds the design and the current build state. Read it before
starting work. `NEXT_APWORLD_PLAYBOOK.md` holds the process and the Unreal mod
patterns (Appendix B is UE3/UDK).

## How review works

- `.claude/agents/code-reviewer.md` is a read-only reviewer. It reads the diff,
  checks it against this file, and returns findings with a `file:line` and a
  severity. It never edits code.
- The `Stop` hook fires the reviewer whenever a turn touched `VCD_AP/apworld/*.py`
  or `VCD_AP/mod/**/*.uc`. Address blockers before committing.
- Other agents and workflows can call the reviewer directly via
  `subagent_type: code-reviewer` (Agent tool) or `agentType: 'code-reviewer'`
  (Workflow), so a verify stage reuses the same standards.

## House style (all code)

- No em dashes anywhere: code, comments, commit messages. Restructure with
  periods, parentheses, or hyphens.
- Comments are present-tense only. No historical or changelog narration, no
  external references (playtester names, issue numbers, log lines, plan paths,
  commit SHAs). Default to a terse one-liner. Two to three lines only when the
  comment is load-bearing.
- Spell domain terms in full in identifiers. Never abbreviate, for example never
  `punch` for punchout when the full name fits. To save horizontal room, widen
  whitespace rather than truncate a name.
- Never name the user in code: not in comments, log lines, identifiers, or
  example strings. Use the in-game janitor or a slot lookup instead.
- Match the surrounding code: comment density, naming, and idiom.

## Commit messages

- Short sentences ending in full stops. Do not chain clauses with semicolons.
- Err shorter. Stay at or under 100 words even for a large feature. No body.
- No AI attribution. Never add `Co-Authored-By: Claude` or similar.
- Do not write the user's name into the message. The author field carries
  identity; the message describes the change.
- Commit directly to `main`. Do not create a feature branch first. Do not push
  unless asked.

## apworld Python: AP-framework invariants

The reviewer treats a violation of any of these as a correctness blocker.

- Only progression items are guaranteed reachable by the generator. Logic must
  not gate access on a non-progression item.
- The 26 level-access unlock items are progression. Every per-level check
  (milestone ladder, speedrun, punch-out, that level's collectibles and Bob
  note) requires only that level's access item: a single predicate
  `has(Access(level))`. The ONLY exceptions are the two Digsite Bob events
  (Open the Digsite Gates, Find Bob) and the Red Keycard collectible (it sits
  behind those gates), which additionally require the six note-level access
  items (the pedestal needs all nine notes; three are Office freebies).
- `completion_condition` is a solvability contract and switches on the `goal`
  option. Treat edits to it as high-risk. Named count-based traps:
  - `find_bob` resolves to the Find Bob location, whose rule carries the six
    note levels plus the Digsite. Those access items must be progression and
    reachable, or the goal is unsolvable.
  - `collect_collectibles` with amount N requires access to the levels that hold
    N collectibles; the amount is clamped to the 39 that exist.
- The collectible and Bob tables in `collectibles.py` are transcribed from game
  data (map name tables, punchout handlers, `GP_Notes_Arch`); do not hand-guess
  entries. The Doom Armour and Shotgun are an Office stash, not locations.
- Item classification lives in `create_item`: level-access items are progression,
  trap items are `ItemClassification.trap`, useful supply items are
  `ItemClassification.useful`, the rest is filler. No tool-gating. Traps and
  supplies are never progression and never required by logic; the
  `trap_percentage` (default 5) and `useful_percentage` (default 15) options
  convert shares of filler slots, traps first.
- Traps and useful supply drops travel client to mod via
  `Saves\VCArchipelagoTraps.sav` (SeedTag, BaselineIndex, and a full
  "index:Type" queue keyed by received-item position). The mod stores the last
  applied index in its config state, applies one entry per poll, only in
  cleanable levels, and never replays another seed's queue or a pre-connect
  backlog. A trap must never softlock, block a required check, or corrupt a
  save. Supply drops reuse the game's own dispenser spawns (a plain VCBucket or
  VCBin) so they score exactly like vended equipment.
- Game logic lives in one boolean-predicate access-rule module. Read changes
  there as logic, not plumbing.
- The apworld is hand-maintained. There is no generator and no `data/*.yaml`
  source. Every `.py` under `apworld/` is owned source you edit directly.
  `build_apworld.py` only packages. Derive the level table from the game's
  `VCProviders*.ini`, do not hand-guess map names.
- Pinned to Archipelago 0.6.7. `CommonContext` has no `update_tags()`; follow the
  ConnectUpdate pattern if a tag is needed.

## Game and mod facts (confirmed, treat as frozen contracts)

The install that runs is `D:\SteamLibrary\steamapps\common\Viscera` (UDK, engine
build 10907, exe `UDK.exe`). Never bake this path as a default; players set their
own. Decompiled game source (UE Explorer) is the reference for game internals;
re-decompile packages as needed (`NEXT_APWORLD_PLAYBOOK.md` Appendix B.1).

- Custom UnrealScript compiles and runs: the game is uncooked (no `CookedPC`),
  loads script listed in `[Engine.ScriptPackages] +NonNativePackages=`, and
  compiles what is in `[UnrealEd.EditorEngine] +EditPackages=`. Add a package to
  both.
- The mod enters through a GameInfo subclass of `VisceraGame.VCGame`. The class
  the game uses comes from the map-launch URL `?Game=`, which is set from the
  `GameClass` field of a `VCUIDataProvider_GameInfo` entry in `VCProviders.ini`,
  not from `DefaultGame`. The Archipelago mode is its own provider entry so it
  never touches the stock game or its saves.
- Live cleanliness is the game's own value:
  `clean = 1 - VCPunchoutHandler_General.FinalPenalty / StartingCleanupScore`.
  Refresh `FinalPenalty` by calling `PunchoutHandler.ProcessMapState(self, None)`
  on a timer, then read the two floats. `PunchoutHandler` is an inherited public
  var on `VCGameBase`; every per-map handler extends `VCPunchoutHandler_General`.
  Do NOT call `CalculateResults` live: it replicates results and triggers the
  end-of-level UI.
- Prefer calling the game's own functions over reimplementing them. Read the
  decompiled source first to know which are free of side effects.
- Detection cross-checks from save files (read-only): `GlobalStatsData.sav` is
  best-ever and global, so baseline at connect and watch for increases;
  `TrophyDataCollective.sav` holds Office collectibles and EotM frames.

## The mod / client boundary (confirmed by spike, treat as frozen)

- Mod to client: the mod writes state to `UDKGame\Config\UDKVCArchipelago.ini`
  via `SaveConfig()` on a `config(VCArchipelago)` object, only when state changes.
  The client polls that file (about one second latency). The game log is NOT a
  data channel: it buffers to disk every 20 to 30 seconds. A
  `DefaultVCArchipelago.ini` registers the config base. Write the FULL state
  (checked set, current percent, goal flag), not deltas, so a client reconnect
  recovers from the file.
- Archipelago is a game MODE, not a title. A dedicated title is not feasible
  script-only (the `Switch game` menu titles are hardcoded UI and
  `IsValidGameTitle` is a hardcoded static). The mode is a
  `VCUIDataProvider_GameInfo` entry (GameClass `VCArchipelago.VCGame_Archipelago`,
  `ValidTitles=Viscera`, a FriendlyName) that the data-driven Start Work menu
  shows next to Cleanup and Speedrun.
- Client to mod: the client writes the unlocked-level set (and other granted
  state) to a config ini the mod reads. Level gating is IN-ENGINE: the mod
  refuses to start a level not in that set. Do not gate by rewriting the shared
  `VCProviders.ini` map list.
- Office and save isolation is client-side: on AP connect, back up the whole
  `Saves\` directory and swap in a fresh (or per-seed) Office; restore the
  player's saves on disconnect. AP needs a fresh Office so collectibles, the
  Employee-of-the-Month frames, and the cross-level Bob-note chain accumulate
  cleanly without touching the player's normal career.

Standing rules:
- Recover outbound checks and goal completion on reconnect from the framework's
  own state (checked-locations set, finished flag) plus the mod re-emitting its
  full state, never from in-memory-only bookkeeping.
- The cleanliness probe is a timer: skip the Office and menu maps
  (`VCMapInfo.bIsOfficeLevel`) and throttle or event-drive the full mess scan for
  production. Prefer event-driven checks where the game gives an event.
- Player-facing client messages use the `Client` logger, or they are invisible in
  the AP client window.

## apworld Python: lint and tests

- Every change to apworld Python conforms to Archipelago lint and style (flake8
  reads `setup.cfg`), unprompted.
- Every change adds or updates `WorldTestBase` tests for the changed behavior,
  unprompted.
- The pre-commit gate (`VCD_AP/.pre-commit-config.yaml`) runs hygiene, flake8,
  and the world tests on changed `apworld/*.py`. Tests run via
  `VCD_AP/run_world_tests.py`, which uses the sibling Archipelago checkout
  (override with `AP_ROOT`, default `..\Archipelago`).
- Run the fill fuzzer across many seeds before trusting the default of one open
  starting level.
