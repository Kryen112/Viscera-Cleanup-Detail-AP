// The Archipelago HUD: the stock HUD plus a live cleanliness readout with a
// next-milestone line, timed trap countdowns, and the Archipelago toast feed.
//
// The cleanliness readout draws in the top-right corner, below the band the
// multiplayer net-actors warning uses, with the level's next remaining
// milestone on a second line. Both turn green once every milestone on the
// level is confirmed checked. It runs on the host and on co-op guests alike;
// the values arrive through the replicated GRI. The game's speedrun timer
// shares that corner but only draws in speedrun mode, which Archipelago
// never sets.
//
// Timed trap countdowns draw at the top-center (a band the speedrun clock
// also leaves free outside speedrun mode): a "Slowdown 0:27" line over an
// orange bar that empties with the remaining time and blinks through the
// final seconds. The slots arrive through the replicated GRI, so guests see
// them too; remaining time reads off locally stamped end times, so expiry
// hides a slot without waiting on the server.
//
// Toasts show what Archipelago is doing: item transfers and hints involving
// this slot, chat, joins and parts, goals, releases and collects,
// countdowns, and connection lines. The feed file is written by this machine's own client and
// read here (the HUD spawns locally on every machine), so each player running
// a client sees their own toasts with no replication. Segments carry their own
// colors, matching the Archipelago text client palette. Bookkeeping lives in a
// VCArchipelagoMessageState config object so a level load or relaunch never
// replays a shown toast; only a new client session (a fresh SessionTag)
// replays its own feed.
class VCHUD_Archipelago extends VCHUD;

// Feed poll cadence, toast promotion cadence, per-toast lifetime, and the
// visible cap. Promotion paces a backlog so it scrolls instead of flooding.
const MessagePollInterval  = 1.0;
const ToastPromoteInterval = 0.15;
const ToastLifetime        = 5.0;
const MaxVisibleToasts     = 8;
const MaxHistoryToasts     = 20;
// The medium font scaled a touch under 1, so toasts read a step above the
// small join-message font without being as tall as full medium.
const ToastFontScale       = 0.9;

// Countdown block geometry (pre-ratio units) and the blink window.
const TimedEffectTextSize     = 18.0;
const TimedEffectBarWidth     = 200.0;
const TimedEffectBarHeight    = 8.0;
const TimedEffectBlinkSeconds = 5.0;

// Toolsanity unlock panel geometry (pre-ratio units). The width is a floor;
// the backing widens and grows to the measured text extents. The 11 tool bits
// are powers of two in TOOL_KEY_ORDER, so bit (1 << index) walks them in order.
// The side margin doubles as the history column's left inset, so the panel
// (right-aligned) and the history (left column) frame the screen evenly.
const ToolPanelTextSize = 18.0;
const ToolPanelWidth    = 220.0;
const ToolPanelTop      = 120.0;
const PanelSideMargin   = 12.0;
const ToolBitCount      = 11;

// Reused load target for the feed file, so the poll does not pile up garbage
// objects between collections.
var VCArchipelagoMessages MessageFeedFile;

// Persistent shown-toast bookkeeping, mirrored into class defaults on save.
var VCArchipelagoMessageState MessageState;
var bool bMessageStateDirty;

// Feed entries queued for display and the ones on screen, oldest first. The
// parallel arrays carry each pending entry's feed index and each visible
// toast's expiry time.
var array<string> PendingToastTexts;
var array<int>    PendingToastIndexes;
var array<string> VisibleToastTexts;
var array<float>  VisibleToastExpiries;

// Highest feed index already queued this level, so a poll never re-queues.
var int HighestQueuedIndex;

// Rolling log of the most recent promoted toast lines, newest last, shown on
// the Tab history panel. Independent of the visible-toast lifetime.
var array<string> ToastHistory;

simulated event PostBeginPlay()
{
    super.PostBeginPlay();
    MessageState = new class'VCArchipelagoMessageState';
    HighestQueuedIndex = MessageState.ShownIndex;
    SetTimer(MessagePollInterval, true, 'PollMessageFeed');
    SetTimer(ToastPromoteInterval, true, 'PromotePendingToast');
}

// The engine runs DrawHUD only when the scoreboard is hidden, and VCHUD draws
// the scoreboard from PostRender when it is shown. So the toolsanity panel
// (shown while the scoreboard key is held) cannot ride DrawHUD; it hooks here,
// after the scoreboard, and the rest of the HUD keeps drawing from DrawHUD as
// today when the key is not held.
event PostRender()
{
    super.PostRender();
    if (bShowScores)
    {
        DrawToolsanityPanel();
        DrawToastHistoryPanel();
    }
}

// Lists the current level's toolsanity tools while the scoreboard key is held,
// each in its player-facing name, the Archipelago location green when unlocked
// and dim grey when still locked. A level with no toolsanity data (an old
// client or a toolsanity-off seed) shows an all-available heading instead of
// the tool rows. The Self-Cleaning Mop and Squeaky Clean Boots rows follow on
// every cleanable level in either case (those unlocks exist independent of
// toolsanity); the Office never publishes their flags, so it shows neither.
// Reads the replicated GRI, so the host and co-op guests see the same panel.
// The font group can render text larger than the requested size, so the
// backing sizes from measured extents, never from the requested constants.
// The panel right-aligns to the screen edge, clear of the centered
// scoreboard, so the whole left column stays free for the toast history.
function DrawToolsanityPanel()
{
    local VCGameReplicationInfo_Archipelago ReplicatedInfo;
    local VCMapInfo MapInfo;
    local array<string> RowLabels;
    local array<byte>   RowUnlockedFlags;
    local int BitIndex, Bit, RowIndex;
    local float TextWidth, TextHeight, WidestText, RowHeight;
    local float PanelLeft, PanelTop, PanelWidth, PanelHeight;
    local float LabelLeft, HeadingTop;
    local string HeadingText;

    ReplicatedInfo = VCGameReplicationInfo_Archipelago(VCGRI);
    if (ReplicatedInfo == None)
        return;

    if (ReplicatedInfo.PresentToolsMask == 0)
    {
        HeadingText = "All tools available";
    }
    else
    {
        HeadingText = "This level's tools";
        for (BitIndex = 0; BitIndex < ToolBitCount; BitIndex++)
        {
            Bit = 1 << BitIndex;
            if ((ReplicatedInfo.PresentToolsMask & Bit) == 0)
                continue;
            RowLabels.AddItem(
                class'VCGameReplicationInfo_Archipelago'.static.ToolDisplayLabel(Bit));
            if ((ReplicatedInfo.UnlockedToolsMask & Bit) != 0)
                RowUnlockedFlags.AddItem(1);
            else
                RowUnlockedFlags.AddItem(0);
        }
    }

    MapInfo = VCMapInfo(WorldInfo.GetMapInfo());
    if (MapInfo == None || !MapInfo.bIsOfficeLevel)
    {
        RowLabels.AddItem("Self-Cleaning Mop");
        if (ReplicatedInfo.bSelfCleaningMop)
            RowUnlockedFlags.AddItem(1);
        else
            RowUnlockedFlags.AddItem(0);
        RowLabels.AddItem("Squeaky Clean Boots");
        if (ReplicatedInfo.bSqueakyBoots)
            RowUnlockedFlags.AddItem(1);
        else
            RowUnlockedFlags.AddItem(0);
    }

    // Every line shares the font size, so the heading's measured height sets
    // the row pitch and each label only competes on width.
    GetTextExtent(HeadingText, ToolPanelTextSize * RatioY, VCDFont,
        WidestText, TextHeight);
    RowHeight = TextHeight + 6.0 * RatioY;
    for (RowIndex = 0; RowIndex < RowLabels.Length; RowIndex++)
    {
        GetTextExtent(RowLabels[RowIndex], ToolPanelTextSize * RatioY, VCDFont,
            TextWidth, TextHeight);
        if (TextWidth > WidestText)
            WidestText = TextWidth;
    }

    PanelWidth = FMax(ToolPanelWidth * RatioY, WidestText + 12.0 * RatioY);
    PanelHeight = RowHeight * float(RowLabels.Length + 1) + 8.0 * RatioY;
    PanelLeft = Canvas.SizeX - PanelWidth - PanelSideMargin * RatioY;
    PanelTop = ToolPanelTop * RatioY;
    LabelLeft = PanelLeft + 6.0 * RatioY;
    HeadingTop = PanelTop + 4.0 * RatioY;

    DrawToolPanelBacking(PanelLeft, PanelTop, PanelWidth, PanelHeight);

    Canvas.SetDrawColor(255, 255, 255, 255);
    DrawTextEx(HeadingText, LabelLeft, HeadingTop,
        ToolPanelTextSize * RatioY, VCDFont, HA_Left, VA_Top, true);

    for (RowIndex = 0; RowIndex < RowLabels.Length; RowIndex++)
    {
        if (RowUnlockedFlags[RowIndex] != 0)
            Canvas.SetDrawColor(0, 255, 127, 255);
        else
            Canvas.SetDrawColor(128, 128, 128, 255);
        DrawTextEx(RowLabels[RowIndex], LabelLeft,
            HeadingTop + RowHeight * float(RowIndex + 1),
            ToolPanelTextSize * RatioY, VCDFont, HA_Left, VA_Top, true);
    }
}

// A translucent tile behind the panel so the list stays readable over the
// level, the same idiom the timed-effect bar uses.
function DrawToolPanelBacking(float Left, float Top, float Width, float Height)
{
    Canvas.SetDrawColor(0, 0, 0, 128);
    Canvas.SetPos(Left, Top);
    Canvas.DrawTile(Canvas.DefaultTexture, Width, Height, 0.0, 0.0, 32.0, 32.0);
}

function DrawHUD()
{
    local VCGameReplicationInfo_Archipelago ReplicatedInfo;
    local float ReadoutTop;

    super.DrawHUD();

    DrawToasts();

    ReplicatedInfo = VCGameReplicationInfo_Archipelago(VCGRI);
    if (ReplicatedInfo == None)
        return;

    DrawTimedEffects(ReplicatedInfo);

    if (!ReplicatedInfo.bCleanlinessSampled)
        return;

    // The speedrun timer takes the top-right band when the level's Speedrun
    // check is still outstanding; the cleanliness readout drops below it.
    ReadoutTop = 40.0 * RatioY;
    if (ReplicatedInfo.bSpeedrunOutstanding
        && ReplicatedInfo.PunchoutHandler != None
        && ReplicatedInfo.PunchoutHandler.CleanupTimeLimitGamePar > 0.0)
    {
        DrawSpeedrunTimer(ReplicatedInfo.PunchoutHandler);
        ReadoutTop = 72.0 * RatioY;
    }

    // Both lines share the Archipelago location green once every milestone on
    // the level is confirmed checked; white otherwise.
    if (ReplicatedInfo.NextMilestonePercent
        == class'VCGameReplicationInfo_Archipelago'.const.NextMilestoneCleared)
        Canvas.SetDrawColor(0, 255, 127, 255);
    else
        Canvas.SetDrawColor(255, 255, 255, 255);
    DrawTextEx(FormatCleanliness(ReplicatedInfo.CleanlinessHundredths),
        float(Canvas.SizeX - 4), ReadoutTop, 24.0 * RatioY, VCDFont,
        HA_Right, VA_Top, true);
    DrawTextEx(NextMilestoneLine(ReplicatedInfo.NextMilestonePercent),
        float(Canvas.SizeX - 4), ReadoutTop + 30.0 * RatioY, 24.0 * RatioY,
        VCDFont, HA_Right, VA_Top, true);
}

// Draws the base game's speedrun clock (H:MM:SS:CC, top-right, VCDFont) plus a
// par line, shown while the level's Speedrun check is unearned. The clock reads
// the handler's live CleanupTime (real seconds, client-simulated on guests).
// White normally, red once the dilated clock passes par, the point past which
// the check can no longer be earned. Splits the draw like the base HUD so the
// jittery centiseconds sit flush right without shifting the rest.
function DrawSpeedrunTimer(VCPunchoutHandler Handler)
{
    local float Elapsed, DigitsWidth, DigitsHeight;
    local string TimeString;

    Elapsed = Handler.CleanupTime;
    if (Elapsed >= 3600.0)
        TimeString = string((int(Elapsed) % 86400) / 3600) $ ":";
    else
        TimeString = "0:";
    if (Elapsed >= 60.0)
        TimeString $= GetDualDigit((int(Elapsed) % 3600) / 60) $ ":";
    else
        TimeString $= "00:";
    TimeString $= GetDualDigit(int(Elapsed) % 60) $ ":";

    if (Handler.CleanupTimeDilated > Handler.CleanupTimeLimitGamePar)
        Canvas.SetDrawColor(255, 0, 0, 255);
    else
        Canvas.SetDrawColor(255, 255, 255, 255);
    DrawTextEx(GetDualDigit(int(Elapsed * 100.0) % 100),
        float(Canvas.SizeX - 4), 4.0 * RatioY, 24.0 * RatioY, VCDFont,
        HA_Right, VA_Top, true);
    GetTextExtent("88", 24.0 * RatioY, VCDFont, DigitsWidth, DigitsHeight);
    DrawTextEx(TimeString, float(Canvas.SizeX - 4) - DigitsWidth,
        4.0 * RatioY, 24.0 * RatioY, VCDFont, HA_Right, VA_Top, true);

    Canvas.SetDrawColor(255, 128, 0, 255);
    DrawTextEx(FormatSpeedrunPar(Handler.CleanupTimeLimitGamePar) $ " Par",
        float(Canvas.SizeX - 4), 34.0 * RatioY, 18.0 * RatioY, VCDFont,
        HA_Right, VA_Top, true);
}

// "H:MM:SS" for the par line, the base game's format without centiseconds.
function string FormatSpeedrunPar(float Seconds)
{
    local string Text;

    if (Seconds >= 3600.0)
        Text = string((int(Seconds) % 86400) / 3600) $ ":";
    else
        Text = "0:";
    Text $= GetDualDigit((int(Seconds) % 3600) / 60) $ ":";
    return Text $ GetDualDigit(int(Seconds) % 60);
}

// The line under the readout: the lowest percent the server still misses for
// this level, a question mark before trustworthy same-seed data arrives, or
// the cleared text once every milestone is confirmed checked.
function string NextMilestoneLine(int NextPercent)
{
    if (NextPercent == class'VCGameReplicationInfo_Archipelago'.const.NextMilestoneCleared)
        return "All milestones cleared!";
    if (NextPercent == class'VCGameReplicationInfo_Archipelago'.const.NextMilestoneUnknown)
        return "Next milestone: ?";
    return "Next milestone: " $ NextPercent $ "%";
}

// Draws a countdown for every active timed trap effect, stacked downward from
// the top-center: a white label with the remaining minutes and seconds over a
// dim backing bar whose orange fill empties left to right and blinks through
// the final seconds. The text stays solid so the number remains readable.
function DrawTimedEffects(VCGameReplicationInfo_Archipelago ReplicatedInfo)
{
    local float Remaining, DrawY, BarLeft, BarY, FillFraction;
    local int SlotIndex, WholeSeconds;
    local bool bBlinkHidden;

    DrawY = 8.0 * RatioY;
    for (SlotIndex = 0; SlotIndex < ArrayCount(ReplicatedInfo.TimedEffectTypes); SlotIndex++)
    {
        if (ReplicatedInfo.TimedEffectTypes[SlotIndex]
            == class'VCGameReplicationInfo_Archipelago'.const.TimedEffectNone)
        {
            continue;
        }
        Remaining = ReplicatedInfo.TimedEffectEndTimes[SlotIndex] - WorldInfo.TimeSeconds;
        if (Remaining <= 0.0)
            continue;

        WholeSeconds = FCeil(Remaining);
        Canvas.SetDrawColor(255, 255, 255, 255);
        DrawTextEx(TimedEffectLabel(ReplicatedInfo.TimedEffectTypes[SlotIndex])
            $ " " $ (WholeSeconds / 60) $ ":" $ GetDualDigit(WholeSeconds % 60),
            float(Canvas.SizeX) / 2.0, DrawY, TimedEffectTextSize * RatioY, VCDFont,
            HA_Center, VA_Top, true);

        BarLeft = float(Canvas.SizeX) / 2.0 - (TimedEffectBarWidth / 2.0) * RatioY;
        BarY = DrawY + (TimedEffectTextSize + 6.0) * RatioY;
        Canvas.SetDrawColor(0, 0, 0, 96);
        Canvas.SetPos(BarLeft, BarY);
        Canvas.DrawTile(Canvas.DefaultTexture, TimedEffectBarWidth * RatioY,
            TimedEffectBarHeight * RatioY, 0.0, 0.0, 32.0, 32.0);

        bBlinkHidden = Remaining < TimedEffectBlinkSeconds
            && WorldInfo.TimeSeconds % 0.4 >= 0.2;
        if (!bBlinkHidden && ReplicatedInfo.TimedEffectDurations[SlotIndex] > 0.0)
        {
            FillFraction = FClamp(
                Remaining / ReplicatedInfo.TimedEffectDurations[SlotIndex], 0.0, 1.0);
            Canvas.SetDrawColor(255, 128, 0, 255);
            Canvas.SetPos(BarLeft, BarY);
            Canvas.DrawTile(Canvas.DefaultTexture,
                TimedEffectBarWidth * RatioY * FillFraction,
                TimedEffectBarHeight * RatioY, 0.0, 0.0, 32.0, 32.0);
        }

        DrawY += (TimedEffectTextSize + 6.0 + TimedEffectBarHeight + 8.0) * RatioY;
    }
}

// The display name for a timed effect type; an unknown type still counts down.
function string TimedEffectLabel(byte EffectType)
{
    if (EffectType == class'VCGameReplicationInfo_Archipelago'.const.TimedEffectSlowdown)
        return "Slowdown";
    if (EffectType == class'VCGameReplicationInfo_Archipelago'.const.TimedEffectSpeedup)
        return "Speedup";
    if (EffectType == class'VCGameReplicationInfo_Archipelago'.const.TimedEffectZeroGravity)
        return "Zero Gravity";
    return "Trap";
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

// Reads the feed fresh (config-style objects cache at startup; BasicLoadObject
// does not) and queues every entry above the highest index already queued. A
// changed session tag resets the counters: a fresh client session replays its
// own feed from the top, and another seed's leftovers never show.
function PollMessageFeed()
{
    local array<string> Entries;
    local int EntryIndex, ColonAt, I;

    if (MessageFeedFile == None)
        MessageFeedFile = new class'VCArchipelagoMessages';
    if (class'Engine'.static.BasicLoadObject(MessageFeedFile,
        "..\\..\\Saves\\VCArchipelagoMessages.sav", true, 1))
    {
        if (MessageFeedFile.SessionTag != MessageState.ShownSessionTag)
        {
            MessageState.ShownSessionTag = MessageFeedFile.SessionTag;
            MessageState.ShownIndex = 0;
            HighestQueuedIndex = 0;
            PendingToastTexts.Length = 0;
            PendingToastIndexes.Length = 0;
            VisibleToastTexts.Length = 0;
            VisibleToastExpiries.Length = 0;
            ToastHistory.Length = 0;
            bMessageStateDirty = true;
        }
        ParseStringIntoArray(MessageFeedFile.Messages, Entries, Chr(10), true);
        for (I = 0; I < Entries.Length; I++)
        {
            ColonAt = InStr(Entries[I], ":");
            if (ColonAt <= 0)
                continue;
            EntryIndex = int(Left(Entries[I], ColonAt));
            if (EntryIndex <= HighestQueuedIndex)
                continue;
            HighestQueuedIndex = EntryIndex;
            PendingToastTexts.AddItem(Mid(Entries[I], ColonAt + 1));
            PendingToastIndexes.AddItem(EntryIndex);
        }
    }
    SaveMessageStateIfDirty();
}

// Expires finished toasts and promotes at most one pending entry per tick.
// Expiry lives here, not in the draw, so a hidden HUD cannot pile up a wall of
// stale toasts. The shown index advances on display, so quitting mid-backlog
// re-shows only what was never on screen.
function PromotePendingToast()
{
    while (VisibleToastExpiries.Length > 0
        && VisibleToastExpiries[0] <= WorldInfo.TimeSeconds)
    {
        VisibleToastTexts.Remove(0, 1);
        VisibleToastExpiries.Remove(0, 1);
    }

    if (PendingToastTexts.Length == 0
        || VisibleToastTexts.Length >= MaxVisibleToasts)
        return;

    VisibleToastTexts.AddItem(PendingToastTexts[0]);
    VisibleToastExpiries.AddItem(WorldInfo.TimeSeconds + ToastLifetime);
    // Log every promoted line to the Tab history, newest last, capped.
    ToastHistory.AddItem(PendingToastTexts[0]);
    if (ToastHistory.Length > MaxHistoryToasts)
        ToastHistory.Remove(0, ToastHistory.Length - MaxHistoryToasts);
    MessageState.ShownIndex = PendingToastIndexes[0];
    bMessageStateDirty = true;
    PendingToastTexts.Remove(0, 1);
    PendingToastIndexes.Remove(0, 1);
    if (bMessageBeep && PlayerOwner != None)
        PlayerOwner.PlayBeepSound();
}

// The ini save is throttled to the poll tick; the defaults mirror keeps the
// next level's fresh state object current (an instance SaveConfig never
// updates the class defaults on its own).
function SaveMessageStateIfDirty()
{
    if (!bMessageStateDirty)
        return;
    bMessageStateDirty = false;
    class'VCArchipelagoMessageState'.default.ShownSessionTag = MessageState.ShownSessionTag;
    class'VCArchipelagoMessageState'.default.ShownIndex = MessageState.ShownIndex;
    MessageState.SaveConfig();
}

// Draws the visible toasts under the engine's console-message region (join and
// chat lines stack upward from that anchor; toasts stack downward from one
// line below it), in the same small engine font, each segment in its own
// color with a drop shadow.
function DrawToasts()
{
    local float XStart, MaxRight, BottomLimit, LineHeight;
    local float DrawX, DrawY, CharWidth;
    local array<string> Segments;
    local int ToastIndex, SegmentIndex;

    if (VisibleToastTexts.Length == 0)
        return;

    // The medium font, scaled a touch down, reads a step larger than the
    // small one the join and chat lines use, without crowding the left third
    // the toasts cap at.
    Canvas.Font = class'Engine.Engine'.static.GetMediumFont();
    Canvas.TextSize("A", CharWidth, LineHeight, ToastFontScale, ToastFontScale);

    XStart = ((1.0 - HudCanvasScale) / 2.0) * Canvas.SizeX
        + ConsoleMessagePosX * HudCanvasScale * Canvas.SizeX;
    DrawY = ((1.0 - HudCanvasScale) / 2.0) * Canvas.SizeY
        + ConsoleMessagePosY * HudCanvasScale * Canvas.SizeY
        + LineHeight;
    MaxRight = XStart + 0.4 * Canvas.SizeX;
    BottomLimit = Canvas.SizeY - ((1.0 - HudCanvasScale) / 2.0) * Canvas.SizeY;
    // The console anchor can sit low enough that the downward stack clips
    // after a few lines. Lift the start so the full visible cap fits above
    // the bottom, while never dropping the start into the top margin.
    if (DrawY > BottomLimit - float(MaxVisibleToasts) * LineHeight)
        DrawY = FMax(LineHeight,
            BottomLimit - float(MaxVisibleToasts) * LineHeight);

    for (ToastIndex = 0; ToastIndex < VisibleToastTexts.Length; ToastIndex++)
    {
        if (DrawY + LineHeight > BottomLimit)
            break;
        DrawX = XStart;
        ParseStringIntoArray(VisibleToastTexts[ToastIndex], Segments, Chr(9), true);
        for (SegmentIndex = 0; SegmentIndex < Segments.Length; SegmentIndex++)
        {
            if (Len(Segments[SegmentIndex]) <= 6)
                continue;
            DrawToastSegment(Mid(Segments[SegmentIndex], 6),
                HexToColor(Left(Segments[SegmentIndex], 6)),
                DrawX, DrawY, XStart, MaxRight, LineHeight);
        }
        DrawY += LineHeight;
    }
}

// The Tab scrollback: the most recent promoted toast lines, newest at the
// bottom of the left column, bottom-anchored to the screen edge so the
// newest lines always show and older lines drop first. The tool panel sits
// on the right, so the whole column is available; its top stops under the
// centered scoreboard box, whose lines reach into this column's width. A
// measure pass charges each entry its wrapped row count, so the block
// anchors exactly. Same colored-segment draw as the live toasts.
function DrawToastHistoryPanel()
{
    local float XStart, MaxRight, LineHeight, CharWidth;
    local float PanelTop, TopLimit, BottomLimit, DrawX, DrawY;
    local int RowBudget, RowsUsed, EntryRows, First, I, SegmentIndex;
    local array<string> Segments;
    local Color HeadingColor;

    if (ToastHistory.Length == 0)
        return;

    Canvas.Font = class'Engine.Engine'.static.GetMediumFont();
    Canvas.TextSize("A", CharWidth, LineHeight, ToastFontScale, ToastFontScale);

    XStart = PanelSideMargin * RatioY;
    MaxRight = XStart + 0.4 * Canvas.SizeX;
    BottomLimit = Canvas.SizeY - 24.0 * RatioY;

    // The scoreboard box bottom (heading band, rows, and the soft edge tile
    // below them, 148 in the stock pre-ratio units) plus an 8-unit gap.
    TopLimit = ToolPanelTop * RatioY;
    if (VCGRI != None)
        TopLimit = FMax(TopLimit,
            (156.0 + 26.0 * float(VCGRI.PRIArray.Length)) * RatioY);

    // A heading row plus the entry rows must fit between the limits.
    RowBudget = int((BottomLimit - TopLimit) / LineHeight) - 1;
    if (RowBudget < 1)
        return;

    // Walk newest to oldest, charging each entry its wrapped rows, until the
    // budget or the display cap runs out.
    First = ToastHistory.Length;
    RowsUsed = 0;
    while (First > 0 && ToastHistory.Length - First < MaxHistoryToasts)
    {
        EntryRows = MeasureToastRows(ToastHistory[First - 1], XStart, MaxRight,
            LineHeight);
        if (RowsUsed + EntryRows > RowBudget)
            break;
        RowsUsed += EntryRows;
        First--;
    }
    // The newest entry alone can outsize the budget; show it clipped at the
    // bottom rather than show nothing.
    if (First == ToastHistory.Length)
    {
        First--;
        RowsUsed = RowBudget;
    }

    PanelTop = BottomLimit - float(RowsUsed + 1) * LineHeight;

    HeadingColor.R = 255;
    HeadingColor.G = 255;
    HeadingColor.B = 255;
    HeadingColor.A = 255;
    DrawShadowedText("Recent Archipelago activity", HeadingColor, XStart, PanelTop);

    DrawY = PanelTop + LineHeight;
    for (I = First; I < ToastHistory.Length; I++)
    {
        // The measure pass sizes the block, so this guard only trips on the
        // clipped single-entry case.
        if (DrawY + LineHeight > BottomLimit)
            break;
        DrawX = XStart;
        ParseStringIntoArray(ToastHistory[I], Segments, Chr(9), true);
        for (SegmentIndex = 0; SegmentIndex < Segments.Length; SegmentIndex++)
        {
            if (Len(Segments[SegmentIndex]) <= 6)
                continue;
            DrawToastSegment(Mid(Segments[SegmentIndex], 6),
                HexToColor(Left(Segments[SegmentIndex], 6)),
                DrawX, DrawY, XStart, MaxRight, LineHeight);
        }
        DrawY += LineHeight;
    }
}

// Counts the rows one history line occupies after soft-wrapping, running the
// segment cursor in measure-only mode so the count always matches the draw.
// Expects the caller to have set the toast font on the canvas.
function int MeasureToastRows(string HistoryLine, float XStart, float MaxRight,
    float LineHeight)
{
    local array<string> Segments;
    local int SegmentIndex;
    local float DrawX, DrawY;
    local Color UnusedColor;

    DrawX = XStart;
    ParseStringIntoArray(HistoryLine, Segments, Chr(9), true);
    for (SegmentIndex = 0; SegmentIndex < Segments.Length; SegmentIndex++)
    {
        if (Len(Segments[SegmentIndex]) <= 6)
            continue;
        DrawToastSegment(Mid(Segments[SegmentIndex], 6), UnusedColor,
            DrawX, DrawY, XStart, MaxRight, LineHeight, true);
    }
    // DrawY accumulates float additions of LineHeight, so round before
    // truncating or ulp drift can undercount a wrapped row.
    return int(DrawY / LineHeight + 0.5) + 1;
}

// Draws one colored segment at the running cursor, soft-wrapping at MaxRight
// back to XStart. Prefers a space break; a spaceless overlong piece wraps to
// its own line first and hard-breaks only when even a fresh line cannot hold
// it. Leaves the cursor after the last character drawn. Measure-only mode
// runs the same cursor without drawing, so a height count matches the draw.
function DrawToastSegment(string Text, Color SegmentColor, out float DrawX,
    out float DrawY, float XStart, float MaxRight, float LineHeight,
    optional bool bMeasureOnly)
{
    local string Remaining, Piece;
    local float PieceWidth, PieceHeight;
    local int BreakAt;

    Remaining = Text;
    while (Len(Remaining) > 0)
    {
        Piece = Remaining;
        Canvas.TextSize(Piece, PieceWidth, PieceHeight, ToastFontScale, ToastFontScale);
        while (DrawX + PieceWidth > MaxRight)
        {
            BreakAt = LastSpaceIn(Piece);
            if (BreakAt > 0)
                Piece = Left(Piece, BreakAt);
            else if (DrawX > XStart)
            {
                Piece = "";
                break;
            }
            else if (Len(Piece) > 1)
                Piece = Left(Piece, Len(Piece) - 1);
            else
                break;
            Canvas.TextSize(Piece, PieceWidth, PieceHeight, ToastFontScale, ToastFontScale);
        }
        if (Piece == "")
        {
            DrawX = XStart;
            DrawY += LineHeight;
            continue;
        }
        if (!bMeasureOnly)
            DrawShadowedText(Piece, SegmentColor, DrawX, DrawY);
        DrawX += PieceWidth;
        Remaining = Mid(Remaining, Len(Piece));
        if (Len(Remaining) > 0)
        {
            DrawX = XStart;
            DrawY += LineHeight;
            if (Left(Remaining, 1) == " ")
                Remaining = Mid(Remaining, 1);
        }
    }
}

function DrawShadowedText(string Text, Color TextColor, float DrawX, float DrawY)
{
    Canvas.SetDrawColor(0, 0, 0, TextColor.A);
    Canvas.SetPos(DrawX + 1.0, DrawY + 1.0);
    Canvas.DrawText(Text, false, ToastFontScale, ToastFontScale);
    Canvas.DrawColor = TextColor;
    Canvas.SetPos(DrawX, DrawY);
    Canvas.DrawText(Text, false, ToastFontScale, ToastFontScale);
}

function int LastSpaceIn(string Text)
{
    local int I, Last;

    Last = -1;
    for (I = 0; I < Len(Text); I++)
    {
        if (Mid(Text, I, 1) == " ")
            Last = I;
    }
    return Last;
}

// "AF99EF" to a Color; a malformed digit reads as zero rather than failing.
function Color HexToColor(string Hex)
{
    local Color OutColor;

    OutColor.R = HexByte(Mid(Hex, 0, 2));
    OutColor.G = HexByte(Mid(Hex, 2, 2));
    OutColor.B = HexByte(Mid(Hex, 4, 2));
    OutColor.A = 255;
    return OutColor;
}

function int HexByte(string Pair)
{
    return HexDigit(Left(Pair, 1)) * 16 + HexDigit(Mid(Pair, 1, 1));
}

function int HexDigit(string Digit)
{
    local int Value;

    Value = InStr("0123456789ABCDEF", Caps(Digit));
    if (Value < 0)
        return 0;
    return Value;
}
