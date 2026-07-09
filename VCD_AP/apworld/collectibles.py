"""Collectibles and the Bob storyline, transcribed from the game data.

Sources (ground truth, not guessed): each map package's name table names the
placed ``VCSpecialDrop_*`` classes; the per-map punchout handlers and the
``GP_Notes_Arch`` package name the rest; display names come from the game's
``.int`` localization. Two drops spawn at runtime rather than being placed (the
Saber from the Digsite sand trap, the Cane Sheath from the Cane Sword) and are
confirmed by the spawning code. The Doom Armour and Shotgun (Item5 and Item6)
live in the Office stash behind the Red Keycard gate, not in any level, so they
are not locations.

Detection is the trunk: a collectible or Bob note banks when it sits in the
janitor's trunk at a punch-out in good standing (a fired punch-out clears the
trophies, per the game's own PostPunchout). The mod publishes each banked
item's token; tokens are unique across the whole game, so an item carried to
another level later still maps to its home location.

The Bob chain: six levels hold a Bob note (three more notes are Office
freebies). All nine notes on the Digsite pedestal open the gates
(bOpenedDigsiteGates), behind which sit Bob (bFoundBob) and the Red Keycard.
The gate check, the Find Bob check, and the Red Keycard collectible therefore
require access to the six note levels plus the Digsite; they are the only
checks that need more than their own level's access item. The Digsite's other
drops (the Bolter and the sand-trap Saber) sit in the open dig area, before
the gates.
"""

from __future__ import annotations

# (map_name, token, check_name). The token is the VCSpecialDrop class name the
# mod reports from the trunk scan.
COLLECTIBLES: list[tuple[str, str, str]] = [
    # Base game.
    ("VC_Jungle", "VCSpecialDrop_Item1", "Pickaxe"),
    ("VC_Cryo", "VCSpecialDrop_Item2", "Glasses"),
    ("VC_Cryo", "VCSpecialDrop_Item3", "Crowbar"),
    ("VC_Greenhouse", "VCSpecialDrop_Item4", "Helmet"),
    ("VC_Digsite", "VCSpecialDrop_Item7", "Bolter"),
    ("VC_ZeroG_New", "VCSpecialDrop_Item8", "Shades"),
    ("VC_ZeroG_New", "VCSpecialDrop_Item9", "Gum"),
    ("VC_MedBay", "VCSpecialDrop_Item10", "Hugger"),
    ("VC_Digsite", "VCSpecialDrop_Item11", "Red Keycard"),
    ("VC_Robot", "VCSpecialDrop_Item12", "Pill Case"),
    ("VC_Greenhouse", "VCSpecialDrop_Item13", "Easter Egg Green"),
    ("VC_Jungle", "VCSpecialDrop_Item14", "Easter Egg Red"),
    ("VC_Hall", "VCSpecialDrop_Item15", "Easter Egg Blue"),
    ("VC_Digsite", "VCSpecialDrop_Item16", "Saber"),
    # House of Horror.
    ("VC_Horror_01", "VCSpecialDrop_Horror_Item1", "Shimmering Axe"),
    ("VC_Horror_01", "VCSpecialDrop_Horror_Item2", "Boomstick"),
    ("VC_Horror_01", "VCSpecialDrop_Horror_Item3", "Chainsaw"),
    ("VC_Horror_01", "VCSpecialDrop_Horror_Item4", "Severed Hand"),
    ("VC_Horror_01", "VCSpecialDrop_Horror_Item5", "Necronomicon"),
    ("VC_Horror_01", "VCSpecialDrop_Horror_Item6", "Knife"),
    ("VC_Horror_01", "VCSpecialDrop_Horror_Item7", "Halloween Mask"),
    ("VC_Horror_01", "VCSpecialDrop_Horror_Item8", "Claw"),
    ("VC_Horror_01", "VCSpecialDrop_Horror_Item9", "Cthulhu Key"),
    ("VC_Horror_01", "VCSpecialDrop_Horror_Item10", "Machete"),
    ("VC_Horror_01", "VCSpecialDrop_Horror_Item11", "Hockey Mask"),
    ("VC_Horror_01", "VCSpecialDrop_Horror_Item12", "Ring"),
    ("VC_Horror_01", "VCSpecialDrop_Horror_Item13", "Cabin Key"),
    # The Vulcan Affair.
    ("VC_Vulcan_01", "VCSpecialDrop_Vulcan_Item1", "Bow-Tie"),
    ("VC_Vulcan_01", "VCSpecialDrop_Vulcan_Item2", "Bowler Hat"),
    ("VC_Vulcan_01", "VCSpecialDrop_Vulcan_Item3", "Golden Finger"),
    ("VC_Vulcan_01", "VCSpecialDrop_Vulcan_Item4", "Collar"),
    ("VC_Vulcan_01", "VCSpecialDrop_Vulcan_Item5", "Gun"),
    ("VC_Vulcan_01", "VCSpecialDrop_Vulcan_Item6", "Grappling Gun"),
    ("VC_Vulcan_01", "VCSpecialDrop_Vulcan_Item7", "Cane Sheath"),
    ("VC_Vulcan_01", "VCSpecialDrop_Vulcan_Item8", "Cane Sword"),
    ("VC_Vulcan_01", "VCSpecialDrop_Vulcan_Item9", "Mojo"),
    ("VC_Vulcan_01", "VCSpecialDrop_Vulcan_Item10", "Metal Teeth"),
    ("VC_Vulcan_01", "VCSpecialDrop_Vulcan_Item11", "Book"),
    ("VC_Vulcan_01", "VCSpecialDrop_Vulcan_Item12", "Cat Photo"),
]

# (map_name, token): the Bob note archetypes and the levels that hold them.
BOB_NOTES: list[tuple[str, str]] = [
    ("VC_Caduceus", "Note_Bob_Caduceus01"),
    ("VC_Cryo", "Note_Bob_Cryo01"),
    ("VC_Greenhouse", "Note_Bob_Greenhouse01"),
    ("VC_MedBay", "Note_Bob_Medbay01"),
    ("VC_Robot", "Note_Bob_Robot01"),
    ("VC_Sewer", "Note_Bob_Sewer01"),
]
BOB_NOTE_MAPS: list[str] = [m for m, _ in BOB_NOTES]

BOB_ALTAR_MAP = "VC_Digsite"

# Global stat keys the mod forwards when the Digsite Kismet fires them.
STAT_DIGSITE_GATES = "bOpenedDigsiteGates"
STAT_FOUND_BOB = "bFoundBob"

COLLECTIBLE_BY_TOKEN: dict[str, tuple[str, str]] = {
    token: (map_name, name) for map_name, token, name in COLLECTIBLES
}
BOB_NOTE_MAP_BY_TOKEN: dict[str, str] = {token: m for m, token in BOB_NOTES}

# Collectibles locked behind the Digsite gates, sharing the Bob events' rule.
GATED_COLLECTIBLE_TOKENS: frozenset[str] = frozenset({"VCSpecialDrop_Item11"})

# Collectibles that need a tool beyond the level's clean kit to reach or
# extract, by token. The clean kit is always implied (a trophy only banks on a
# not-fired punch-out, and its hands grab the item); these stack on top. The
# Overgrowth pickaxe is dug out with the shovel; Athena's Wrath's blue easter
# egg sits where only the J-HARM reaches. A token absent here needs only the
# clean kit.
COLLECTIBLE_EXTRA_TOOLS: dict[str, "frozenset[str]"] = {
    "VCSpecialDrop_Item1": frozenset({"Shovel"}),
    "VCSpecialDrop_Item15": frozenset({"Lift"}),
}
