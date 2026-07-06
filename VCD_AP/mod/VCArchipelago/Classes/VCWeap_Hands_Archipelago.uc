// The carry-lock hands. VCGame_Archipelago swaps this subclass in for the
// stock hands on every spawn, so every stock cast against VCWeap_Hands still
// succeeds and the pawn always has hands in the inventory.
//
// While the level's Hands item is missing (the GRI tool mask, so co-op guests
// enforce the same lock) grabbing and carrying are denied but machine
// interaction keeps working: the punch clock, the dispensers, the incinerator
// doors, and every machine UI panel dispatch exactly as the stock hands do.
// The dispatch below mirrors the stock HandleInstantHit order with the grab
// branches removed.
//
// Locked machines and locked floor tools deny with a message here too, so a
// dead click never reads as a bug.
class VCWeap_Hands_Archipelago extends VCWeap_Hands;

// Seconds between deny messages, so holding the button does not flood the HUD.
var float LastDenyMessageTime;

simulated function bool IsToolUnlocked(int ToolBit)
{
    local VCGameReplicationInfo_Archipelago ReplicatedInfo;

    ReplicatedInfo = VCGameReplicationInfo_Archipelago(WorldInfo.GRI);
    return ReplicatedInfo == None || ReplicatedInfo.IsToolUnlocked(ToolBit);
}

simulated function bool HandleInstantHit(byte FiringMode, ImpactInfo Impact, optional int NumHits)
{
    local string LockedToolName;

    // The stock dispatch runs on fire mode 0 only; mirror that before the
    // lock checks so mode 1 swings never trip a deny message.
    if (FiringMode == 0 && Instigator != None && Role == ROLE_Authority
        && Impact.HitActor != None)
    {
        // Each deny mirrors the stock placement guard, so a click that stock
        // hands would not treat as machine use falls through unchanged.
        if (VCBucketDispensor(Impact.HitActor) != None
            && Impact.HitLocation.Z > Impact.HitActor.Location.Z - 20.0
            && !IsToolUnlocked(class'VCGameReplicationInfo_Archipelago'.const.ToolSloshOMatic))
        {
            NotifyToolLocked("Slosh-O-Matic");
            return true;
        }
        if (VCBinDispensor(Impact.HitActor) != None
            && Impact.HitLocation.Z > Impact.HitActor.Location.Z
            && !IsToolUnlocked(class'VCGameReplicationInfo_Archipelago'.const.ToolBins))
        {
            NotifyToolLocked("Bin Dispenser");
            return true;
        }
        if (VCIncinerator(Impact.HitActor) != None
            && Abs((Impact.HitLocation - Impact.HitActor.Location) Dot Vector(Impact.HitActor.Rotation)) > 60.0
            && !IsToolUnlocked(class'VCGameReplicationInfo_Archipelago'.const.ToolIncinerator))
        {
            NotifyToolLocked("Incinerator");
            return true;
        }
        if (VCIncineratorDoorHull(Impact.HitActor) != None
            && Abs((Impact.HitLocation - Impact.HitActor.Owner.Location) Dot Vector(Impact.HitActor.Owner.Rotation)) > 60.0
            && !IsToolUnlocked(class'VCGameReplicationInfo_Archipelago'.const.ToolIncinerator))
        {
            NotifyToolLocked("Incinerator");
            return true;
        }
        LockedToolName = LockedToolPickupName(Impact.HitActor);
        if (LockedToolName != "")
        {
            NotifyToolLocked(LockedToolName);
            return true;
        }
    }
    if (!IsToolUnlocked(class'VCGameReplicationInfo_Archipelago'.const.ToolHands)
        && !IsEquipmentGrab(Impact.HitActor))
    {
        return HandleCarryLockedHit(FiringMode, Impact);
    }
    return super.HandleInstantHit(FiringMode, Impact, NumHits);
}

// Equipment stays carryable under the carry-lock: buckets (the mop needs its
// rinse water nearby), bins, the radio, the janitor trunk, and the J-HARM.
// Only a direct hit on equipment that can be held right now passes through:
// the stock grab then takes the directly hit actor as its target, so nearby
// mess can never ride along, and a hit the stock path cannot hold (a raised
// lift) stays on the locked dispatch instead of falling into the stock
// proximity search.
simulated function bool IsEquipmentGrab(Actor HitActor)
{
    local VCHoldableInterface Holdable, Redirected;

    Holdable = VCHoldableInterface(HitActor);
    if (Holdable == None)
        return false;
    Redirected = Holdable.RedirectActor();
    if (Redirected != None)
    {
        HitActor = Actor(Redirected);
        Holdable = Redirected;
    }
    if (!Holdable.CanHold(Instigator))
        return false;
    return VCBucket(HitActor) != None
        || VCBin(HitActor) != None
        || VCRadio(HitActor) != None
        || VCTrunk(HitActor) != None
        || VCScissorLift(HitActor) != None;
}

// The tool a floor pickup would grant, when that tool is still locked. The
// pickup grab path grants the weapon outside the GameInfo, so it is denied at
// the hands; the per-second inventory sweep backstops anything that slips in.
simulated function string LockedToolPickupName(Actor HitActor)
{
    if (VCItemDrop_WeldingLaser(HitActor) != None
        && !IsToolUnlocked(class'VCGameReplicationInfo_Archipelago'.const.ToolWelder))
    {
        return "Laser Welder";
    }
    if (VCItemDrop_Broom(HitActor) != None
        && !IsToolUnlocked(class'VCGameReplicationInfo_Archipelago'.const.ToolBroom))
    {
        return "Broom";
    }
    if (VCItemDrop_Shovel(HitActor) != None
        && !IsToolUnlocked(class'VCGameReplicationInfo_Archipelago'.const.ToolShovel))
    {
        return "Shovel";
    }
    return "";
}

// The stock dispatch with every grab branch removed: machine UI panels, the
// dispensers, the incinerator doors, and plain UsedBy still work, so the
// punch clock and the Slosh-O-Matic stay reachable with hands locked.
simulated function bool HandleCarryLockedHit(byte FiringMode, ImpactInfo Impact)
{
    local Actor Thing;
    local bool bAimedAtHoldable;

    if (FiringMode == 1 || Instigator == None)
        return false;
    // A net guest runs only the machine UI branch locally, same as stock; the
    // server runs the rest through its own call.
    if (Role < ROLE_Authority)
    {
        if (Impact.HitActor != None
            && VCMachineUIHandsInterface(Impact.HitActor) != None)
        {
            VCMachineUIHandsInterface(Impact.HitActor).UseMachineUI(Instigator, Impact.HitLocation);
            return true;
        }
        return false;
    }
    if (Impact.HitActor == None || Pawn(Impact.HitActor) != None)
        return false;
    if (VCMachineUIHandsInterface(Impact.HitActor) != None
        && VCMachineUIHandsInterface(Impact.HitActor).UseMachineUI(Instigator, Impact.HitLocation))
    {
        return true;
    }
    if (VCHoldableInterface(Impact.HitActor) != None
        && VCHoldableInterface(Impact.HitActor).CanHold(Instigator))
    {
        // A holdable that is also usable still gets its use; the grab that
        // would follow in stock hands is the denied part.
        if (Impact.HitActor.UsedBy(Instigator))
            return true;
        NotifyToolLocked("Hands");
        return true;
    }
    if (VCBucketDispensor(Impact.HitActor) != None
        && Impact.HitLocation.Z > Impact.HitActor.Location.Z - 20.0)
    {
        VCBucketDispensor(Impact.HitActor).Use(Instigator);
        return true;
    }
    if (VCBinDispensor(Impact.HitActor) != None
        && Impact.HitLocation.Z > Impact.HitActor.Location.Z)
    {
        VCBinDispensor(Impact.HitActor).Use(Instigator);
        return true;
    }
    if (VCIncinerator(Impact.HitActor) != None
        && Abs((Impact.HitLocation - Impact.HitActor.Location) Dot Vector(Impact.HitActor.Rotation)) > 60.0)
    {
        VCIncinerator(Impact.HitActor).Use(Instigator);
        return true;
    }
    if (VCIncineratorDoorHull(Impact.HitActor) != None
        && Abs((Impact.HitLocation - Impact.HitActor.Owner.Location) Dot Vector(Impact.HitActor.Owner.Rotation)) > 60.0)
    {
        VCIncinerator(Impact.HitActor.Owner).Use(Instigator);
        return true;
    }
    if (Impact.HitActor.UsedBy(Instigator))
        return true;
    // The click did nothing. Explain it only when stock hands would have
    // grabbed something nearby, so wall clicks stay silent.
    foreach CollidingActors(class'Actor', Thing, 48.0,
        Impact.HitLocation - (Impact.RayDir * 32.0), false,
        class'VCHoldableInterface')
    {
        if (VCHoldableInterface(Thing).CanHold(Instigator))
        {
            bAimedAtHoldable = true;
            break;
        }
    }
    if (bAimedAtHoldable)
        NotifyToolLocked("Hands");
    return false;
}

simulated function NotifyToolLocked(string ToolName)
{
    local PlayerController PlayerOwner;

    if (Role != ROLE_Authority || Instigator == None)
        return;
    if (WorldInfo.TimeSeconds - LastDenyMessageTime < 2.0)
        return;
    LastDenyMessageTime = WorldInfo.TimeSeconds;
    PlayerOwner = PlayerController(Instigator.Controller);
    if (PlayerOwner != None)
        PlayerOwner.ClientMessage("Archipelago: "$ToolName$" is locked for this level.");
}
