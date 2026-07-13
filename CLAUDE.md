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

- The one maintained player doc is `VCD_AP/docs/PLAYER_SETUP.md` (install and
  first run). `RELEASE_NOTES.md`, `RELEASE_NOTES_FULL.md`, and
  `AI_DISCLOSURE.md` in the same directory are frozen since the first public
  release; never edit them.
- A docs pass is required for every player-visible change: options and their
  defaults, checks and goals, client commands and messages, the install and
  connect flow, save isolation, traps and supply drops. Internal refactors
  need none.
- A player-visible change ships with a small release note: a short
  Discord-ready paragraph in the turn's final summary, not a maintained file.
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
  core-kit ceiling model: the core kit (Hands, Incinerator, Mop, Slosh-O-Matic)
  cleans a level to 100 percent on its own, so every cleanliness check up to and
  including 100 (regular rungs by the band cap with one step of slack, Employee
  of the Month, punch-out, speedrun) comes with the core kit, and no situational
  tool a level does not need for 100 gates any of them. Over 100, each
  situational tool the level has (`SITUATIONAL_TOOL_KEYS`) adds a fixed share
  (`OVER_100_PER_TOOL_PERCENT`) so the over-100 ladder is a per-tool climb; it is
  a conservative floor (the report and stacking usually reach more, so higher
  rungs are often obtainable out of logic), the climb is also capped by the
  physical ceiling the missing tools leave (a tool's own scanned mess share is
  unreachable without it, so no toolset is credited a rung it cannot clean to),
  and the full kit reaches the level's over-100 maximum with margin. Four
  suspect levels leave mess only one tool can clear
  (`CORE_KIT_CEILING_PERCENT`: VC_Incubator, VC_Energy_01, and VC_Vulcan_01
  need the Welder, VC_Uprinsing the Vendor); there the core kit tops out at
  the recorded ceiling and the checks above it wait for that one
  `EXTRA_CLEAN_TOOL`. Three ceilings are measured with APCleanCoreKit; the
  Vulcan ceiling is a conservative floor under the arithmetic bound its scan
  row proves, pending a measurement. A module-import assert rejects any
  core-kit-cleans-to-100 claim the scan shares contradict, and the client
  cross-checks each level's live StartingCleanupScore against the scan table
  at play time (`APStartScore` in the state ini) and warns on drift. Physical pickups (collectibles,
  Bob notes) need the level's full clean kit (`full_clean_keys`, the core kit
  plus any suspect extra tool), because a trophy only banks on a not-fired
  punch-out; the Overgrowth pickaxe also needs the Shovel, and Athena's Wrath's
  blue easter egg the J-HARM (`COLLECTIBLE_EXTRA_TOOLS`). A tool stored where
  only another tool reaches counts as usable only alongside that prerequisite
  (`TOOL_REACH_PREREQUISITES`): Athena's Wrath keeps its Laser Welder where
  only the J-HARM reaches, so its welder rungs need both unlocks and a pickup
  rule pulls a required tool's prerequisite in with it. The scan table there
  is transcribed from the mod's APScanReport run on every level, and the suspect
  ceilings from APCleanCoreKit; never hand-guess either. The full clean kit
  always caps at the level's known-maximum usable total. An itemized
  Slosh-O-Matic (a hard-start level under `random_starting_kit`) is satisfiable
  two ways in every rule: the machine unlock or the level's Self-Cleaning Mop,
  since a mop that never dirties needs no rinse bucket; that mop copy
  classifies progression there.
- The Digsite gate exceptions: the two Bob events (Open the Digsite Gates,
  Find Bob) and the Red Keycard and Bolter collectibles additionally require
  the six note-level access items (the pedestal needs all nine notes; two
  are Office freebies and one lies in the Digsite's open dig area), plus
  each note level's clean kit under toolsanity (a note banks on a not-fired
  shift on its own level).
- `completion_condition` is a solvability contract and switches on the `goal`
  option. Treat edits to it as high-risk. Named count-based traps:
  - `find_bob` resolves to the Find Bob location, whose rule carries the six
    note levels plus the Digsite (and their clean kits under toolsanity).
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
  by logic, with one exception: a hard-start level's Self-Cleaning Mop
  classifies progression because it stands in for that level's itemized
  Slosh-O-Matic in logic. The `trap_percentage` (default 5) and
  `useful_percentage` (default 15) options convert shares of filler slots,
  traps first.
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
  backlog. Two keys live in server data storage: the slot's baseline
  (`vcd_traps_baseline_{team}_{slot}`, written exactly once at the slot's
  first-ever connect via the Set default-if-absent path, so nothing is ever
  inferred from packet order) and the applied high-water mark
  (`vcd_traps_applied_{team}_{slot}`, an atomic `max`). BaselineIndex is the
  larger of the two, so a new co-op host never replays entries and a
  reconnect never truncates an in-flight burst; the client holds the traps
  file write until the connect-time storage read answers. A trap must never
  softlock, block a required check, or corrupt a save. Supply drops reuse the
  game's own dispenser spawns (a plain VCBucket or VCBin) so they score
  exactly like vended equipment; both anchor on a random living janitor.
- DeathLink and TrapLink (both options off by default) ride a second queue,
  `Saves\VCArchipelagoLinks.sav` (a per-connect SessionTag, the DeathLinkOn
  flag, and "index:Type" entries; the client is the only writer), because
  bounced events are not items and cannot use the item-indexed trap queue.
  The mod applies entries only in a cleanable level and consumes everything
  else without effect (a tag change or a poll outside a level baselines to
  the newest index), so a stale death never fires on a level load. Any
  death, organic or inbound, kills every janitor in the session when death
  link is on; a sweep latch keeps those deaths from counting or cascading.
  Outbound, the mod publishes the organic death count (`APDeathCount`) and
  the last item-queue spawn applied (`APLastSpawn`, "index:Type"; never
  written by the link queue, so a linked trap cannot re-broadcast); the
  client adopts the first same-seed sighting of each as its baseline and
  bounces only rises. Inbound TrapLink names map through the broad alias
  table in `links.py`; unknown names are ignored, never guessed, and
  `trap_percentage` 0 does not gate inbound linked traps.
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
  compiles what is in `[UnrealEd.EditorEngine] +EditPackages=`. On the dev
  machine add a package to both. A player install gets the canonical
  precompiled package through `NonNativePackages` only: the installer
  deliberately strips `EditPackages` and any deployed source tree, so the game
  can never rebuild the package locally and fork its GUID out of co-op.
- The `VisceraHorror` and `VisceraVulcan` packages are OPTIONAL content: an
  install without the free content packs has no file for them, every import
  of their classes then resolves to none, and a statement touching such an
  import crashes the script VM. Every compile-time reference to their classes
  (the woodchipper, the shark pool) lives in
  `VCArchipelagoOptionalMachineLocks` behind package-loaded checks; never name
  them in another mod class.
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
  Three documented adjustments ride on top of the game value: the mod widens
  the Digsite's crate stacking zones to the crate archetypes the level spawns
  (the shipped map data lists only Type1 crates, which the level barely has;
  this raises the game's own score, live and at punch-out), and the published
  live value credits two flat all-or-nothing infractions gradually: sand pit
  fill on the Digsite and Penumbra (bit 262144 on both handlers, 150 points)
  and seed bed restoration on the Greenhouse (bit 1048576, 40 points). Live
  and paper agree once the job completes. A sweep of all 26 level packages
  and every per-map punchout handler confirms these are the only stacking
  zone mismatches and the only break-on-first group infractions; every other
  special mess scores per item.
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
  a FriendlyName) that the data-driven Start Work menu shows next to Cleanup
  and Speedrun. The entry deliberately carries no `ValidTitles` filter, so the
  mode exists under every title and granted DLC maps list under whichever
  title the player is running.
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
