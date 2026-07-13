// Machine locks for the optional content packages: VisceraHorror's
// woodchipper and VisceraVulcan's shark pool. Those packages are not part of
// every install (the free content packs are optional downloads), and on an
// install without a pack every import of its classes resolves to none, which
// crashes the script VM the moment a statement touches one. Every
// compile-time reference to those classes therefore lives in this class, and
// every path that touches one sits behind a package-loaded flag, so the rest
// of the mod runs clean on installs without the packs. A level that contains
// one of these machines only exists where its package exists, so skipping
// the work when the package is absent never skips a real machine.
class VCArchipelagoOptionalMachineLocks extends Info;

// Whether each optional package is loadable on this install, checked once at
// spawn. On a full install the packages are already loaded as dependencies,
// so the checks resolve instantly.
var bool bWoodChipperPackageLoaded;
var bool bSharkPoolPackageLoaded;

// Shark pools whose sharks are despawned while the incinerator group is
// locked, so they can be respawned on unlock. The plain count mirrors the
// array for outside queries, so no caller ever touches the optionally-typed
// array itself.
var int DespawnedVolumeCount;
var array<VCSharkDisposalVolume> SharkVolumesDespawned;

event PostBeginPlay()
{
    super.PostBeginPlay();
    bWoodChipperPackageLoaded = DynamicLoadObject(
        "VisceraHorror.VCWoodChipper", class'Core.Class', true) != None;
    bSharkPoolPackageLoaded = DynamicLoadObject(
        "VisceraVulcan.VCSharkDisposalVolume", class'Core.Class', true) != None;
}

// Whether an unlock pass still owes a shark respawn, for the caller's
// steady-state early-out.
function bool HoldsRestoreState()
{
    return DespawnedVolumeCount > 0;
}

function ApplyLocks(bool bIncineratorGroupLocked)
{
    if (bWoodChipperPackageLoaded)
        PinWoodChipperTimers(bIncineratorGroupLocked);
    if (bSharkPoolPackageLoaded)
        ApplySharkPoolLocks(bIncineratorGroupLocked);
}

// The woodchipper's consume ignores its own in-flag: it destroys an object
// once that object's consume timer reaches four seconds near the intake.
// Removing the entry does not stop it, so pin every entry's timer to zero
// each pass; a one-second pass keeps it well under the four-second mark.
function PinWoodChipperTimers(bool bLocked)
{
    local VCWoodChipper Chipper;
    local int I;

    if (!bLocked)
        return;
    foreach AllActors(class'VCWoodChipper', Chipper)
    {
        for (I = 0; I < Chipper.DebrisObjects.Length; I++)
            Chipper.DebrisObjects[I].ConsumeTime = 0.0;
    }
}

// The shark pool eats what swims in within a fraction of a second, too fast
// to intercept by clearing targets on a poll, so despawn the sharks while
// locked and respawn them on unlock. The pool spawns its sharks once and
// never maintains a count, so a cleared list stays cleared.
function ApplySharkPoolLocks(bool bLocked)
{
    local VCSharkDisposalVolume SharkVolume;
    local array<VCShark> DoomedSharks;
    local int CacheIndex, I;

    foreach AllActors(class'VCSharkDisposalVolume', SharkVolume)
    {
        CacheIndex = SharkVolumesDespawned.Find(SharkVolume);
        if (bLocked)
        {
            if (CacheIndex == -1)
            {
                // Clear the pool's lists before destroying, so a shark's
                // UnTouch firing synchronously during Destroy never reads a
                // half-cleared Sharks array.
                DoomedSharks = SharkVolume.Sharks;
                SharkVolume.Sharks.Length = 0;
                SharkVolume.PendingTargets.Length = 0;
                for (I = 0; I < DoomedSharks.Length; I++)
                {
                    if (DoomedSharks[I] != None)
                        DoomedSharks[I].Destroy();
                }
                SharkVolumesDespawned.AddItem(SharkVolume);
            }
        }
        else if (CacheIndex != -1)
        {
            SharkVolume.SpawnSharks();
            SharkVolumesDespawned.Remove(CacheIndex, 1);
        }
    }
    DespawnedVolumeCount = SharkVolumesDespawned.Length;
}

// Machine presence counts for the scan report; zero when a package is
// absent, where no level can hold its machine anyway.
function int CountWoodChippers()
{
    local VCWoodChipper Chipper;
    local int Count;

    if (!bWoodChipperPackageLoaded)
        return 0;
    foreach AllActors(class'VCWoodChipper', Chipper)
        Count++;
    return Count;
}

function int CountSharkPools()
{
    local VCSharkDisposalVolume SharkVolume;
    local int Count;

    if (!bSharkPoolPackageLoaded)
        return 0;
    foreach AllActors(class'VCSharkDisposalVolume', SharkVolume)
        Count++;
    return Count;
}
