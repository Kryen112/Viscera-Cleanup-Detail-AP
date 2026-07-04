// Replicated Archipelago state, one instance per level, spawned by the game
// mode through GameReplicationInfoClass.
//
// The cleanliness readout and the timed-trap countdowns must reach co-op
// guests, who have no GameInfo, so the host writes the values here and the
// engine replicates them. Every stock VCGameReplicationInfo cast still
// succeeds against this subclass.
class VCGameReplicationInfo_Archipelago extends VCGameReplicationInfo;

// Live cleanliness in hundredths of a percent, floored, negative when the
// level is dirtier than it started. Unsampled until the first probe scan, so
// the HUD stays blank in the Office and the menus.
var int CleanlinessHundredths;
var bool bCleanlinessSampled;

// Timed trap effects for the on-screen countdown. Fixed slots because
// dynamic arrays do not replicate; the None type marks an empty slot.
const TimedEffectNone     = 0;
const TimedEffectSlowdown = 1;

var byte  TimedEffectTypes[4];
var float TimedEffectRemaining[4];
var float TimedEffectDurations[4];

// Bumped on every slot write. Declared after the payload arrays so a
// replication bunch applies the slot values before the notify restamps the
// local end times; a stamp from a torn bunch self-corrects on the next
// once-per-second refresh.
var repnotify int TimedEffectCounter;

// Local end times derived from the replicated remaining seconds. Never
// replicated: server and client clocks differ.
var float TimedEffectEndTimes[4];

replication
{
    if (bNetDirty)
        CleanlinessHundredths, bCleanlinessSampled, TimedEffectTypes,
        TimedEffectRemaining, TimedEffectDurations, TimedEffectCounter;
}

simulated event ReplicatedEvent(name VarName)
{
    if (VarName == 'TimedEffectCounter')
        StampTimedEffectEndTimes();
    else
        super.ReplicatedEvent(VarName);
}

// Rebuilds the local end times from the remaining seconds.
simulated function StampTimedEffectEndTimes()
{
    local int SlotIndex;

    for (SlotIndex = 0; SlotIndex < ArrayCount(TimedEffectTypes); SlotIndex++)
        TimedEffectEndTimes[SlotIndex] = WorldInfo.TimeSeconds + TimedEffectRemaining[SlotIndex];
}

// Server-side: starts the effect's countdown, restarting its clock when one
// is already running, and begins the once-per-second remaining refresh.
function StartTimedEffect(byte EffectType, float DurationSeconds)
{
    local int SlotIndex, ChosenSlot;

    ChosenSlot = -1;
    for (SlotIndex = 0; SlotIndex < ArrayCount(TimedEffectTypes); SlotIndex++)
    {
        if (TimedEffectTypes[SlotIndex] == EffectType)
        {
            ChosenSlot = SlotIndex;
            break;
        }
        if (ChosenSlot == -1 && TimedEffectTypes[SlotIndex] == TimedEffectNone)
            ChosenSlot = SlotIndex;
    }
    if (ChosenSlot == -1)
        return;
    // Other active slots keep their clocks: sync their remaining from the
    // live end times first, or the restamp below would extend them by
    // whatever staleness the last refresh left.
    for (SlotIndex = 0; SlotIndex < ArrayCount(TimedEffectTypes); SlotIndex++)
    {
        if (SlotIndex != ChosenSlot && TimedEffectTypes[SlotIndex] != TimedEffectNone)
        {
            TimedEffectRemaining[SlotIndex] =
                FMax(TimedEffectEndTimes[SlotIndex] - WorldInfo.TimeSeconds, 0.0);
        }
    }
    TimedEffectTypes[ChosenSlot] = EffectType;
    TimedEffectRemaining[ChosenSlot] = DurationSeconds;
    TimedEffectDurations[ChosenSlot] = DurationSeconds;
    TimedEffectCounter++;
    StampTimedEffectEndTimes();
    SetTimer(1.0, true, 'RefreshTimedEffects');
}

// Server-side: clears the effect's slot when the effect ends.
function ClearTimedEffect(byte EffectType)
{
    local int SlotIndex;
    local bool bCleared;

    for (SlotIndex = 0; SlotIndex < ArrayCount(TimedEffectTypes); SlotIndex++)
    {
        if (TimedEffectTypes[SlotIndex] != EffectType)
            continue;
        TimedEffectTypes[SlotIndex] = TimedEffectNone;
        TimedEffectRemaining[SlotIndex] = 0.0;
        TimedEffectDurations[SlotIndex] = 0.0;
        bCleared = true;
    }
    if (bCleared)
        TimedEffectCounter++;
}

// Server-side once-per-second rewrite of the replicated remaining seconds,
// so a guest who joins mid-effect converges within about a second and drift
// self-corrects. Stops itself once no slot is active.
function RefreshTimedEffects()
{
    local int SlotIndex;
    local bool bAnyActive;

    for (SlotIndex = 0; SlotIndex < ArrayCount(TimedEffectTypes); SlotIndex++)
    {
        if (TimedEffectTypes[SlotIndex] == TimedEffectNone)
            continue;
        bAnyActive = true;
        TimedEffectRemaining[SlotIndex] =
            FMax(TimedEffectEndTimes[SlotIndex] - WorldInfo.TimeSeconds, 0.0);
    }
    if (!bAnyActive)
    {
        ClearTimer('RefreshTimedEffects');
        return;
    }
    TimedEffectCounter++;
}
