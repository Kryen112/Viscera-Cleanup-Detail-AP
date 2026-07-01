# Building the next Archipelago world: a playbook

Distilled from the HP2PC project. Game-agnostic. The ordering is deliberate:
the first section is the scaffolding we wish we had on day one, before a single
line of game logic. Everything after it is cheaper once that scaffolding exists.

The one-sentence lesson: **stand up the guardrails first, keep one source of
truth, and do not build machinery (generators, protocols, abstractions) until
the hand-written version hurts.**

---

## Part 0. Guardrails to stand up before writing any game logic

These paid for themselves many times over, and every one of them we bolted on
late. Do them in the empty repo.

### 0.1 CLAUDE.md as the single source of truth
Write it before the code. It holds three things:
- **House style** for every language in the repo (Python, the mod language, the
  tracker pack). Concrete rules, not vibes: no em dashes, comment tense,
  no abbreviations, no user name in code, commit-message shape.
- **Framework invariants** that a reviewer must treat as correctness blockers
  (see Part 1). These are the rules that are non-obvious and expensive to get
  wrong.
- **How review and testing work** so any agent or session can reconstruct the
  process from the file alone.

Keep it terse and imperative. It is loaded into every session, so bloat costs
you on every turn.

### 0.2 A read-only reviewer subagent, wired to a Stop hook
- Author a `code-reviewer` subagent whose entire job is: read the diff, check it
  against CLAUDE.md, return findings with `file:line` and a severity. It never
  edits.
- Wire a **Stop hook** so the review fires automatically on any turn that
  touched the apworld source. Automation beats remembering. The single biggest
  process win was making the review non-optional rather than a thing to
  remember to run.
- Let workflows and other agents call the same reviewer as a verify stage, so
  the standard is enforced identically whether a human, a hook, or a fan-out
  triggered it.

### 0.3 Pre-commit hooks: hygiene, lint, tests
Gate commits on changed source with three layers:
1. hygiene (whitespace, line endings, no stray debug files),
2. lint/format (the framework's own config, see 0.4),
3. the world tests (see 0.5).

Run the tests through a small script rather than inline in the hook config, so
the same entry point works from the hook, from CI, and from a manual run.

### 0.4 Lint and format config that matches the framework
Adopt Archipelago's own lint/style (flake8 + a `setup.cfg`) from the start.
Conforming continuously is free; retrofitting a whole world to pass lint later
is a slog. Treat "passes lint and style, unprompted" as part of the definition
of done for every change.

### 0.5 A test harness wired against a real Archipelago checkout
- Every behavior change adds or updates a `WorldTestBase` test, unprompted. Make
  this a standing rule in CLAUDE.md, not a per-task ask.
- The tests need a real AP checkout to import against. Put a sibling checkout
  next to the repo, and write the test runner to locate it (with an env-var
  override, e.g. `AP_ROOT`) rather than hard-coding a path. Do this in the first
  week; wiring it later means the first dozen changes shipped untested.

### 0.6 A multi-seed fill fuzzer, early
Run generation across thousands of seeds early and watch for `FillError`. It
tells you whether a fill failure is **structural** (your logic is genuinely
unsolvable for some configuration) or **probabilistic seed luck** (a tiny
sphere-0, unlucky placement). We spent effort chasing a "bug" that was seed
luck. Knowing the base rate from day one saves that.

### 0.7 Pin the framework version and keep a quirks log
- Pin the exact Archipelago version. API surface shifts between minor versions.
- Keep a running list of framework gotchas as you hit them (for us: no
  `update_tags()` on `CommonContext`, so tag updates follow the ConnectUpdate
  pattern). Every one you record is one the next session does not rediscover.

### 0.8 A decision/memory log
Capture non-obvious *decisions and facts* (not code structure, not git history):
why an approach was abandoned, what a subtle contract means, which install is
the real one. One fact per note, with a one-line index. This is what lets a
later session avoid relearning what a dead end was.

---

## Part 1. Architecture decisions to get right early

### 1.1 Do NOT build a generator prematurely
We built a generator plus `data/*.yaml` as the source of truth, then retired the
whole layer. For a hand-maintained world it added a second source of truth and a
layer of indirection for no payoff: **the `.py` files were the real owned
source all along.** Only introduce code generation when the data genuinely
outgrows hand-editing (hundreds of near-identical entries with a mechanical
mapping). Default to hand-written Python that you edit directly. If you package,
let the packager only package; it must not own logic.

### 1.2 Separate logic from plumbing
Put game logic in one clearly-named place with a boolean-predicate shape
(an access-rule DSL), and read changes there as *logic* to be reasoned about,
not plumbing to be skimmed. Everything else (item/location tables, options,
client) is plumbing around that core. This separation is what makes the reviewer
and your own review effective: you know which diffs need hard thinking.

### 1.3 Nail the solvability contracts and write them into CLAUDE.md
- Only **progression** items are guaranteed reachable by the generator. Logic
  must never gate access on a non-progression item. This is the single most
  common way to ship a subtly-broken world.
- Item classification is a design decision per game mode, made in one place
  (`create_item`): what is progression, useful, filler,
  `progression_skip_balancing`.
- `completion_condition` (and any "N of item X unlocks the goal" threshold) is a
  contract about what the generator guarantees is beatable. Any edit to it is
  high-risk. We had a "need 40 of item X or it is unsolvable" trap; name those
  traps explicitly so a later change to a count does not silently break
  solvability.

### 1.4 Know exactly which install runs, from day one
We ran two installs: a source checkout used only for validation, and a separate
frozen install that the player actually launched. Debugging the wrong one wasted
real time. Before you debug anything, pin down: which binary runs, where its
config lives, where its logs and generated output land. Write it in the memory
log. Never bake a real machine path as a config default; players set their own.

### 1.5 Design for disconnect and for protocol limits up front
If the world talks to a game mod over a socket:
- Assume the client disconnects and reconnects. Outbound checks and goal
  completion must **recover on reconnect** from the framework's own state
  (checked-locations set, finished-game flag), not from in-memory-only bookkeeping.
- Design message framing before you need it. We hit a line-overflow bug where an
  oversized line lost its newline and ate the next message. Chunk large frames
  and put a universal newline guard on every outbound frame from the start.

---

## Part 2. Suggested build order

1. Repo scaffolding: Part 0 in full (CLAUDE.md, reviewer + hook, pre-commit,
   lint config, test runner against a sibling AP checkout).
2. Options and the world skeleton that imports and registers cleanly.
3. Item and location tables as plain hand-written Python.
4. The access-rule logic DSL, with `WorldTestBase` tests written alongside.
5. `completion_condition` and item classification, reviewed as high-risk.
6. Fill fuzzer across many seeds to establish the base rate.
7. Client/mod integration, if the game needs one (Part 3).
8. Tracker pack, last, generated from or checked against the same logic.

---

## Part 3. The mod / client boundary (only if the game needs a mod)

- Keep the boundary between the apworld and the game mod explicit and frozen.
  Ours depended on markers in the mod that we agreed not to change to suit a
  Python edit. Decide which side owns which contract and write it down.
- Prefer event-driven over polling on the game side (fire a check on the event,
  keep a poll only as a safety net). It is simpler to reason about and less
  racy, and it is easier to do from the start than to retrofit.
- The person who can run the game and paste real logs is a required part of the
  loop. Design your verification so a single in-game run produces the evidence
  you need, because each run has a cost.

---

## Part 4. Testing and verification discipline

- Tests are part of every change, not a phase. The Stop hook and pre-commit
  gate make this structural rather than optional.
- **Bisect before blaming.** Never assert a root cause (especially
  "pre-existing") from theory. Get evidence: bisect, or check the one
  load-bearing fact, before you commit to an explanation.
- **Measure before speculating.** Ground guards and special-casing in observed
  data. Do not add complexity against an imagined problem.
- In-game verification is the final gate for anything the player sees. Note the
  date and result in the memory log so it is not re-litigated.

---

## Part 5. Working practices that saved time

- **One design question at a time**, always with a recommendation. The human
  authors the game logic; the agent scaffolds, tests, and reviews.
- **Commit style**: short sentences ending in full stops, no semicolon-chained
  clauses, err shorter, no body, no AI attribution, no human name in the
  message body. Commit directly to the main branch when asked.
- **Concurrent edits**: if multiple agents touch the same files under one
  identity, stage only your own hunks, commit in one tight sequence, and never
  leave hunks staged across a turn.
- **No em dashes** anywhere. Present-tense comments only, no changelog narration
  in code, no external references (playtester names, issue numbers, log lines).
- **Spell domain terms in full** in identifiers. Widen whitespace rather than
  truncate a name.

---

## The short version

The things we found late and would want on day one, in priority order:

1. CLAUDE.md as the single source of truth.
2. A read-only reviewer subagent fired automatically by a Stop hook.
3. Pre-commit hooks: hygiene, lint, world tests.
4. `WorldTestBase` tests as part of every change, run against a real AP checkout.
5. Framework lint/format config adopted continuously, not retrofitted.
6. A multi-seed fill fuzzer to learn the FillError base rate.
7. Pinned framework version plus a running quirks log.
8. No premature generator. Hand-written Python is the source of truth.
9. Solvability contracts (progression reachability, completion condition,
   count-based traps) written down and treated as high-risk.
10. Clarity on which install actually runs, and design for disconnect and
    protocol limits from the start.

---

## Appendix A. Unreal / UScript mod patterns (HP1, HP2, HP3, and kin)

HP1 and HP2 share the KnowWonder Unreal Engine 1 generation, so most of this
carries almost directly. HP3 is a later revision of the same toolchain, so treat
its specifics as hypotheses to confirm, not facts to assume.

**Read this whole appendix as a re-verification checklist, not a spec.** The
*patterns* below transfer between games. The *exact mechanisms* (which ini wins,
the precise entry-point hook, a language quirk) are engine-version-specific.
Bisect and confirm each per game before relying on it. Asserting "HP3 works like
HP2" from theory is exactly the trap the main playbook warns against.

### A.1 Mod entry point
- Subclass the engine's `GameInfo`, override `event InitGame()`, and register it
  via `DefaultGame=` in `Game.ini` under `[Engine.Engine]`. This is the entry
  point that worked; confirm the class and ini key per game.
- Dead ends we burned time on: `ServerActors=` is silently ignored, and the
  `?Mutator=` URL parameter does not apply. Do not reach for them again.
- Spawn your mod actors from `InitGame` using `DynamicLoadObject` plus `Spawn`.
  There is no mutator hook to lean on, so `InitGame` is your one anchor.

### A.2 Config and ini layering
- There is an override hierarchy across per-game ini files (for us
  `Game.ini` > `HP.ini` > `Default.ini`, with the first two optional). Ship a
  single pre-patched `Default.ini`; tell players with prior launches to delete
  stale per-user ini so it does not shadow your patch.
- Encoding is a trap: the ini files are ANSI but the game log is UTF-16LE. Read
  and write each with the right encoding or you get mojibake and silent misreads.
- When you extend the package list (`EditPackages`), insert at the correct line
  in the file, not at end-of-file. The file continues past the visible list.

### A.3 Build toolchain (UCC)
- `UCC make` rebuilds shared engine packages every run. That is expected and
  safe, not a sign something is wrong.
- UCC accepts `#exec` asset imports (meshes, animations, textures) directly, so
  asset packaging can live in the build step.
- UCC writes no log file. All build diagnostics are stdout only, so capture
  stdout or you lose the errors.
- Building against an install under a protected directory needs elevated
  privileges. In this project the human runs the rebuild and pastes UCC stdout;
  keep that division. Do not try to run the elevated build from the agent.

### A.4 UScript language gotchas
- Array dimensions must be an integer literal, not a `const` or enum value.
- Widen this list per game as you hit new ones, and record each in the memory
  log so the next game does not rediscover it.

### A.5 The teardown-GC actor-reference hazard (the expensive one)
A class-default singleton pointer that holds any instance `Actor` reference
causes a garbage-collection crash on level teardown (for us, on any level
transition). The fix is to host per-level singletons on the level's `GameInfo`
(reachable via `Level.Game`), not on a `default.LatestInstance`-style class
pointer. If you build any manager or registry actor, apply this from the start
rather than discovering it via a transition crash.

### A.6 Spawning visible actors at runtime
Runtime-`Spawn()`ed *visible* actors may never render (proven by bisect in the
open-castle build). The only reliable revival was to build the actor hidden at
level init and un-hide it later, instead of spawning it on demand. If a feature
needs a new visible actor mid-level, plan for the hidden-then-reveal pattern.

### A.7 Instant (event-driven) checks over polling
- Fire a location check on the touch or pickup event, not from a poll. Keep a
  poll only as a safety net. Event-driven is simpler to reason about and less
  racy, and far easier to do from the start than to retrofit.
- Overriding an interactable or vendor means extending the stock base class
  (so the game's own bind loop still finds it) and doing a destroy-first swap of
  the original. A parallel replacement that does not extend the base gets
  skipped by the engine's own wiring.

### A.8 Persistence across save/load and level travel
- Grants persist by writing the save immediately after the grant. Do not assume
  in-memory state survives.
- Actors are garbage-collected on level travel, and `Destroyed` does not fire on
  travel. To carry on-screen state across a loading zone, continuously mirror it
  into a class-default buffer and drain it on the far side.
- On a new-game restore, reconcile granted state explicitly (a RESYNC pass), or
  milestones and toasts silently drop.

### A.9 The mod-to-client socket protocol
- Line overflow is real: an oversized outbound line loses its newline and eats
  the next message. Chunk large frames with an explicit begin/chunk/end envelope
  and put a universal newline guard on every outbound frame. Design this before
  you have a frame large enough to trip it.
- Recover outbound checks and goal completion on reconnect from the framework's
  own state (checked-locations set, finished-game flag), with the mod replaying
  its checked and goal markers. Do not rely on in-memory-only bookkeeping.
- The AP Kivy client window only shows the `Client` logger. Player-facing client
  messages must use that logger name, or they are file-only and invisible.

### A.10 Assets are per-game, expect to redo them
The visual and audio asset model did not generalize even within one game
(irregular skin names, meshes shared across items, sounds in mixed codecs, some
textures decodable and some procedural and not). Budget for re-discovering the
asset taxonomy per game with a census/dump pass, and do not assume HP1 or HP3
lay assets out like HP2.

### A.11 Deployment: know your two installs
As in the main playbook, expect a dev checkout used only for validation and a
separate frozen install the player actually launches. Debug the frozen one: its
config, its logs, its generated output. Confirm which is which before chasing
any in-game bug.
