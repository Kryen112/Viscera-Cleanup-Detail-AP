// The PRI is the single authoritative choke point for two client-to-server
// paths. ServerReceiveUICommand carries every machine UI panel click, so
// dropping a command here locks the Vendor and the J-HARM lift for host and
// guests alike. ServerReceiveIncidentReportValue carries every punch-out
// report field edit, so clamping a field's length here caps the string that
// gets replicated and saved to the UI's own maximum, keeping a pasted overflow
// from bloating the report payload. The report bonus can no longer fake
// cleanliness (the milestone probe ignores it, see VCGame_Archipelago's
// PublishCleanliness); these clamps are payload hygiene, not the anti-cheese.
// Installed through the game mode's PlayerReplicationInfoClass.
class VCPlayerReplicationInfo_Archipelago extends VCPlayerReplicationInfo;

// Seconds between deny messages, so panel click spam does not flood the HUD.
var float LastDenyMessageTime;

// The incident report bonus scales with the length of five text fields:
// ProcessIncidentReports adds len(field)/divisor to the penalty reduction,
// and the Union ID field's divisor is small enough that each character drops
// the mess penalty by a full point. Even at the UI's own caps that hands out
// far too much cleanliness for free, so the milestone probe ignores the whole
// report bonus (VCGame_Archipelago's PublishCleanliness adds ReportsPenalty
// back). These clamps only cap the string that gets replicated and saved: a
// paste bypasses the UI cap, and every field edit reaches the store through
// one of two paths on this PRI (a co-op guest sends through the ServerReceive
// RPCs, while a standalone player and a co-op host's own edits drain through
// the ClientReceive functions, the game's pending-changes flush picking the
// path by net mode), so all four truncate to the field's own UI limit before
// storing. ValueId to limit matches the report form's MaxCharacters; the
// other value ids are numeric fields left unchanged.
const ReportFieldWorkMethod  = 2;
const ReportFieldPlayerText  = 3;
const ReportFieldPeerText    = 9;
const ReportFieldUnionID     = 10;
const ReportFieldUnionText   = 11;
const ReportTextFieldLimit   = 600;
const ReportUnionIDLimit     = 18;

// The per-employee death report carries the same length-based bonus on two
// text fields (value ids 3 and 6, both capped at 600 in the UI), through its
// own server RPC, so it needs the same clamp.
const DeathReportFieldCadaver     = 3;
const DeathReportFieldIncidentText = 6;

reliable server function ServerReceiveUICommand(Actor TargetObject, name CommandID,
    optional int IntData, optional string StringData, optional Object ObjectData)
{
    local VCGameReplicationInfo_Archipelago ReplicatedInfo;

    ReplicatedInfo = VCGameReplicationInfo_Archipelago(WorldInfo.GRI);
    if (ReplicatedInfo != None && TargetObject != None)
    {
        if (VCSupplyMachine(TargetObject) != None
            && !ReplicatedInfo.IsToolUnlocked(class'VCGameReplicationInfo_Archipelago'.const.ToolVendor))
        {
            NotifyMachineLocked("Vendor");
            return;
        }
        if (VCScissorLift(TargetObject) != None
            && !ReplicatedInfo.IsToolUnlocked(class'VCGameReplicationInfo_Archipelago'.const.ToolLift))
        {
            NotifyMachineLocked("J-HARM");
            return;
        }
    }
    super.ServerReceiveUICommand(TargetObject, CommandID, IntData, StringData, ObjectData);
}

reliable server function ServerReceiveIncidentReportValue(byte ValueId, coerce string Value)
{
    super.ServerReceiveIncidentReportValue(ValueId, ClampReportValue(ValueId, Value));
}

// Truncates a report field to its UI character limit, so a pasted overflow
// cannot bloat the string that gets replicated and saved. Non-text value ids
// pass through unchanged.
function string ClampReportValue(byte ValueId, string Value)
{
    local int Limit;

    switch (int(ValueId))
    {
        case ReportFieldUnionID:
            Limit = ReportUnionIDLimit;
            break;
        case ReportFieldWorkMethod:
        case ReportFieldPlayerText:
        case ReportFieldPeerText:
        case ReportFieldUnionText:
            Limit = ReportTextFieldLimit;
            break;
        default:
            return Value;
    }
    if (Len(Value) > Limit)
        return Left(Value, Limit);
    return Value;
}

reliable server function ServerReceiveDeathReportValue(byte ReportID, byte ValueId, coerce string Value)
{
    super.ServerReceiveDeathReportValue(ReportID, ValueId,
        ClampDeathReportValue(ValueId, Value));
}

// The standalone and co-op-host drain path. Same clamp as the server RPCs,
// because the flush routes a local player's own edits through here.
reliable client simulated function ClientReceiveIncidentReportValue(byte IncidentReportID, byte ValueId, coerce string Value)
{
    super.ClientReceiveIncidentReportValue(IncidentReportID, ValueId,
        ClampReportValue(ValueId, Value));
}

reliable client simulated function ClientReceiveDeathReportValue(byte IncidentReportID, byte ReportID, byte ValueId, coerce string Value)
{
    super.ClientReceiveDeathReportValue(IncidentReportID, ReportID, ValueId,
        ClampDeathReportValue(ValueId, Value));
}

function string ClampDeathReportValue(byte ValueId, string Value)
{
    if ((int(ValueId) == DeathReportFieldCadaver
            || int(ValueId) == DeathReportFieldIncidentText)
        && Len(Value) > ReportTextFieldLimit)
    {
        return Left(Value, ReportTextFieldLimit);
    }
    return Value;
}

function NotifyMachineLocked(string MachineName)
{
    local PlayerController PlayerOwner;

    if (WorldInfo.TimeSeconds - LastDenyMessageTime < 2.0)
        return;
    LastDenyMessageTime = WorldInfo.TimeSeconds;
    PlayerOwner = PlayerController(Owner);
    if (PlayerOwner != None)
        PlayerOwner.ClientMessage("Archipelago: "$MachineName$" is locked for this level.");
}
