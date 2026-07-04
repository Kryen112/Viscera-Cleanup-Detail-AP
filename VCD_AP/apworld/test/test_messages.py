"""Tests for the toast feed codec: the file layout the mod reads, segment
encoding and sanitization, the entry cap, and the session tag."""
import unittest

from .bases import read_sav_properties
from .. import messages


class TestFeedFile(unittest.TestCase):
    def test_layout_round_trips(self) -> None:
        entries = [
            messages.encode_entry(1, [(messages.WHITE, "Archipelago connected.")]),
            messages.encode_entry(2, [(messages.WHITE, "You sent "),
                                      ("AF99EF", "Mop Upgrade")]),
        ]
        data = messages.build("seed_1-abcd1234", entries)
        properties = read_sav_properties(data)
        self.assertEqual(properties["SessionTag"], "seed_1-abcd1234")
        self.assertEqual(properties["Messages"].split("\n"), [
            "1:FFFFFFArchipelago connected.",
            "2:FFFFFFYou sent \tAF99EFMop Upgrade",
        ])

    def test_only_the_newest_entries_are_kept(self) -> None:
        entries = [messages.encode_entry(index, [(messages.WHITE, "line")])
                   for index in range(1, messages.MAX_ENTRIES + 51)]
        data = messages.build("seed_1-tag", entries)
        kept = read_sav_properties(data)["Messages"].split("\n")
        self.assertEqual(len(kept), messages.MAX_ENTRIES)
        self.assertTrue(kept[0].startswith("51:"))
        self.assertTrue(kept[-1].startswith(f"{messages.MAX_ENTRIES + 50}:"))


class TestEncodeEntry(unittest.TestCase):
    def test_segments_join_with_tabs_behind_the_index(self) -> None:
        entry = messages.encode_entry(
            7, [("FAFAD2", "Bob"), (messages.WHITE, " sent you "),
                ("FA8072", "Slowdown Trap")])
        self.assertEqual(
            entry, "7:FAFAD2Bob\tFFFFFF sent you \tFA8072Slowdown Trap")

    def test_adjacent_same_color_segments_merge(self) -> None:
        entry = messages.encode_entry(
            1, [(messages.WHITE, "Goal "), (messages.WHITE, "complete.")])
        self.assertEqual(entry, "1:FFFFFFGoal complete.")

    def test_empty_segments_drop(self) -> None:
        entry = messages.encode_entry(
            1, [(messages.WHITE, ""), ("AF99EF", "Key")])
        self.assertEqual(entry, "1:AF99EFKey")

    def test_text_is_sanitized_to_printable_ascii(self) -> None:
        # Delimiters and non-ASCII in multiworld names must never corrupt the
        # feed: tab and newline flatten to spaces, non-ASCII reads as "?".
        entry = messages.encode_entry(
            3, [(messages.WHITE, "A\tB\nC"), ("AF99EF", "Zcézar")])
        self.assertEqual(entry, "3:FFFFFFA B C\tAF99EFZc?zar")


class TestPalette(unittest.TestCase):
    def test_item_color_precedence_matches_the_text_client(self) -> None:
        self.assertEqual(messages.item_color(0b001), "AF99EF")
        self.assertEqual(messages.item_color(0b011), "AF99EF")
        self.assertEqual(messages.item_color(0b010), "6D8BE8")
        self.assertEqual(messages.item_color(0b100), "FA8072")
        self.assertEqual(messages.item_color(0), "00EEEE")

    def test_named_color_takes_the_first_known_name(self) -> None:
        self.assertEqual(messages.named_color("bold;green"), "00FF7F")
        self.assertEqual(messages.named_color("salmon"), "FA8072")
        self.assertEqual(messages.named_color("not_a_color"), messages.WHITE)
        self.assertEqual(messages.named_color(""), messages.WHITE)


class TestSessionTag(unittest.TestCase):
    def test_tag_carries_the_seed_and_a_nonce(self) -> None:
        tag = messages.session_tag("seed_1")
        self.assertTrue(tag.startswith("seed_1-"))
        self.assertEqual(len(tag), len("seed_1-") + 8)

    def test_two_tags_differ(self) -> None:
        self.assertNotEqual(messages.session_tag("seed_1"),
                            messages.session_tag("seed_1"))

    def test_missing_seed_still_tags(self) -> None:
        self.assertTrue(messages.session_tag(None).startswith("unseeded-"))
