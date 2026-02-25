# BBCode Templates

Templates control what the generated BBCode looks like when a gallery upload completes. They use placeholders that get replaced with actual gallery data, and support conditional logic to show or hide sections based on available data.

## Managing Templates

Open the template manager from **Settings > Templates** or the **Templates** button in the quick settings panel.

BBDrop ships with two built-in templates:

- **default** — Simple output: gallery name followed by all image BBCode
- **Extended Example** — Demonstrates all placeholders and conditional features

Built-in templates are read-only. To customize, click **Copy** to duplicate one as a starting point, or **Create New** to start from scratch.

!!! tip
    The **Extended Example** template demonstrates every placeholder and conditional feature — it's the best starting point for learning the syntax.

## Placeholders

Placeholders use `#name#` syntax and are replaced with gallery data when BBCode is generated:

### Gallery Info
| Placeholder | Description |
|---|---|
| `#folderName#` | Gallery name |
| `#pictureCount#` | Number of successfully uploaded images |
| `#folderSize#` | Total gallery size (e.g., "125.3 MB") |
| `#extension#` | Most common file extension (e.g., "JPG") |

### Image Dimensions
| Placeholder | Description |
|---|---|
| `#width#` | Average image width in pixels |
| `#height#` | Average image height in pixels |
| `#longest#` | Longest dimension (max of width and height) |

### Links
| Placeholder | Description |
|---|---|
| `#galleryLink#` | Gallery URL on the image host |
| `#allImages#` | BBCode for all uploaded images (thumbnail linked to full size) |
| `#hostLinks#` | File host download links (empty if no file hosts used) |

### Custom and External Fields
| Placeholder | Description |
|---|---|
| `#custom1#` to `#custom4#` | User-defined fields, editable in the gallery table |
| `#ext1#` to `#ext4#` | Fields populated by external programs via [hooks](hooks.md) |

The template editor has placeholder buttons for quick insertion, and typing triggers autocomplete suggestions.

## Conditional Logic

Wrap content in `[if]` blocks to show it only when a placeholder has a value:

```bbcode
[if galleryLink]Gallery: #galleryLink#[/if]
```

Use `[else]` for fallback content:

```bbcode
[if hostLinks]
Download: #hostLinks#
[else]
No downloads available
[/if]
```

Compare against a specific value:

```bbcode
[if extension=JPG]High-quality JPG gallery[/if]
```

Conditionals can be nested and work across multiple lines. The template editor includes a **Conditional Insert** helper and a **Validate Syntax** button to check for errors.

## Example Template

```bbcode
[center][size=4][b]#folderName#[/b][/size]
[size=2]#pictureCount# images | #extension# | #width#x#height# | #folderSize#[/size][/center]

#allImages#

[if galleryLink][b]Gallery:[/b] #galleryLink#[/if]
[if hostLinks]
[b]Download:[/b]
#hostLinks#
[/if]
[if custom1]Tags: #custom1#[/if]
```

## File Host Link Placeholders

The `#hostLinks#` placeholder expands using each file host's own BBCode format (configured in the file host settings). That format supports its own placeholders:

| Placeholder | Description |
|---|---|
| `#link#` | Download URL |
| `#hostName#` | Host display name (e.g., "Rapidgator") |
| `#partLabel#` | Part label for split archives (e.g., "Part 1") |
| `#partNumber#` | Part number (1, 2, 3...) |
| `#partCount#` | Total number of parts |

## Per-Gallery Templates

Each gallery has a template assignment (shown in the **Template** column). Change it by clicking the cell and selecting from the dropdown, or right-click multiple galleries and use **Set template to...** for bulk changes.

## Regenerating BBCode

When you change a template, rename a gallery, or update custom fields, BBCode can be regenerated from the original upload data:

- **Automatic** — Enable "Auto-regenerate artifacts when data changes" in **Settings > General** (on by default)
- **Manual** — Right-click a completed gallery and select **Regenerate BBCode**

Regeneration works from the saved JSON artifact, so no re-upload is needed.

!!! warning
    If you delete the JSON artifact file, BBCode can no longer be regenerated for that gallery. Keep central storage enabled to maintain a backup copy.

## Template Storage

Custom templates are saved as `.template.txt` files in your central storage directory (`~/.bbdrop/templates/` by default). They can be backed up and shared between installations.
