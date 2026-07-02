# FromSave Manager

A save slot manager for PC games. Import your current save, load it back at any time, and organize slots into profiles.

---

## Supported games

The following games come pre-configured and will appear in the game dropdown automatically:

- Elden Ring
- Dark Souls Remastered
- Dark Souls II: Scholar of the First Sin
- Dark Souls III
- Sekiro: Shadows Die Twice
- Armored Core VI

Any other game can be added manually via **Settings > Add game**.

---

## Getting started

1. Open the app and select a game from the dropdown.
2. Go to **Settings** and set the save file path for that game.
3. Click **Import Save** to create your first slot.

---

## Manually importing existing saves

If you already have save files backed up somewhere, you can drop them straight into the `saves` folder and the app will detect them automatically without using the Import button.

### Where the saves folder is

The `saves` folder is in the **same folder as `FromSave.exe`**:

```
FromSave.exe
saves/
```

### Folder structure

```
saves/
└── <Game Name>/
    └── <Profile Name>/
        └── <Slot Name>/
            └── your_save_file
```

| Folder | What it becomes in the app |
|---|---|
| `<Game Name>` | Must match the game name exactly. Pre-configured games already have folders here. |
| `<Profile Name>` | The profile that appears in the Profile dropdown |
| `<Slot Name>` | The name of the save slot |
| `your_save_file` | Your actual save file, placed directly inside the slot folder |

### Elden Ring example

Elden Ring's save file is named `ER0000.sl2`.

Say you have two saves you want to import, one from your first playthrough and one from a randomizer run, and you want them in separate profiles.

Create this structure inside your `saves` folder:

```
saves/
└── Elden Ring/
    ├── Main/
    │   ├── First Clear/
    │   │   └── ER0000.sl2
    │   └── Before Malenia/
    │       └── ER0000.sl2
    └── Randomizer/
        ├── Start/
        │   └── ER0000.sl2
        └── Mountaintops/
            └── ER0000.sl2
```

Once copied in, open the app (or switch to a different game and back). Your profiles and slots will appear exactly as named above.

### Notes

- You do **not** need to create `meta.json` or `notes.txt`. The app generates them automatically on first load.
- The slot folder name is what you will see in the slot list, so name it something meaningful.
- Multiple save files in one slot folder are supported (for games with more than one save file).
- After copying files in, **switch to a different game and back** in the app to refresh the list, or restart the app.

---

## Practice Mode

Practice Mode locks a slot so the game can't overwrite it. When you enable it:

1. Select the slot you want to practice from.
2. Click the **Practice Mode** toggle (or use the checkbox in the slot detail panel).
3. The app immediately loads that slot into the game and then watches the save file. Any time the game tries to save, the app restores the slot, discarding the new data.

The game's current save is backed up before the overwrite. When you disable Practice Mode, that save is automatically restored, putting the game back to where it was before you started practicing.

To save progress normally again, disable Practice Mode before saving in-game. While Practice Mode is on, **Load Save** is blocked for that game.

> **Note:** Practice Mode may not work correctly on all games — behavior depends on how the game handles save files.

---

## Run Mode

Run Mode is designed for active playthroughs where you want safety backups without accidentally losing your current save. When enabled:

- **Load Save** and **Practice Mode** are both disabled, so the game save can't be overwritten while you're playing.
- The app automatically takes a rolling backup of the game's save file every 2 minutes, keeping the last 3 backups.

Toggle **Run Mode** on before starting a serious run and off when you're done. The backups are separate from your named slots and are not visible in the slot list, they act as a short-term safety net in case the game corrupts or deletes your save mid-session.

---

## Adding a new game

1. Open **Settings** and click **Add game**.
2. Enter the game name and select the save type (single file, multiple files, or folder).
3. Set the path to the game's save file or folder.
4. Click **Add**, then **Save**.

The game will appear in the dropdown and a folder for it will be created in `saves/` automatically.

---

## Icon attribution

App icon based on [Floppy disc icons](https://www.flaticon.com/free-icons/floppy-disc) by IYAHICON - Flaticon. Modified from the original.
