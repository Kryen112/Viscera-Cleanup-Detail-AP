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

// The next milestone for the current level, mirrored from the client-written
// milestones file: the lowest percent whose check the server has not
// confirmed. Unknown until trustworthy same-seed data arrives; Cleared once
// every percent check for the level is confirmed. Server state only, so the
// indicator never runs ahead of the server.
const NextMilestoneUnknown = -1;
const NextMilestoneCleared = 0;

var int NextMilestonePercent;

// Speedrun: whether the current level's Speedrun check is still outstanding
// (speedrunsanity on and not yet earned). The HUD shows the speedrun timer
// only while this is set; the host reads it from the client-written milestones
// file, so co-op guests get it through replication.
var bool bSpeedrunOutstanding;

// Toolsanity: the current level's unlocked tools and machines as a bitmask,
// bit set means unlocked. The host computes it from the client-written grants
// (everything unlocked when the level has no toolsanity data, so stock
// behavior is the default) and the weapon and PRI checks read it here, so
// co-op guests enforce the same locks.
const ToolHands       = 1;
const ToolWelder      = 2;
const ToolShovel      = 4;
const ToolLift        = 8;
const ToolVendor      = 16;
const ToolIncinerator = 32;
const ToolSniffer     = 64;
const ToolBroom       = 128;
const ToolBins        = 256;
const ToolMop         = 512;
const ToolSloshOMatic = 1024;
const ToolMaskAll     = 2047;

var int UnlockedToolsMask;

// Toolsanity: the tools the current level HAS (a superset of the unlocked
// mask), so the HUD panel can tell a locked tool from one not on this level.
// The host reads it from the client-written grants; 0 means no toolsanity
// data, where the panel shows an all-available fallback.
var int PresentToolsMask;

// Squeaky Clean Boots: set when the current level holds the boots unlock, so
// the janitor pawn subclass drops foot-blood accumulation before it can ever
// stamp a print. The host reads it from the client-written grants; guests read
// it here, and the print spawn is authority-side, so the host suppression is
// what counts.
var bool bSqueakyBoots;

// Self-Cleaning Mop: set when the current level holds the mop unlock, so the
// mop weapon subclass pins its saturation to zero. The host reads it from the
// client-written grants; the mop is server-owned and replicated, so the host
// suppression reaches guests.
var bool bSelfCleaningMop;

// Timed trap effects for the on-screen countdown. Fixed slots because
// dynamic arrays do not replicate; the None type marks an empty slot.
const TimedEffectNone     = 0;
const TimedEffectSlowdown = 1;
const TimedEffectSpeedup  = 2;

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
        CleanlinessHundredths, bCleanlinessSampled, NextMilestonePercent,
        bSpeedrunOutstanding, UnlockedToolsMask, PresentToolsMask,
        bSqueakyBoots, bSelfCleaningMop, TimedEffectTypes,
        TimedEffectRemaining, TimedEffectDurations, TimedEffectCounter;
}

simulated function bool IsToolUnlocked(int ToolBit)
{
    return (UnlockedToolsMask & ToolBit) != 0;
}

// The grants-file key for each tool bit and back. The client writes these keys
// into the UnlockedTools string; the dev override commands take them too.
static function int ToolBitForKey(string ToolKey)
{
    if (ToolKey ~= "Hands")       return ToolHands;
    if (ToolKey ~= "Welder")      return ToolWelder;
    if (ToolKey ~= "Shovel")      return ToolShovel;
    if (ToolKey ~= "Lift")        return ToolLift;
    if (ToolKey ~= "Vendor")      return ToolVendor;
    if (ToolKey ~= "Incinerator") return ToolIncinerator;
    if (ToolKey ~= "Sniffer")     return ToolSniffer;
    if (ToolKey ~= "Broom")       return ToolBroom;
    if (ToolKey ~= "Bins")        return ToolBins;
    if (ToolKey ~= "Mop")         return ToolMop;
    if (ToolKey ~= "SloshOMatic") return ToolSloshOMatic;
    return 0;
}

static function string DescribeToolMask(int ToolMask)
{
    local string Described;

    if ((ToolMask & ToolHands) != 0)       Described $= "Hands ";
    if ((ToolMask & ToolWelder) != 0)      Described $= "Welder ";
    if ((ToolMask & ToolShovel) != 0)      Described $= "Shovel ";
    if ((ToolMask & ToolLift) != 0)        Described $= "Lift ";
    if ((ToolMask & ToolVendor) != 0)      Described $= "Vendor ";
    if ((ToolMask & ToolIncinerator) != 0) Described $= "Incinerator ";
    if ((ToolMask & ToolSniffer) != 0)     Described $= "Sniffer ";
    if ((ToolMask & ToolBroom) != 0)       Described $= "Broom ";
    if ((ToolMask & ToolBins) != 0)        Described $= "Bins ";
    if ((ToolMask & ToolMop) != 0)         Described $= "Mop ";
    if ((ToolMask & ToolSloshOMatic) != 0) Described $= "SloshOMatic ";
    if (Described == "")
        return "none";
    return Left(Described, Len(Described) - 1);
}

// The player-facing name for a single tool bit, for the HUD unlock panel.
static function string ToolDisplayLabel(int ToolBit)
{
    switch (ToolBit)
    {
        case ToolHands:       return "Hands";
        case ToolWelder:      return "Laser Welder";
        case ToolShovel:      return "Shovel";
        case ToolLift:        return "J-HARM";
        case ToolVendor:      return "Vendor";
        case ToolIncinerator: return "Incinerator";
        case ToolSniffer:     return "Sniffer";
        case ToolBroom:       return "Broom";
        case ToolBins:        return "Bin Dispenser";
        case ToolMop:         return "Mop";
        case ToolSloshOMatic: return "Slosh-O-Matic";
    }
    return "";
}

simulated event ReplicatedEvent(name VarName)
{
    if (VarName == 'TimedEffectCounter')
        StampTimedEffectEndTimes();
    else
        super.ReplicatedEvent(VarName);
}

// The game keeps live mess counts here: every splat and debris calls these
// four on spawn and cleanup (authority only). That makes them the change
// signal the base game otherwise lacks, so the cleanliness probe scans the
// moment mess appears or clears instead of only on a timer. Guests have no
// GameInfo, so the notify no-ops there.
simulated function AddSplat(VCSplat Splat)
{
    super.AddSplat(Splat);
    NotifyGameCleanlinessDirty();
}

simulated function RemoveSplat(VCSplat Splat)
{
    super.RemoveSplat(Splat);
    NotifyGameCleanlinessDirty();
}

simulated function AddDebris(VCDebris Debris)
{
    super.AddDebris(Debris);
    NotifyGameCleanlinessDirty();
}

simulated function RemoveDebris(VCDebris Debris)
{
    super.RemoveDebris(Debris);
    NotifyGameCleanlinessDirty();
}

simulated function NotifyGameCleanlinessDirty()
{
    local VCGame_Archipelago Game;

    Game = VCGame_Archipelago(WorldInfo.Game);
    if (Game != None)
        Game.NotifyMessChanged();
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

defaultproperties
{
    NextMilestonePercent=-1
    // Everything unlocked until the host applies the level's toolsanity data,
    // so a stock or toolsanity-off level never flickers into a locked state.
    UnlockedToolsMask=2047
}
