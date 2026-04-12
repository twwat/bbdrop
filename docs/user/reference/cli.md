# CLI Reference

BBDrop includes a command-line interface for uploading galleries without the GUI. This is primarily useful when running from source.

## Usage

```bash
python bbdrop.py [OPTIONS] [FOLDER_PATHS...]
```

## Options

| Flag | Description | Default |
|------|-------------|---------|
| `folder_paths` | Paths to folders containing images | -- |
| `-v`, `--version` | Print version and exit | -- |
| `--gui` | Launch GUI mode | off |
| `--name NAME` | Gallery name | folder name |
| `--size {1,2,3,4,6}` | Thumbnail size: 1=100, 2=180, 3=250, 4=300, 6=150 | 3 |
| `--format {1,2,3,4}` | Thumbnail format: 1=fixed width, 2=proportional, 3=square, 4=fixed height | 2 |
| `--max-retries N` | Retry attempts for failed uploads | 3 |
| `--parallel N` | Simultaneous upload count | 4 |
| `--template`, `-t NAME` | BBCode template name | default |
| `--setup-secure` | Set up secure password storage (interactive) | -- |
| `--rename-unnamed` | Rename all unnamed galleries from previous uploads | -- |
| `--debug` | Print all log messages to console | off |
| `--install-context-menu` | Install Windows right-click menu entry | -- |
| `--remove-context-menu` | Remove Windows right-click menu entry | -- |

## Examples

```bash
# Upload a folder with default settings
python bbdrop.py /path/to/images

# Upload with a custom gallery name and template
python bbdrop.py /path/to/images --name "Gallery Name" --template "Forum Post"

# Launch the GUI
python bbdrop.py --gui

# Send a folder to a running GUI instance
python bbdrop.py --gui /path/to/gallery

# Upload with debug logging
python bbdrop.py /path/to/images --debug
```

## Windows context menu

Register a shell context menu entry so you can right-click any folder and select **Add to BBDrop**:

```bash
python bbdrop.py --install-context-menu
```

Remove it with:

```bash
python bbdrop.py --remove-context-menu
```

The context menu sends the folder path to the running BBDrop instance via IPC. If BBDrop is not running, it launches a new instance.
