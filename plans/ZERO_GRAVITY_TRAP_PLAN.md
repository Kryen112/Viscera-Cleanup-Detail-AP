# Zero Gravity Trap plan

## Context

Add a new Archipelago trap, **Zero Gravity Trap**: when received, gravity in
the current level drops to a near-zero float for 30 seconds, then restores.
Debris drifts, thrown objects sail, staged piles scatter, the janitor
moon-jumps. It joins the five existing traps as another
`ItemClassification.trap` filler item behind the existing `trap_percentage`
option, and it is a timed effect in the mold of Slowdown and Speedup (shared
30-second shape, HUD countdown, restore on a timer). Per the CLAUDE.md trap
invariant it must never softlock, block a required check, or corrupt a save.

The trap plumbing is fully generic: an item name, a type token, an automatic
client mapping, one `ApplyQueueEntry` branch in the mod. No changes to the
queue file format, baseline logic, co-op replay guards, or the toast feed.

## How gravity works in this game (explored, decompiled source, then measured)

Two distinct mechanisms exist, and the trap needs both. A throwaway
`VCGravitySpike` probe package (compiled into the dev install, never the repo,
removed after) ran timer-driven measurements in VC_Section8, VC_ZeroG, and
VC_ZeroG_New: it tossed the pawn and sampled rigid body debris at quarter
second intervals under each candidate lever. The measured numbers below come
from those runs.

### The two gravity levels: placed VCLowGravityVolume brushes

Only **VC_ZeroG (Zero-G Therapy)** and **VC_ZeroG_New (Gravity Drive)** have
toggleable gravity (they are the two rows with a nonzero "free" machine-work
column in the toolsanity scan table; the 50 points is the punch-out penalty
for leaving low gravity on).

- `VCLowGravityVolume extends GravityVolume extends PhysicsVolume`
  (VisceraGame). It is a placed brush volume, listed per map in
  `VCMapInfo.GravityVolumes`. Brush volumes cannot be spawned at runtime (no
  brush geometry), so this mechanism cannot be ported to other levels.
- `SetEnabled(bool)` is the whole switch: sets `bEnabled`, sets
  `bWaterVolume = bEnabled` (pawns inside go to swimming physics, which is the
  authentic weightless movement feel), sets `GravityZ` to `ActiveGravity`
  (per-instance map data) when on or back to the class default (-520, normal)
  when off, then wakes the rigid body of every `VCDebris` in the level so
  sleeping props start floating immediately.
- `bEnabled` is repnotify and replicates; co-op guests re-run `SetEnabled`
  from `ReplicatedEvent`. Kismet drives it through `OnToggle`
  (`SeqAct_Toggle`).
- The in-level console is a `VCInteractiveActor` whose machine UI is
  `VCUI_InteractiveUI_GravityConsole`. Clicking sends
  `ServerReceiveUICommand('SwitchInteractiveState')`; the state change fires
  the map's Kismet, which toggles the volumes. State 2 is a "Cycling"
  transition during which the console refuses input.
- The volume implements `SaveGameStateInterface` and serializes `bEnabled`
  into the level save. A trap-flipped volume left unrestored would persist
  across save and load.
- `VCPunchoutCondition_IsLowGravityOn` charges a penalty when low gravity is
  still enabled at punch-out. The mod's `APScanReport` already measures this
  as `GravityPenalty`, and live cleanliness (`ProcessMapState`) includes it,
  so while the trap runs in these two levels the live percent dips by that
  free-work share (under one percent) and returns on restore.
- **Measured: both gravity levels START in zero gravity.** In VC_ZeroG (two
  volumes) and VC_ZeroG_New (one volume) the probe found every volume
  `bEnabled=True` at level start with `ActiveGravity=0.0` (true zero, not
  low), `bWaterVolume=True`, and the janitor spawn inside. Inside an enabled
  volume the pawn runs swimming physics and a tossed debris rises at constant
  velocity while world gravity sits at -520: the volume fully overrides the
  world lever. So the trap's volume path only has a visible effect after the
  player has turned gravity on at the console; a level still in its starting
  zero-g is already in the trap state and the trap is a no-op there.
- Both maps also layer plain `GravityVolume` brushes (fixed `GravityZ`, seen
  as the pawn's volume at floor level in Gravity Drive). Those keep their
  designed gravity no matter what the trap does; they are deliberate map
  pockets and stay untouched.

### Every other level: world gravity

- `WorldInfo.WorldGravityZ` is a transient float, **replicated** (it sits in
  the same `bNetDirty` block as `TimeDilation`), and the native
  `WorldInfo.GetGravityZ()` returns it. `PhysicsVolume.GetGravityZ()` defers
  to it, so pawn falling physics follows a live change. This is the exact
  lever the stock UT3 low-gravity mutator uses.
- **Measured: writing `WorldGravityZ` alone is sufficient for everything.**
  With `WorldGravityZ = -60`, tossed debris decelerated at about -120 uu/s^2
  (exactly -60 times the install's `RBPhysicsGravityScaling` of 2.0) and the
  pawn at about -116 uu/s^2; the control tosses at -520 measured about -1040
  for both. The PhysX scene re-derives rigid body gravity from
  `WorldGravityZ` live, so `SetLevelRBGravity` is redundant and the trap does
  not call it. The engine never resets the value on its own (it held -60
  across every sample); restore is writing back the captured value.
- Because the one write replicates, co-op guests get both pawn and rigid body
  gravity for free. No GRI side channel is needed.
- Sleeping rigid bodies ignore a gravity change until woken. The trap mirrors
  what `SetEnabled` does: wake every `VCDebris` mesh on apply and again on
  restore so floaters settle back down. Measured wake counts (197, 304, and
  649 debris per level) ran with no visible hitch.
- Inside any `GravityVolume` the volume's own `GravityZ` overrides world
  gravity even while disabled (the native override returns it
  unconditionally, confirmed by the constant-velocity rise inside enabled
  volumes). So the world lever is invisible inside the gravity levels'
  volumes, which is why those two levels use their own volumes instead.
- `WorldGravityZ` is transient: a level reload resets it, so a crash or quit
  mid-trap cannot corrupt anything on this path.

### Safety notes feeding the design

- **Never set gravity to zero or positive.** A pawn that jumps under exactly
  zero gravity may never land, and positive gravity rains the level into the
  ceiling. A small negative value (-60, roughly one ninth of the normal -520)
  keeps everything sinking and self-recovers even if a restore were missed.
- Trophies and collectibles are plain `VCDebris` (`VCTrophyHandler` stores
  `array<VCDebris>`), so the wake pass wakes them too. A woken body under
  reduced negative gravity re-settles in place unless pushed; and even the
  worst case (a collectible drifting into a destroy hazard) is recoverable
  because restarting the shift respawns the level, so no check is permanently
  blocked.
- Bodies drifting during the 30 seconds can spill buckets and scatter piles.
  That is the trap working as intended and is all cleanable. The Gravity
  Drive probe run lost about a hundred woken debris to out-of-world
  destruction across its tosses, which only removes penalty (cleanliness can
  only improve); the mild negative value keeps unbumped items settling
  instead of drifting into void levels' kill boundaries.
- Fall damage: none. No falling-damage handling exists in the decompiled
  VisceraGame classes, and the probe's pawn tosses and gravity restores never
  moved health off 100 in any run.

## Design decisions (to confirm before building)

1. **Feel in the 24 normal levels**: low gravity (slow fall, moon jumps,
   drifting debris) via `WorldGravityZ`. True weightless swim physics is not
   portable outside the placed volumes. Measured at -60: a debris tossed at
   200 uu/s floats up for about 1.6 seconds and drifts down over several
   more, versus an apex inside the first quarter second at normal gravity. A
   good float that still settles; -60 is the build value, revisited only if
   playtesting wants more or less.
2. **The two gravity levels use the game's own volumes**: apply by calling
   `SetEnabled(true)` on every entry in `MapInfo.GravityVolumes` (exactly what
   the map Kismet does via `SeqAct_Toggle`), restore each volume to its
   captured pre-trap state. Both levels start in zero-g, so the trap only
   changes anything after the player has turned gravity on at the console;
   when the level is still in its starting zero-g the volume path is a no-op
   and the trap still shows its HUD countdown (the queue entry is spent
   either way, matching how Bucket Spill falls back rather than refunds).
   Driving the console's `InteractiveState` instead would keep the console
   caption truthful but couples the trap to per-map Kismet wiring and the
   Cycling lockout; calling the volumes directly matches the punch-out
   condition, the scan, and replication, and the console self-corrects on the
   next click. Recommended: volumes directly, console desync accepted.
   - Alternative worth deciding: in these two levels, skip the auto-restore
     and let the janitor walk to the console and fix it (authentic sabotage,
     natural counterplay). Recommended against for consistency with the
     30-second HUD countdown, but cheap to choose either way.
3. **Restore-before-anything-persists**: on the gravity-level path the volume
   state serializes into the level save, so the restore must also run from
   the level-teardown paths that already clear `PollTraps` timers (punch-out
   and quit), not only from the 30-second timer.
4. **Duration**: reuse the 30-second shape. Rename or share
   `SpeedEffectDurationSeconds` (a shared `TimedEffectDurationSeconds` const)
   rather than adding a second magic number.
5. **Stacking**: gravity runs on its own clock and state, independent of the
   speed effect (they can overlap; the GRI has four timed-effect slots). A
   second Zero Gravity Trap while one runs restarts the 30 seconds, matching
   how Slowdown replaces Speedup today.

## apworld changes (Python)

1. **`VCD_AP/apworld/traps.py`**: add `"Zero Gravity Trap": "ZeroGravity"` to
   `TRAP_TYPE_BY_NAME`. `TRAP_NAMES`, `QUEUE_TYPE_BY_NAME`, and the client's
   `queue_id_to_type` derive from it, so the client side is automatic.
2. **`VCD_AP/apworld/items.py`**: append `"Zero Gravity Trap"` to the very
   end of `_ID_ORDERED_NAMES` (after `"Magnetize Trap"`), per the frozen-tail
   rule so existing ids stay stable. The sorted assert and
   `ITEM_GROUPS["Traps"]` follow automatically.
3. Classification and pool fill need no code change: `create_item` already
   maps any `TRAP_NAMES` member to `ItemClassification.trap`, and
   `create_items` fills trap slots with `random.choice(TRAP_NAMES)`.
4. Tests (`test_traps.py`, `test_generation.py` as fits): queue building
   emits `index:ZeroGravity`, the item classifies as a trap, and it never
   lands in progression.

## Mod changes (UnrealScript)

Source of truth is `VCD_AP/mod/VCArchipelago/Classes/`; the packaged copy and
compiled `.u` are regenerated by the build.

5. **`VCGameReplicationInfo_Archipelago.uc`**: add
   `const TimedEffectZeroGravity = 3;`. The existing
   `StartTimedEffect`/`ClearTimedEffect`/slot plumbing handles it unchanged.
6. **`VCHUD_Archipelago.uc`**: add the `TimedEffectLabel` case, "Zero
   Gravity".
7. **`VCGame_Archipelago.uc`**:
   - `ApplyQueueEntry`: branch `QueueType ~= "ZeroGravity"` calling
     `StartZeroGravity()`.
   - New state vars: the captured pre-trap `WorldGravityZ`, a captured list
     of volume states for the gravity-level path, and a bool marking the
     effect active so a double apply restarts cleanly.
   - `StartZeroGravity()`:
     - If `VCMapInfo(WorldInfo.GetMapInfo()).GravityVolumes.Length > 0`:
       remember each volume's `bEnabled`, then `SetEnabled(true)` on all of
       them (their own wake pass and replication come free).
     - Else: capture `WorldInfo.WorldGravityZ`, set it to -60, and wake every
       `VCDebris` mesh (same loop `SetEnabled` uses). No `SetLevelRBGravity`:
       the scene re-derives rigid body gravity from `WorldGravityZ` live
       (measured).
     - Register the HUD countdown via
       `StartTimedEffect(TimedEffectZeroGravity, 30.0)` and set the restore
       timer, mirroring `ScaleJanitorSpeeds`.
   - `RestoreGravity()`: invert the applied path (volumes back to their
     remembered states, or `WorldGravityZ` back to captured), wake `VCDebris`
     again so floaters drop, clear the GRI effect. Mirroring
     `RestoreJanitorSpeeds`.
   - Call `RestoreGravity()` from the existing teardown paths that clear
     `PollTraps` (punch-out flow and `GameEnding`), guarding on the
     active-effect bool, so a persisted volume flip can never outlive the
     trap.
8. **Co-op**: `WorldGravityZ` and volume `bEnabled` both replicate, so guests
   get pawn and rigid body gravity for free. Nothing extra to build.

## Spike results (done, throwaway VCGravitySpike probe, 2026-07-08)

A probe game class launched by map URL measured VC_Section8, VC_ZeroG, and
VC_ZeroG_New with quarter second samples of the pawn and three tossed rigid
body debris per phase. The install stayed clean: the package compiled beside
`VCArchipelago.u` without recompiling it, and Saves was backed up and
restored around the runs.

1. `WorldInfo.WorldGravityZ` alone drives everything: debris deceleration
   measured about -120 uu/s^2 at -60 (times the 2.0 `RBPhysicsGravityScaling`)
   and about -1040 at -520; the pawn matched. `SetLevelRBGravity` added
   nothing on top and is not needed. The engine never overwrote the value.
2. -60 gives the wanted feel: about a 1.6 second rise on a 200 uu/s toss with
   a slow settle, versus a sub-quarter-second apex at normal gravity.
3. Restore snapped every profile back to the control numbers. A body that
   went to sleep mid-float stays asleep until woken, which is why the restore
   path wakes debris again.
4. Pawn health stayed 100 through every toss and restore: no fall damage.
5. Both gravity levels start with their volumes enabled at `ActiveGravity=0`
   with swim physics inside; `SetEnabled` flips took effect immediately and
   restoring the captured state worked. Live `ProcessMapState` reads around
   the flips ran without triggering the end-of-level flow.
6. Plain `GravityVolume` brushes in those maps keep their fixed gravity
   regardless of the world value: accepted designed pockets.

Still open for a hands-on pass during the build (not blocking): the in-hand
feel of a jump under -60, whether a held mop or bucket misbehaves while
floating, and the console caption desync after a direct volume flip.

## Docs pass (same turn as the build)

- `RELEASE_NOTES_FULL.md`: dated entry for the new trap.
- `RELEASE_NOTES.md`: rewrite within the 2000-character cap.
- No options change (the trap rides `trap_percentage`), so no template
  regeneration; rebuild the apworld so the datapackage carries the new item.
- `plans/V1_PLAN.md` build state when it lands.
