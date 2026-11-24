# Photos 0.1.6

Bug-fix release of **Win11-like Photos app for Linux**: the window buttons are visible again on every desktop theme.

## Fixed

- **Missing minimize, maximize and close buttons.** With some GTK themes (for example a Windows 11 style theme such as `Mint-Y-Dark-Aqua-Win11`) the window buttons were invisible: the theme hides the stock buttons' image and paints the glyphs as a background image, which the app's own styling then cleared. The buttons were there and clickable, but nothing was drawn. This affected every earlier version.
- The app now draws its own window buttons in the Windows 11 style, so no desktop theme can hide them: 46 x 48 px, flush with the window edge, a restore icon when the window is maximized, a grey hover and a red close button with a white glyph. They are in the viewer and in the Gallery.
- Tooltips are translated into the seven interface languages. In right-to-left languages the buttons move to the left edge, with close at the edge.

## Verification

- New regression tests render the buttons under CSS that mimics that theme and check the drawn pixels, hover colours, the window actions, the restore icon, the translations and the Gallery window. They run in CI and in the release workflow.
- Checked on a real desktop with the affected theme: hover, maximize, restore, minimize, close and double-click on the title bar.

## Install or update

```bash
SUDO_ASKPASS="$__hermes_sudo_dir/a" sudo "${__hermes_sudo_o[@]}" apt install ./photos_0.1.6_all.deb
```

Verify the download with `sha256sum -c photos_0.1.6_all.deb.sha256`.

Licensed under Apache-2.0. No Microsoft code or assets are included.
