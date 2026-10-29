# Photos 0.1.3

Performance release of **Win11-like Photos app for Linux**, focused on old hardware and network folders.

## Faster

- **Opening an image is immediate.** The viewer appears with the requested file; the rest of its folder is listed in the background and added to the filmstrip and the previous/next arrows when ready. Before, every neighbouring image was opened for its metadata first. Measured with simulated network latency (5 ms per operation, folder of 400 images): 18.4 s -> 0.8 s.
- **Gallery metadata is cached and read in parallel.** Image sizes and capture dates are read by several threads at once and remembered in `~/.cache/photos/meta.sqlite3`, so reopening a big or remote folder no longer reopens every image (15.9 s -> 0.9 s in the same test; first scan 16.0 s -> 3.0 s). The cache is only a speed-up: it is safe to delete.
- **The Gallery shows items while it is still scanning.**
- Directory listings stat files in parallel; thumbnail cache files are written about 3x faster.

## Fixed

- An unreachable network folder no longer freezes the window: folder checks, the sidebar tree and the Information panel (DPI, bit depth, EXIF) no longer touch the disk on the interface thread.
- The Gallery could stay in the loading state if a scan failed, and late results could reach a window that was already closed.

## Verification

- New regression tests for the metadata cache, parallel scanning, instant opening and the absence of disk access on the interface thread run in CI and in the release workflow, together with the existing suites.
- Cold starts of the real app (no arguments, file, folder, `--slideshow`, `--edit`, dead network folder, missing file) open their window in about 0.3 s.

## Install or update

```bash
sudo -S -p '' apt install ./photos_0.1.3_all.deb
```

Verify the download with `sha256sum -c photos_0.1.3_all.deb.sha256`.

Licensed under Apache-2.0. No Microsoft code or assets are included.
