# Hooks & Automation

Hooks let you run external scripts or programs at key points in the gallery lifecycle. Combined with JSON key mappings, they create a pipeline where external tool output flows directly into your BBCode templates.

## Hook Events

Three events are available:

| Event | When It Fires |
|---|---|
| **On Gallery Added** | When a gallery is added to the queue |
| **On Gallery Started** | When a gallery upload begins |
| **On Gallery Completed** | When a gallery upload finishes successfully |

## Setting Up a Hook

Go to **Settings > Hooks** (or click the **App Hooks** button) and configure any of the three events.

### Command Builder

Each hook has a command template — a command line with `%` variables that get replaced with gallery data at runtime:

```
python my_script.py "%N" "%p" --images %C
```

**Available variables:**

| Variable | Description | Available |
|---|---|---|
| `%N` | Gallery name | All events |
| `%T` | Tab name | All events |
| `%p` | Gallery folder path | All events |
| `%C` | Number of images | All events |
| `%s` | Gallery size in bytes | All events |
| `%t` | Template name | All events |
| `%z` | ZIP archive path (created on demand) | All events |
| `%e1`-`%e4` | ext field values | All events |
| `%c1`-`%c4` | custom field values | All events |
| `%g` | Gallery ID | On Completed only |
| `%j` | JSON artifact path | On Completed only |
| `%b` | BBCode artifact path | On Completed only |

Use `%%` for a literal percent sign.

The **Insert % Variable** dropdown and live preview help you build commands. Click **Run Test Command** to test with sample data before saving.

!!! tip
    Always wrap `%` variables in quotes in your command template (e.g., `"%N"` not `%N`) to handle gallery names with spaces.

### Execution Mode

- **Parallel** — All hooks run simultaneously (default)
- **Sequential** — Hooks run one at a time in order

## JSON Key Mappings

This is where hooks become powerful. If your external program outputs JSON to stdout, BBDrop can map specific keys back into the gallery's ext fields.

### How It Works

1. Your script prints JSON to stdout:
   ```json
   {"download_url": "https://example.com/abc123", "file_id": "abc123"}
   ```

2. In the JSON Key Mappings section, map keys to ext fields:
   - **ext1** → `download_url`
   - **ext2** → `file_id`

3. BBDrop parses the JSON, extracts the values, and stores them in the gallery's ext1 and ext2 fields.

4. Those fields are now available in your BBCode templates as `#ext1#` and `#ext4#`:
   ```bbcode
   [if ext1]Download: [url=#ext1#]Link[/url][/if]
   ```

### Testing

When you click **Run Test Command**, the output panel shows:

- **Left side** — Parsed JSON in a table format (if valid JSON detected)
- **Right side** — Raw stdout/stderr output

BBDrop can auto-detect URLs, file paths, and IDs in the output and suggest mappings.

## Console Options

- **Show console window when executing** — Display a command window while the hook runs (Windows). Useful for debugging scripts that prompt for input or show progress.

## Example: Adding a File Host Link via Hook

A script that uploads an archive to a custom host and returns the link:

**Command:**
```
python upload_to_host.py "%z" --name "%N"
```

**Script output:**
```json
{"url": "https://myhost.com/files/abc123"}
```

**Mapping:** ext1 → `url`

**Template usage:**
```bbcode
[if ext1]My Host: [url=#ext1#]Download[/url][/if]
```

The download link appears in your BBCode automatically, only when a URL was actually returned.
