// The Archipelago HUD: the stock HUD plus a live cleanliness readout and the
// Archipelago toast feed.
//
// The cleanliness readout draws in the top-right corner, below the band the
// multiplayer net-actors warning uses. It runs on the host and on co-op guests
// alike; the value arrives through the replicated GRI. The game's speedrun
// timer shares that corner but only draws in speedrun mode, which Archipelago
// never sets.
//
// Toasts show what Archipelago is doing: check sends, item receives, goal and
// connection lines. The feed file is written by this machine's own client and
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

simulated event PostBeginPlay()
{
    super.PostBeginPlay();
    MessageState = new class'VCArchipelagoMessageState';
    HighestQueuedIndex = MessageState.ShownIndex;
    SetTimer(MessagePollInterval, true, 'PollMessageFeed');
    SetTimer(ToastPromoteInterval, true, 'PromotePendingToast');
}

function DrawHUD()
{
    local VCGameReplicationInfo_Archipelago ReplicatedInfo;

    super.DrawHUD();

    DrawToasts();

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

    Canvas.Font = class'Engine.Engine'.static.GetSmallFont();
    Canvas.TextSize("A", CharWidth, LineHeight);

    XStart = ((1.0 - HudCanvasScale) / 2.0) * Canvas.SizeX
        + ConsoleMessagePosX * HudCanvasScale * Canvas.SizeX;
    DrawY = ((1.0 - HudCanvasScale) / 2.0) * Canvas.SizeY
        + ConsoleMessagePosY * HudCanvasScale * Canvas.SizeY
        + LineHeight;
    MaxRight = XStart + 0.4 * Canvas.SizeX;
    BottomLimit = Canvas.SizeY - ((1.0 - HudCanvasScale) / 2.0) * Canvas.SizeY;

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

// Draws one colored segment at the running cursor, soft-wrapping at MaxRight
// back to XStart. Prefers a space break; a spaceless overlong piece wraps to
// its own line first and hard-breaks only when even a fresh line cannot hold
// it. Leaves the cursor after the last character drawn.
function DrawToastSegment(string Text, Color SegmentColor, out float DrawX,
    out float DrawY, float XStart, float MaxRight, float LineHeight)
{
    local string Remaining, Piece;
    local float PieceWidth, PieceHeight;
    local int BreakAt;

    Remaining = Text;
    while (Len(Remaining) > 0)
    {
        Piece = Remaining;
        Canvas.TextSize(Piece, PieceWidth, PieceHeight);
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
            Canvas.TextSize(Piece, PieceWidth, PieceHeight);
        }
        if (Piece == "")
        {
            DrawX = XStart;
            DrawY += LineHeight;
            continue;
        }
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
    Canvas.DrawText(Text, false);
    Canvas.DrawColor = TextColor;
    Canvas.SetPos(DrawX, DrawY);
    Canvas.DrawText(Text, false);
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
