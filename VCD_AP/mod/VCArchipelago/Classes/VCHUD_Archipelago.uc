// The Archipelago HUD: the stock HUD plus a live cleanliness readout.
//
// Draws the replicated cleanliness in the top-right corner, below the band
// the multiplayer net-actors warning uses. Runs on the host and on co-op
// guests alike; the value arrives through the replicated GRI. The game's
// speedrun timer shares this corner but only draws in speedrun mode, which
// Archipelago never sets.
class VCHUD_Archipelago extends VCHUD;

function DrawHUD()
{
    local VCGameReplicationInfo_Archipelago ReplicatedInfo;

    super.DrawHUD();

    ReplicatedInfo = VCGameReplicationInfo_Archipelago(VCGRI);
    if (ReplicatedInfo == None || !ReplicatedInfo.bCleanlinessSampled)
        return;

    Canvas.SetDrawColor(255, 255, 255, 255);
    DrawTextEx(FormatCleanliness(ReplicatedInfo.CleanlinessHundredths),
        float(Canvas.SizeX - 4), 40.0 * RatioY, 24.0 * RatioY, VCDFont,
        HA_Right, VA_Top, true);
}

// "32.12% cleaned": floored whole percent, a point, two floored decimals.
// Integer divide truncates toward zero and drops the sign of a -0.xx value,
// so peel the sign before splitting.
function string FormatCleanliness(int Hundredths)
{
    local int AbsoluteHundredths;
    local string SignText;

    if (Hundredths < 0)
    {
        SignText = "-";
        AbsoluteHundredths = -Hundredths;
    }
    else
    {
        AbsoluteHundredths = Hundredths;
    }
    return SignText $ (AbsoluteHundredths / 100) $ "."
        $ GetDualDigit(AbsoluteHundredths - (AbsoluteHundredths / 100) * 100)
        $ "% cleaned";
}
