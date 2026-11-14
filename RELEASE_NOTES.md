# Photos 0.1.4

Feature release of **Win11-like Photos app for Linux**: choose the order of the previous/next arrows, and names are now sorted the way photos are numbered.

## New

- **Browsing order setting.** Settings now has *Browsing order* (name, date created or date modified) and *Browsing direction* (ascending or descending). It decides how the previous/next arrows, the filmstrip and the slideshow walk through a folder. The choice is remembered and applies at once to viewer windows that are already open, staying on the current photo.
- **Photo-style numbering for names.** Numbers in names count by value: `0, 1, 2, … 9, 10, 11, … 32` instead of `0, 1, 10, 11, … 19, 2, 20, …`. This also works for zero-padded names (`IMG_0009` before `IMG_0010`), names with several numbers (`Trip 2 day 9` before `Trip 2 day 10`) and copies (`foto.jpg`, `foto (1).jpg`, `foto (2).jpg`, `foto (10).jpg`). Case and accents are ignored. The Gallery's *Name* sort uses the same rule.
- The new settings are translated into all seven interface languages.

## Notes

- Opening a photo from the Gallery now follows the browsing order from Settings rather than the Gallery's own sort.
- *Date taken* is not offered for the arrows on purpose: it would require opening every image of the folder, which is slow on network shares. Created and modified come from the folder listing at no extra cost.
- Files named one by one on the command line keep the order they were typed.

## Verification

- New regression tests cover the natural order (including your 0–32 example), the setting, live reordering of open windows and the settings page. They run in CI and in the release workflow with the existing suites.
- Checked with the real app and real clicks in English, Portuguese, Arabic and Chinese: open `9.jpg`, step with the arrows (9 → 10 → 11 → 12), change the order in Settings, and watch the open window reorder.

## Install or update

```bash
sudo apt install ./photos_0.1.4_all.deb
```

Verify the download with `sha256sum -c photos_0.1.4_all.deb.sha256`.

Licensed under Apache-2.0. No Microsoft code or assets are included.
