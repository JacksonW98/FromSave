# FromSave Manager

A save slot manager for PC games. Import your current save, load it back at any time, and organise slots into profiles.

---

## Manually Importing Existing Saves

If you already have save files backed up somewhere, you can drop them straight into FromSave without using the app's Import button. The app will detect them automatically.

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
| `<Game Name>` | Must match the game name exactly as entered in Settings |
| `<Profile Name>` | The profile that appears in the Profile dropdown |
| `<Slot Name>` | The name of the save slot |
| `your_save_file` | Your actual save file, placed directly inside the slot folder |

---

### Elden Ring example

Elden Ring's save file is named `ER0000.sl2`.

Say you have two saves you want to import, one from your first playthrough and one from a randomiser run, and you want them in separate profiles.

Create this structure inside your `saves` folder:

```
saves/
└── Elden Ring/
    ├── Main/
    │   ├── First Clear/
    │   │   └── ER0000.sl2
    │   └── Before Malenia/
    │       └── ER0000.sl2
    └── Randomiser/
        ├── Start/
        │   └── ER0000.sl2
        └── Mountaintops/
            └── ER0000.sl2
```

Once copied in, open the app (or switch to a different game and back). Your profiles and slots will appear exactly as named above.

> **Important:** The game name folder (`Elden Ring`) must be spelled exactly the same as the game name in the app's Settings. Capitalisation and spacing matter.

---

### Notes

- You do **not** need to create `meta.json` or `notes.txt`. The app generates them automatically on first load.
- The slot folder name is what you will see in the slot list, so name it something meaningful.
- Multiple save files in one slot folder are supported (for games with more than one save file).
- After copying files in, **switch to a different game and back** in the app to refresh the list, or restart the app.

---

## Icon Attribution

App icon based on [Floppy disc icons](https://www.flaticon.com/free-icons/floppy-disc) by IYAHICON - Flaticon. Modified from the original.
