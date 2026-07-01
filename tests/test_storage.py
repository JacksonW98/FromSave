"""Tests for storage.py save management operations."""
import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest

import storage


@pytest.fixture(autouse=True)
def isolated_saves(tmp_path, monkeypatch):
    """Redirect SAVES_DIR to a temp directory so tests don't touch real saves."""
    monkeypatch.setattr(storage, "SAVES_DIR", tmp_path / "saves")
    monkeypatch.setattr(storage, "GAMES_FILE", tmp_path / "games.json")
    yield tmp_path


# ── helpers ──────────────────────────────────────────────────────────────────

def cfg_file(save_path: Path) -> storage.GameConfig:
    return storage.GameConfig(name="TestGame", save_path=str(save_path), save_mode="file")


def cfg_files(paths: list[Path]) -> storage.GameConfig:
    return storage.GameConfig(
        name="TestGame", save_path="", save_mode="files",
        save_paths=[str(p) for p in paths],
    )


def cfg_folder(save_path: Path) -> storage.GameConfig:
    return storage.GameConfig(name="TestGame", save_path=str(save_path), save_mode="folder")


def make_src_file(tmp_path: Path, name: str = "save.sav", content: str = "data") -> Path:
    p = tmp_path / name
    p.write_text(content)
    return p


def make_src_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "game_saves"
    folder.mkdir()
    (folder / "checkpoint.sav").write_text("checkpoint")
    (folder / "sub").mkdir()
    (folder / "sub" / "nested.dat").write_text("nested")
    return folder


# ── import_save ──────────────────────────────────────────────────────────────

class TestImportSave:
    def test_file_mode_copies_file(self, tmp_path):
        src = make_src_file(tmp_path, "ER0000.sl2", "save data")
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_file(src))

        assert (slot.path / "ER0000.sl2").read_text() == "save data"
        assert slot.save_file == "ER0000.sl2"

    def test_file_mode_creates_meta_and_notes(self, tmp_path):
        src = make_src_file(tmp_path)
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_file(src))

        assert (slot.path / "meta.json").exists()
        assert (slot.path / "notes.txt").exists()
        assert slot.notes == ""

    def test_files_mode_copies_all_files(self, tmp_path):
        f1 = make_src_file(tmp_path, "save1.dat", "data1")
        f2 = make_src_file(tmp_path, "save2.dat", "data2")
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_files([f1, f2]))

        assert (slot.path / "save1.dat").read_text() == "data1"
        assert (slot.path / "save2.dat").read_text() == "data2"
        assert slot.save_file is None

    def test_files_mode_skips_missing_files(self, tmp_path):
        existing = make_src_file(tmp_path, "present.dat", "ok")
        missing = tmp_path / "absent.dat"
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_files([existing, missing]))

        assert (slot.path / "present.dat").exists()
        assert not (slot.path / "absent.dat").exists()

    def test_folder_mode_copies_tree(self, tmp_path):
        src_folder = make_src_folder(tmp_path)
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_folder(src_folder))

        assert (slot.path / "save_data" / "checkpoint.sav").read_text() == "checkpoint"
        assert (slot.path / "save_data" / "sub" / "nested.dat").read_text() == "nested"

    def test_raises_if_slot_already_exists(self, tmp_path):
        src = make_src_file(tmp_path)
        storage.import_save("TestGame", "default", "Slot1", cfg_file(src))
        with pytest.raises(FileExistsError):
            storage.import_save("TestGame", "default", "Slot1", cfg_file(src))

    def test_creates_nested_profile_dirs(self, tmp_path):
        src = make_src_file(tmp_path)
        slot = storage.import_save("TestGame", "deep/profile", "Slot1", cfg_file(src))
        assert slot.path.parent.name == "profile"

    def test_returns_slot_with_correct_fields(self, tmp_path):
        src = make_src_file(tmp_path)
        before = datetime.now()
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_file(src))

        assert slot.name == "Slot1"
        assert slot.game == "TestGame"
        assert slot.profile == "default"
        assert slot.date_created >= before
        assert slot.date_modified >= before


# ── replace_save ─────────────────────────────────────────────────────────────

class TestReplaceSave:
    def test_file_mode_overwrites(self, tmp_path):
        src = make_src_file(tmp_path, content="original")
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_file(src))
        src.write_text("updated")

        storage.replace_save(slot, cfg_file(src))

        assert (slot.path / "save.sav").read_text() == "updated"

    def test_files_mode_overwrites_all(self, tmp_path):
        f1 = make_src_file(tmp_path, "a.dat", "orig1")
        f2 = make_src_file(tmp_path, "b.dat", "orig2")
        game_cfg = cfg_files([f1, f2])
        slot = storage.import_save("TestGame", "default", "Slot1", game_cfg)
        f1.write_text("new1")
        f2.write_text("new2")

        storage.replace_save(slot, game_cfg)

        assert (slot.path / "a.dat").read_text() == "new1"
        assert (slot.path / "b.dat").read_text() == "new2"

    def test_folder_mode_replaces_tree(self, tmp_path):
        src_folder = make_src_folder(tmp_path)
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_folder(src_folder))
        (src_folder / "checkpoint.sav").write_text("replaced")
        (src_folder / "extra.sav").write_text("new file")

        storage.replace_save(slot, cfg_folder(src_folder))

        assert (slot.path / "save_data" / "checkpoint.sav").read_text() == "replaced"
        assert (slot.path / "save_data" / "extra.sav").read_text() == "new file"

    def test_updates_modified_timestamp(self, tmp_path):
        src = make_src_file(tmp_path)
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_file(src))
        original_modified = slot.date_modified

        storage.replace_save(slot, cfg_file(src))

        assert slot.date_modified >= original_modified

    def test_preserves_created_timestamp(self, tmp_path):
        src = make_src_file(tmp_path)
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_file(src))
        original_created = slot.date_created

        storage.replace_save(slot, cfg_file(src))

        meta = json.loads((slot.path / "meta.json").read_text())
        reloaded_created = datetime.fromisoformat(meta["created"])
        assert abs((reloaded_created - original_created).total_seconds()) < 1


# ── load_save ────────────────────────────────────────────────────────────────

class TestLoadSave:
    def test_file_mode_restores_to_game_path(self, tmp_path):
        src = make_src_file(tmp_path, content="save data")
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_file(src))
        src.write_text("CORRUPTED")

        storage.load_save(slot, cfg_file(src))

        assert src.read_text() == "save data"

    def test_files_mode_restores_each_file(self, tmp_path):
        f1 = make_src_file(tmp_path, "a.dat", "d1")
        f2 = make_src_file(tmp_path, "b.dat", "d2")
        game_cfg = cfg_files([f1, f2])
        slot = storage.import_save("TestGame", "default", "Slot1", game_cfg)
        f1.write_text("corrupted1")
        f2.write_text("corrupted2")

        storage.load_save(slot, game_cfg)

        assert f1.read_text() == "d1"
        assert f2.read_text() == "d2"

    def test_files_mode_skips_missing_slot_files(self, tmp_path):
        f1 = make_src_file(tmp_path, "a.dat", "d1")
        f2 = make_src_file(tmp_path, "b.dat", "d2")
        game_cfg = cfg_files([f1, f2])
        slot = storage.import_save("TestGame", "default", "Slot1", game_cfg)
        (slot.path / "b.dat").unlink()  # remove from slot
        f2.write_text("corrupted2")

        storage.load_save(slot, game_cfg)

        assert f1.read_text() == "d1"
        assert f2.read_text() == "corrupted2"  # b.dat not restored

    def test_folder_mode_replaces_game_folder(self, tmp_path):
        src_folder = make_src_folder(tmp_path)
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_folder(src_folder))
        shutil.rmtree(src_folder)

        storage.load_save(slot, cfg_folder(src_folder))

        assert (src_folder / "checkpoint.sav").read_text() == "checkpoint"
        assert (src_folder / "sub" / "nested.dat").read_text() == "nested"


# ── delete_slot ──────────────────────────────────────────────────────────────

class TestDeleteSlot:
    def test_hard_delete_removes_directory(self, tmp_path):
        src = make_src_file(tmp_path)
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_file(src))
        slot_path = slot.path

        storage.delete_slot(slot, soft=False)

        assert not slot_path.exists()

    def test_hard_delete_leaves_other_slots(self, tmp_path):
        src = make_src_file(tmp_path)
        slot1 = storage.import_save("TestGame", "default", "Slot1", cfg_file(src))
        slot2 = storage.import_save("TestGame", "default", "Slot2", cfg_file(src))

        storage.delete_slot(slot1, soft=False)

        assert not slot1.path.exists()
        assert slot2.path.exists()

    def test_soft_delete_removes_from_original_path(self, tmp_path):
        src = make_src_file(tmp_path)
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_file(src))
        slot_path = slot.path

        storage.delete_slot(slot, soft=True)

        assert not slot_path.exists()


# ── rename_slot ──────────────────────────────────────────────────────────────

class TestRenameSlot:
    def test_renames_directory(self, tmp_path):
        src = make_src_file(tmp_path)
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_file(src))
        original_path = slot.path

        storage.rename_slot(slot, "RenamedSlot")

        assert not original_path.exists()
        assert slot.path.exists()

    def test_updates_slot_name_and_path(self, tmp_path):
        src = make_src_file(tmp_path)
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_file(src))

        storage.rename_slot(slot, "RenamedSlot")

        assert slot.name == "RenamedSlot"
        assert slot.path.name == "RenamedSlot"

    def test_preserves_file_contents(self, tmp_path):
        src = make_src_file(tmp_path, content="precious save")
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_file(src))

        storage.rename_slot(slot, "RenamedSlot")

        assert (slot.path / "save.sav").read_text() == "precious save"

    def test_preserves_notes(self, tmp_path):
        src = make_src_file(tmp_path)
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_file(src))
        storage.save_notes(slot, "don't lose me")

        storage.rename_slot(slot, "RenamedSlot")

        assert (slot.path / "notes.txt").read_text() == "don't lose me"


# ── duplicate_slot ───────────────────────────────────────────────────────────

class TestDuplicateSlot:
    def test_creates_copy_in_same_profile(self, tmp_path):
        src = make_src_file(tmp_path, content="data")
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_file(src))

        duped = storage.duplicate_slot(slot, "Slot1 copy")

        assert duped.path.exists()
        assert duped.name == "Slot1 copy"
        assert duped.path.parent == slot.path.parent

    def test_original_still_exists(self, tmp_path):
        src = make_src_file(tmp_path)
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_file(src))

        storage.duplicate_slot(slot, "Slot1 copy")

        assert slot.path.exists()

    def test_copies_save_file_content(self, tmp_path):
        src = make_src_file(tmp_path, content="important save")
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_file(src))

        duped = storage.duplicate_slot(slot, "Slot1 copy")

        assert (duped.path / "save.sav").read_text() == "important save"

    def test_copies_notes(self, tmp_path):
        src = make_src_file(tmp_path)
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_file(src))
        storage.save_notes(slot, "my notes")

        duped = storage.duplicate_slot(slot, "Slot1 copy")

        assert duped.notes == "my notes"

    def test_gets_fresh_timestamps(self, tmp_path):
        src = make_src_file(tmp_path)
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_file(src))
        # meta.json stores to second precision; floor before to match
        before = datetime.now().replace(microsecond=0)

        duped = storage.duplicate_slot(slot, "Slot1 copy")

        assert duped.date_created >= before
        assert duped.date_modified >= before

    def test_folder_mode_duplicates_tree(self, tmp_path):
        src_folder = make_src_folder(tmp_path)
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_folder(src_folder))

        duped = storage.duplicate_slot(slot, "Slot1 copy")

        assert (duped.path / "save_data" / "checkpoint.sav").read_text() == "checkpoint"
        assert (duped.path / "save_data" / "sub" / "nested.dat").read_text() == "nested"


# ── copy_slot_to_profile ──────────────────────────────────────────────────────

class TestCopySlotToProfile:
    def test_copies_to_target_profile(self, tmp_path):
        src = make_src_file(tmp_path, content="data")
        slot = storage.import_save("TestGame", "profile_a", "Slot1", cfg_file(src))
        storage.create_profile("TestGame", "profile_b")

        copied = storage.copy_slot_to_profile(slot, "profile_b", "Slot1")

        assert copied.profile == "profile_b"
        assert (copied.path / "save.sav").read_text() == "data"

    def test_original_remains_in_source_profile(self, tmp_path):
        src = make_src_file(tmp_path)
        slot = storage.import_save("TestGame", "profile_a", "Slot1", cfg_file(src))
        storage.create_profile("TestGame", "profile_b")

        storage.copy_slot_to_profile(slot, "profile_b", "Slot1")

        assert slot.path.exists()
        assert slot.profile == "profile_a"

    def test_copies_notes(self, tmp_path):
        src = make_src_file(tmp_path)
        slot = storage.import_save("TestGame", "profile_a", "Slot1", cfg_file(src))
        storage.save_notes(slot, "important note")
        storage.create_profile("TestGame", "profile_b")

        copied = storage.copy_slot_to_profile(slot, "profile_b", "Slot1")

        assert copied.notes == "important note"

    def test_fresh_timestamps_on_copy(self, tmp_path):
        src = make_src_file(tmp_path)
        slot = storage.import_save("TestGame", "profile_a", "Slot1", cfg_file(src))
        storage.create_profile("TestGame", "profile_b")
        before = datetime.now().replace(microsecond=0)

        copied = storage.copy_slot_to_profile(slot, "profile_b", "Slot1")

        assert copied.date_created >= before

    def test_can_use_different_name_in_target(self, tmp_path):
        src = make_src_file(tmp_path)
        slot = storage.import_save("TestGame", "profile_a", "Slot1", cfg_file(src))
        storage.create_profile("TestGame", "profile_b")

        copied = storage.copy_slot_to_profile(slot, "profile_b", "SlotX")

        assert copied.name == "SlotX"

    def test_folder_mode_copies_tree(self, tmp_path):
        src_folder = make_src_folder(tmp_path)
        slot = storage.import_save("TestGame", "profile_a", "Slot1", cfg_folder(src_folder))
        storage.create_profile("TestGame", "profile_b")

        copied = storage.copy_slot_to_profile(slot, "profile_b", "Slot1")

        assert (copied.path / "save_data" / "checkpoint.sav").read_text() == "checkpoint"


# ── profile management ────────────────────────────────────────────────────────

class TestProfileManagement:
    def test_create_profile(self):
        storage.create_profile("TestGame", "TestProfile")
        assert "TestProfile" in storage.load_profiles("TestGame")

    def test_create_duplicate_profile_raises(self):
        storage.create_profile("TestGame", "TestProfile")
        with pytest.raises(FileExistsError):
            storage.create_profile("TestGame", "TestProfile")

    def test_rename_profile(self):
        storage.create_profile("TestGame", "OldName")
        storage.rename_profile("TestGame", "OldName", "NewName")
        profiles = storage.load_profiles("TestGame")
        assert "NewName" in profiles
        assert "OldName" not in profiles

    def test_rename_preserves_slots(self, tmp_path):
        src = make_src_file(tmp_path)
        storage.import_save("TestGame", "OldProfile", "Slot1", cfg_file(src))
        storage.rename_profile("TestGame", "OldProfile", "NewProfile")
        slots = storage.load_slots("TestGame", "NewProfile")
        assert any(s.name == "Slot1" for s in slots)

    def test_delete_profile(self):
        storage.create_profile("TestGame", "ToDelete")
        storage.delete_profile("TestGame", "ToDelete")
        assert "ToDelete" not in storage.load_profiles("TestGame")

    def test_delete_profile_removes_from_original_path(self, tmp_path):
        src = make_src_file(tmp_path)
        storage.import_save("TestGame", "ToDelete", "Slot1", cfg_file(src))
        profile_path = storage.SAVES_DIR / "TestGame" / "ToDelete"
        storage.delete_profile("TestGame", "ToDelete")
        assert not profile_path.exists()

    def test_load_profiles_sorted(self):
        storage.create_profile("TestGame", "Zebra")
        storage.create_profile("TestGame", "Alpha")
        storage.create_profile("TestGame", "Mango")
        profiles = storage.load_profiles("TestGame")
        assert profiles == sorted(profiles)

    def test_load_profiles_empty_when_game_missing(self):
        assert storage.load_profiles("NoGame") == []


# ── slot naming helpers ───────────────────────────────────────────────────────

class TestAutoSlotName:
    def test_returns_new_save_when_unused(self):
        storage.create_profile("TestGame", "default")
        assert storage.auto_slot_name("TestGame", "default") == "new save"

    def test_increments_when_base_taken(self, tmp_path):
        src = make_src_file(tmp_path)
        storage.import_save("TestGame", "default", "new save", cfg_file(src))
        assert storage.auto_slot_name("TestGame", "default") == "new save 2"

    def test_increments_past_existing_numbers(self, tmp_path):
        src = make_src_file(tmp_path)
        storage.import_save("TestGame", "default", "new save", cfg_file(src))
        storage.import_save("TestGame", "default", "new save 2", cfg_file(src))
        assert storage.auto_slot_name("TestGame", "default") == "new save 3"


class TestDuplicateSlotName:
    def test_first_copy(self, tmp_path):
        src = make_src_file(tmp_path)
        storage.import_save("TestGame", "default", "Boss Fight", cfg_file(src))
        name = storage.duplicate_slot_name("TestGame", "default", "Boss Fight")
        assert name == "Boss Fight copy"

    def test_second_copy_when_first_exists(self, tmp_path):
        src = make_src_file(tmp_path)
        storage.import_save("TestGame", "default", "Boss Fight", cfg_file(src))
        storage.import_save("TestGame", "default", "Boss Fight copy", cfg_file(src))
        name = storage.duplicate_slot_name("TestGame", "default", "Boss Fight")
        assert name == "Boss Fight copy 2"

    def test_third_copy(self, tmp_path):
        src = make_src_file(tmp_path)
        storage.import_save("TestGame", "default", "Run", cfg_file(src))
        storage.import_save("TestGame", "default", "Run copy", cfg_file(src))
        storage.import_save("TestGame", "default", "Run copy 2", cfg_file(src))
        name = storage.duplicate_slot_name("TestGame", "default", "Run")
        assert name == "Run copy 3"


# ── load_slots ────────────────────────────────────────────────────────────────

class TestLoadSlots:
    def test_loads_all_slots(self, tmp_path):
        src = make_src_file(tmp_path)
        storage.import_save("TestGame", "default", "Slot1", cfg_file(src))
        storage.import_save("TestGame", "default", "Slot2", cfg_file(src))
        slots = storage.load_slots("TestGame", "default")
        names = {s.name for s in slots}
        assert {"Slot1", "Slot2"} <= names

    def test_returns_empty_for_missing_profile(self):
        assert storage.load_slots("NoGame", "NoProfile") == []

    def test_slot_has_correct_metadata(self, tmp_path):
        src = make_src_file(tmp_path)
        before = datetime.now().replace(microsecond=0)
        storage.import_save("TestGame", "default", "Slot1", cfg_file(src))

        [loaded] = storage.load_slots("TestGame", "default")

        assert loaded.name == "Slot1"
        assert loaded.game == "TestGame"
        assert loaded.profile == "default"
        assert loaded.date_created >= before

    def test_ignores_order_json_file(self, tmp_path):
        src = make_src_file(tmp_path)
        storage.import_save("TestGame", "default", "Slot1", cfg_file(src))
        storage.save_slot_order("TestGame", "default", ["Slot1"])
        slots = storage.load_slots("TestGame", "default")
        assert all(s.name != "order.json" for s in slots)


# ── save_notes ────────────────────────────────────────────────────────────────

class TestSaveNotes:
    def test_persists_notes_to_disk(self, tmp_path):
        src = make_src_file(tmp_path)
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_file(src))

        storage.save_notes(slot, "This is a note")

        [loaded] = storage.load_slots("TestGame", "default")
        assert loaded.notes == "This is a note"

    def test_updates_slot_object_in_place(self, tmp_path):
        src = make_src_file(tmp_path)
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_file(src))

        storage.save_notes(slot, "Updated")

        assert slot.notes == "Updated"

    def test_overwrites_existing_notes(self, tmp_path):
        src = make_src_file(tmp_path)
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_file(src))
        storage.save_notes(slot, "First note")
        storage.save_notes(slot, "Second note")

        [loaded] = storage.load_slots("TestGame", "default")
        assert loaded.notes == "Second note"


# ── slot order ────────────────────────────────────────────────────────────────

class TestSlotOrder:
    def test_saves_and_loads_order(self):
        storage.create_profile("TestGame", "default")
        order = ["SlotC", "SlotA", "SlotB"]
        storage.save_slot_order("TestGame", "default", order)
        assert storage.load_slot_order("TestGame", "default") == order

    def test_returns_empty_list_when_no_order_file(self):
        storage.create_profile("TestGame", "default")
        assert storage.load_slot_order("TestGame", "default") == []

    def test_overwrites_existing_order(self):
        storage.create_profile("TestGame", "default")
        storage.save_slot_order("TestGame", "default", ["A", "B"])
        storage.save_slot_order("TestGame", "default", ["B", "A"])
        assert storage.load_slot_order("TestGame", "default") == ["B", "A"]


# ── manually-added saves (no meta.json) ──────────────────────────────────────

class TestManuallyAddedSaves:
    """Verify behaviour when the user drops files into the saves folder by hand."""

    def _make_slot_dir(self) -> Path:
        """Return the profile dir, creating it on disk."""
        profile_dir = storage.SAVES_DIR / "TestGame" / "default"
        profile_dir.mkdir(parents=True, exist_ok=True)
        return profile_dir

    def test_file_mode_detected(self):
        profile_dir = self._make_slot_dir()
        slot_dir = profile_dir / "ManualSlot"
        slot_dir.mkdir()
        (slot_dir / "ER0000.sl2").write_text("save data")

        [slot] = storage.load_slots("TestGame", "default")

        assert slot.name == "ManualSlot"
        assert slot.save_file == "ER0000.sl2"

    def test_file_mode_creates_meta_on_first_load(self):
        profile_dir = self._make_slot_dir()
        slot_dir = profile_dir / "ManualSlot"
        slot_dir.mkdir()
        (slot_dir / "save.sav").write_text("data")

        storage.load_slots("TestGame", "default")

        assert (slot_dir / "meta.json").exists()

    def test_file_mode_date_created_from_file_stat(self):
        profile_dir = self._make_slot_dir()
        slot_dir = profile_dir / "ManualSlot"
        slot_dir.mkdir()
        save_file = slot_dir / "save.sav"
        before = datetime.now().replace(microsecond=0)
        save_file.write_text("data")

        [slot] = storage.load_slots("TestGame", "default")

        # date_created should come from the file's ctime (creation time on Windows),
        # not from when load_slots was called
        assert slot.date_created is not None
        assert slot.date_created >= before

    def test_file_mode_date_modified_from_file_stat(self):
        profile_dir = self._make_slot_dir()
        slot_dir = profile_dir / "ManualSlot"
        slot_dir.mkdir()
        save_file = slot_dir / "save.sav"
        before = datetime.now().replace(microsecond=0)
        save_file.write_text("data")

        [slot] = storage.load_slots("TestGame", "default")

        assert slot.date_modified is not None
        assert slot.date_modified >= before

    def test_file_mode_meta_not_recreated_on_second_load(self):
        profile_dir = self._make_slot_dir()
        slot_dir = profile_dir / "ManualSlot"
        slot_dir.mkdir()
        (slot_dir / "save.sav").write_text("data")

        storage.load_slots("TestGame", "default")
        first_meta = (slot_dir / "meta.json").read_text()
        storage.load_slots("TestGame", "default")
        second_meta = (slot_dir / "meta.json").read_text()

        assert first_meta == second_meta

    def test_folder_mode_detected(self):
        profile_dir = self._make_slot_dir()
        slot_dir = profile_dir / "ManualSlot"
        slot_dir.mkdir()
        save_data = slot_dir / "save_data"
        save_data.mkdir()
        (save_data / "checkpoint.sav").write_text("data")

        [slot] = storage.load_slots("TestGame", "default")

        assert slot.name == "ManualSlot"
        assert slot.save_file is None  # folder mode has no single save_file

    def test_folder_mode_date_is_load_time(self):
        """Folder-mode slots with no meta.json fall back to datetime.now() since
        there's no single file to stat. date_created reflects first-load time."""
        profile_dir = self._make_slot_dir()
        slot_dir = profile_dir / "ManualSlot"
        slot_dir.mkdir()
        (slot_dir / "save_data").mkdir()
        (slot_dir / "save_data" / "data.sav").write_text("data")

        before = datetime.now().replace(microsecond=0)
        [slot] = storage.load_slots("TestGame", "default")

        assert slot.date_created >= before

    def test_files_mode_multiple_files_detected(self):
        profile_dir = self._make_slot_dir()
        slot_dir = profile_dir / "ManualSlot"
        slot_dir.mkdir()
        (slot_dir / "save1.dat").write_text("d1")
        (slot_dir / "save2.dat").write_text("d2")

        [slot] = storage.load_slots("TestGame", "default")

        # save_file will be set to whichever file is found first
        assert slot.save_file is not None
        assert (slot.path / slot.save_file).exists()

    def test_empty_dir_without_meta_is_ignored(self):
        profile_dir = self._make_slot_dir()
        (profile_dir / "EmptyDir").mkdir()

        slots = storage.load_slots("TestGame", "default")

        assert slots == []

    def test_notes_file_created_if_missing(self):
        profile_dir = self._make_slot_dir()
        slot_dir = profile_dir / "ManualSlot"
        slot_dir.mkdir()
        (slot_dir / "save.sav").write_text("data")

        [slot] = storage.load_slots("TestGame", "default")

        assert (slot_dir / "notes.txt").exists()
        assert slot.notes == ""

    def test_manual_slot_usable_after_detection(self, tmp_path):
        """A manually-added slot should work with load_save once detected."""
        src = make_src_file(tmp_path, "save.sav", "original data")

        # Manually place save into slot dir (simulating user dropping it in)
        profile_dir = self._make_slot_dir()
        slot_dir = profile_dir / "ManualSlot"
        slot_dir.mkdir()
        shutil.copy2(src, slot_dir / "save.sav")

        [slot] = storage.load_slots("TestGame", "default")
        src.write_text("CORRUPTED")
        storage.load_save(slot, cfg_file(src))

        assert src.read_text() == "original data"


# ── load backups ──────────────────────────────────────────────────────────────

class TestLoadBackups:
    def _backup_dirs(self, game_name: str) -> list[Path]:
        backup_game = storage.SAVES_DIR / storage._BACKUPS_DIR_NAME / game_name
        if not backup_game.exists():
            return []
        return sorted(d for d in backup_game.iterdir() if d.is_dir())

    def test_backup_created_on_load(self, tmp_path):
        src = make_src_file(tmp_path, "save.sav", "live data")
        game_cfg = cfg_file(src)
        slot = storage.import_save("TestGame", "default", "Slot1", game_cfg)

        storage.load_save(slot, game_cfg)

        backups = self._backup_dirs("TestGame")
        assert len(backups) == 1
        assert (backups[0] / "save.sav").read_text() == "live data"

    def test_backup_contains_live_content_not_slot_content(self, tmp_path):
        src = make_src_file(tmp_path, "save.sav", "live v1")
        game_cfg = cfg_file(src)
        slot = storage.import_save("TestGame", "default", "Slot1", game_cfg)
        src.write_text("live v2")  # live save changed after import

        storage.load_save(slot, game_cfg)

        [backup] = self._backup_dirs("TestGame")
        assert (backup / "save.sav").read_text() == "live v2"

    def test_files_mode_backup(self, tmp_path):
        f1 = make_src_file(tmp_path, "a.dat", "d1")
        f2 = make_src_file(tmp_path, "b.dat", "d2")
        game_cfg = cfg_files([f1, f2])
        slot = storage.import_save("TestGame", "default", "Slot1", game_cfg)

        storage.load_save(slot, game_cfg)

        [backup] = self._backup_dirs("TestGame")
        assert (backup / "a.dat").read_text() == "d1"
        assert (backup / "b.dat").read_text() == "d2"

    def test_folder_mode_backup(self, tmp_path):
        src_folder = make_src_folder(tmp_path)
        game_cfg = cfg_folder(src_folder)
        slot = storage.import_save("TestGame", "default", "Slot1", game_cfg)

        storage.load_save(slot, game_cfg)

        [backup] = self._backup_dirs("TestGame")
        assert (backup / "save_data" / "checkpoint.sav").read_text() == "checkpoint"

    def test_keeps_only_last_3_backups(self, tmp_path):
        src = make_src_file(tmp_path, "save.sav", "data")
        game_cfg = cfg_file(src)
        slot = storage.import_save("TestGame", "default", "Slot1", game_cfg)

        for i in range(5):
            src.write_text(f"version {i}")
            storage.import_save("TestGame", "default", f"Slot{i+2}", game_cfg)
            storage.load_save(slot, game_cfg)

        backups = self._backup_dirs("TestGame")
        assert len(backups) == 3

    def test_oldest_backup_pruned_first(self, tmp_path):
        src = make_src_file(tmp_path, "save.sav", "v0")
        game_cfg = cfg_file(src)
        slot = storage.import_save("TestGame", "default", "Slot1", game_cfg)

        for i in range(4):
            src.write_text(f"v{i}")
            storage.import_save("TestGame", "default", f"Slot{i+2}", game_cfg)
            storage.load_save(slot, game_cfg)

        backups = self._backup_dirs("TestGame")
        assert len(backups) == 3
        # The remaining backups should contain v1, v2, v3 (v0 pruned)
        contents = sorted((b / "save.sav").read_text() for b in backups)
        assert contents == ["v1", "v2", "v3"]

    def test_no_backup_when_live_file_missing(self, tmp_path):
        src = make_src_file(tmp_path, "save.sav", "data")
        game_cfg = cfg_file(src)
        slot = storage.import_save("TestGame", "default", "Slot1", game_cfg)
        src.unlink()  # live save doesn't exist

        storage.load_save(slot, game_cfg)  # should not raise

        assert self._backup_dirs("TestGame") == []

    def test_no_backup_when_make_backup_false(self, tmp_path):
        src = make_src_file(tmp_path, "save.sav", "data")
        game_cfg = cfg_file(src)
        slot = storage.import_save("TestGame", "default", "Slot1", game_cfg)

        storage.load_save(slot, game_cfg, make_backup=False)

        assert self._backup_dirs("TestGame") == []


# ── video_url ────────────────────────────────────────────────────────────────

class TestVideoUrl:
    def test_save_and_load_video_url(self, tmp_path):
        src = make_src_file(tmp_path)
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_file(src))
        url = "https://youtu.be/dQw4w9WgXcQ"

        storage.save_video_url(slot, url)

        meta = json.loads((slot.path / "meta.json").read_text())
        assert meta["video_url"] == url
        assert slot.video_url == url

        reloaded = storage.load_slots("TestGame", "default")[0]
        assert reloaded.video_url == url

    def test_replace_save_preserves_video_url(self, tmp_path):
        src = make_src_file(tmp_path, content="original")
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_file(src))
        storage.save_video_url(slot, "https://vimeo.com/123")

        src.write_text("updated")
        storage.replace_save(slot, cfg_file(src))

        meta = json.loads((slot.path / "meta.json").read_text())
        assert meta["video_url"] == "https://vimeo.com/123"

    def test_clear_video_url(self, tmp_path):
        src = make_src_file(tmp_path)
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_file(src))
        storage.save_video_url(slot, "https://example.com/v.mp4")
        storage.save_video_url(slot, "")

        reloaded = storage.load_slots("TestGame", "default")[0]
        assert reloaded.video_url == ""

    def test_duplicate_slot_copies_video_url(self, tmp_path):
        src = make_src_file(tmp_path)
        slot = storage.import_save("TestGame", "default", "Slot1", cfg_file(src))
        storage.save_video_url(slot, "https://youtu.be/abc12345678")

        dup = storage.duplicate_slot(slot, "Slot1 copy")

        assert dup.video_url == "https://youtu.be/abc12345678"
