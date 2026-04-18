# Customize the layout

The BBDrop main window is built around a central **Upload Queue** with six dockable panels you can show, hide, rearrange, float, or tab together to suit your screen and workflow.

The Upload Queue itself stays in the center — only the surrounding panels move.

---

## The dockable panels

| Panel | Default position | What it shows |
|-------|------------------|---------------|
| **Quick Settings** | Right column, top | Image host, thumb size and format, template, action buttons |
| **Hosts** | Right column, middle | Image and file host workers with status |
| **Log** | Right column, bottom | Real-time log messages |
| **Current Tab Progress** | Bottom row, left | Overall progress bar and stats for the active tab |
| **Info** | Bottom row, center | Unnamed galleries, totals uploaded |
| **Speed** | Bottom row, right | Current speed, fastest speed, total transferred |

The default arrangement is called **Classic** and is what you see on first launch.

---

## Show or hide a panel

1. Open **View → Panels**.
2. Click the panel name to toggle its visibility.

A check mark next to the name indicates the panel is currently visible. Hiding a panel does not delete its state — re-opening it restores it to its previous position.

---

## Rearrange panels

Layout is locked by default so you cannot drag a panel out of place by accident. To rearrange:

1. Open **View → Edit Layout** to enter edit mode. A compact title bar appears at the top of every panel with a drag handle on the left and float and close buttons on the right.
2. Drag a panel by its title bar to a new position. Drop indicators show where the panel will land.
3. Open **View → Edit Layout** again to lock the layout when you are done.

In edit mode you can:

- **Move a panel** to any edge of the main window or beside another panel.
- **Float a panel** into its own window with the float button on the title bar (or by dragging it outside the main window).
- **Tab two panels together** by dropping one panel on top of another. Tabs appear at the bottom of the shared dock.
- **Hide a panel** with the close button on the title bar. Re-open it from **View → Panels**.

Locked mode hides the dock title bars entirely so the panels look flush against each other. The panel's own group title (such as "Quick Settings") remains visible inside the panel.

---

## Reset to the default layout

Open **View → Reset Layout** to restore the Classic arrangement: Quick Settings, Hosts, and Log stacked in a right column; Current Tab Progress, Info, and Speed across the bottom; the Upload Queue filling the center.

Reset Layout brings back any panels you have hidden and restores the default sizes.

---

## Layout persistence

BBDrop saves your layout automatically when you close the app and restores it the next time you launch. This includes:

- Which panels are visible
- Where each panel is docked, floated, or tabbed
- The size of each panel and splitter

You do not need to save manually. If a saved layout fails to restore — for example after a Qt update changes the dock-state format — BBDrop falls back to the Classic layout silently.

---

## Tips

- **Vertical monitor?** Hide the bottom row (Current Tab Progress, Info, Speed) and stack everything in a tall right column.
- **Wide monitor?** Float the Log panel into its own window on a second monitor.
- **Need only the queue?** Hide every panel from **View → Panels** to give the Upload Queue the full window.
- **Lost a panel?** Open **View → Panels** to find it, or use **View → Reset Layout** to start over.

---

See also:

- [GUI Guide](gui-guide.md) — Tour of the main window
- [Theme Customization](theme-customization.md) — Dark, light, and auto themes
- [Keyboard Shortcuts](../reference/keyboard-shortcuts.md) — Complete shortcut reference
