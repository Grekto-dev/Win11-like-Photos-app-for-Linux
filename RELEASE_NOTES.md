# Photos 0.1.1

Bug-fix release of **Win11-like Photos app for Linux**.

## Fixed

- Images opened from the file manager or another application now open in the viewer even when their file name has a temporary, missing or nonstandard extension. Previously, valid images such as `.xdp-…png…tmp-…` were rejected by the extension filter and the app opened the Gallery instead.
- Explicit file opening now checks image headers when the extension is unrecognized. Bulk gallery scans keep their existing extension filters to avoid probing unrelated files.

## Verification

- Regression tests cover temporary/hidden file names, missing and incorrect extensions, ordinary image navigation, and rejection of non-image/missing files.
- The regression suite runs in both CI and the release workflow alongside the library and translation tests.

## Install or update

```bash
sudo apt install ./photos_0.1.1_all.deb
```

Verify the download with `sha256sum -c photos_0.1.1_all.deb.sha256`.

Licensed under Apache-2.0. No Microsoft code or assets are included.
