# Photos 0.1.2

Bug-fix release of **Win11-like Photos app for Linux**.

## Fixed

- Crop editor: the horizontal scrollbar of the aspect-ratio selector no longer appears as a wide gray band covering the ratio labels. The shared scrollbar style forced a 40 px minimum height on every scrollbar; thickness is now 4 px on both axes and the 40 px minimum length applies only along each bar's own direction.

## Verification

- New GTK regression tests (scrollbar thickness, row overflow, label overlap) run in CI and in the release workflow, together with the library, translation and file-opening tests.

## Install or update

```bash
sudo apt install ./photos_0.1.2_all.deb
```

Verify the download with `sha256sum -c photos_0.1.2_all.deb.sha256`.

Licensed under Apache-2.0. No Microsoft code or assets are included.
