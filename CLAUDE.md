# Viscera Cleanup Detail project conventions

This file is the source of truth for code-quality standards across the Viscera
Cleanup Detail Archipelago project: the apworld Python (`VCD_AP/apworld/`), the
`VCArchipelago` UnrealScript mod (`.uc`), and, later, a tracker pack. The
`code-reviewer` subagent enforces these rules. A `Stop` hook holds open any
turn that changed apworld Python or mod source until the review and the docs
pass have happened.

`V1_PLAN.md` holds the design and the current build state. Read it before
starting work. `NEXT_APWORLD_PLAYBOOK.md` holds the process and the Unreal mod
patterns (Appendix B is UE3/UDK).

## How review works

- `.claude/agents/code-reviewer.md` is a read-only reviewer. It reads the diff,
  checks it against this file, and returns findings with a `file:line` and a
  severity. It never edits code.
- The `Stop` hook (`.claude/settings.json` plus
  `.claude/hooks/check-docs-review.sh`) blocks the first stop of any turn that
  edited `VCD_AP/apworld/*.py` or `VCD_AP/mod/**/*.uc`, with instructions to
  run the reviewer and do the documentation pass. Address blockers before
  committing.
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

## Documentation stays in sync

Before ending any turn that changed the apworld, the mod, or the client, check
whether the docs still match and update them in the same turn, unprompted. The
reviewer treats a missed update as a blocker.

- Player docs live in `VCD_AP/docs`: `PLAYER_SETUP.md` (install and first
  run), `RELEASE_NOTES.md` (the Discord-sized summary of the LATEST build
  only, hard cap 2000 characters INCLUDING the GitHub release link it must
  end with), and `RELEASE_NOTES_FULL.md` (the unlimited dated build log,
  newest entry first, used as the GitHub release body).
- A docs pass is required for every player-visible change: options and their
  defaults, checks and goals, client commands and messages, the install and
  connect flow, save isolation, traps and supply drops. Internal refactors
  need none.
- A player-visible change adds a dated entry to `RELEASE_NOTES_FULL.md` (or
  extends today's), and rewrites `RELEASE_NOTES.md` to summarize the latest
  build within its 2000-character cap. Verify the character count after
  editing it.
- After any options change, rebuild the apworld and regenerate the options
  template into `Viscera Cleanup Detail.template.yaml` at the repo root. Never
  write to `Viscera Cleanup Detail.yaml`; it holds the player's own settings.
- When a roadmap item lands or its status changes, update the build state in
  `plans/V1_PLAN.md`.

## apworld Python: AP-framework invariants

The reviewer treats a violation of any of these as a correctness blocker.

- Only progression items are guaranteed reachable by the generator. Logic must
  not gate access on a non-progression item.
- The 26 level-access unlock items are progression, and so are the toolsanity
  tool items (Hands, Laser Welder, Shovel, J-HARM, Vendor, Incinerator, plus
  Mop and Slosh-O-Matic under the hard start). Every per-level check requires
  that level's access item; with toolsanity off that is the whole predicate.
- Toolsanity logic (on by default) lives entirely in `toolsanity.py` and is a
  band model: regular milestone rungs need the toolset whose band cap clears
  the rung with one step of slack, and everything else on a level (Employee
  of the Month, over-100 rungs, speedrun, punch-out, collectibles, the Bob
  note) needs the level's full progression kit. The scan table there is
  transcribed from the mod's APScanReport run on every level; never
  hand-guess its numbers, and never credit a band to a toolset that cannot
  physically clear it (the welder and vendor bands also need the mop, every
  special band needs Hands, the lift is a flat reservation). The full kit
  always caps at the level's known-maximum usable total.
- The Digsite gate exceptions: the two Bob events (Open the Digsite Gates,
  Find Bob) and the Red Keycard collectible additionally require the six
  note-level access items (the pedestal needs all nine notes; three are
  Office freebies), plus the chain's full kits under toolsanity.
- `completion_condition` is a solvability contract and switches on the `goal`
  option. Treat edits to it as high-risk. Named count-based traps:
  - `find_bob` resolves to the Find Bob location, whose rule carries the six
    note levels plus the Digsite (and their full kits under toolsanity).
    Those items must be progression and reachable, or the goal is unsolvable.
  - `collect_collectibles` with amount N requires access to the levels that hold
    N collectibles; the amount is clamped to the 39 that exist.
- The collectible and Bob tables in `collectibles.py` are transcribed from game
  data (map name tables, punchout handlers, `GP_Notes_Arch`); do not hand-guess
  entries. The Doom Armour and Shotgun are an Office stash, not locations.
- Item classification lives in `create_item`: level-access and progression
  tool items are progression, trap items are `ItemClassification.trap`,
  useful supply items and the quality-of-life tool unlocks (Sniffer, Broom,
  Bin Dispenser) are `ItemClassification.useful`, the rest is filler. Traps,
  supplies, and useful tool unlocks are never progression and never required
  by logic; the `trap_percentage` (default 5) and `useful_percentage`
  (default 15) options convert shares of filler slots, traps first.
- Toolsanity state travels client to mod inside the grants file as the
  `UnlockedTools` string (`"VC_Hall:Hands Welder,VC_Cryo:"`); a map absent
  from it means toolsanity off for that map, so old clients and
  toolsanity-off seeds get stock behavior. Keys: Hands Welder Shovel Lift
  Vendor Incinerator Sniffer Broom Bins Mop SloshOMatic. The client is the
  only writer.
- Traps and useful supply drops travel client to mod via
  `Saves\VCArchipelagoTraps.sav` (SeedTag, BaselineIndex, and a full
  "index:Type" queue keyed by received-item position). The mod stores the last
  applied index in its config state, applies one entry per poll, only in
  cleanable levels, and never replays another seed's queue or a pre-connect
  backlog. The slot's applied high-water mark also lives in server data
  storage (`vcd_traps_applied_{team}_{slot}`, written with an atomic `max`
  op); the client folds it into BaselineIndex so a new co-op host never
  replays entries, and holds the traps file write until the connect-time
  storage read answers. A trap must never softlock, block a required check, or
  corrupt a save. Supply drops reuse the game's own dispenser spawns (a plain
  VCBucket or VCBin) so they score exactly like vended equipment.
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
  end-of-level UI. The punch-out report's length-based paperwork bonus does
  count toward cleanliness, but each report field is clamped to its UI maximum
  server-side (600 characters, or 18 for the numeric Union ID), so a pasted
  overflow cannot inflate the score past what the fields legitimately hold.
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
- The toast feed travels client to mod via `Saves\VCArchipelagoMessages.sav`
  (a per-connect SessionTag plus newline-joined "index:segments" entries,
  segments tab-joined with a six-hex RRGGBB prefix; text sanitized to
  printable ASCII). The client is the only writer and rewrites it fresh on
  every connect. The HUD polls the file on its own machine (never the
  GameInfo, so shared-slot co-op guests get their own toasts), advances a
  shown index persisted through a config object with the class-defaults
  mirror, and a changed SessionTag resets that index, so toasts never replay
  within a session and never leak across seeds.
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
- The pre-commit gate (`.pre-commit-config.yaml` at the repo root) runs hygiene, flake8,
  and the world tests on changed `apworld/*.py`. Tests run via
  `VCD_AP/scripts/run_world_tests.py`, which uses the sibling Archipelago checkout
  (override with `AP_ROOT`, default `..\Archipelago`).
- Run the fill fuzzer across many seeds before trusting the default of one open
  starting level.
