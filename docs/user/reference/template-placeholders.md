# Template Placeholders Reference

Complete reference for BBCode template syntax.

## Gallery Placeholders

Used in BBCode templates (`Settings > Templates`). Replaced with gallery data when BBCode is generated.

| Placeholder | Description | Example Value |
|---|---|---|
| `#folderName#` | Gallery name | "Beach Photos 2026" |
| `#pictureCount#` | Number of uploaded images | "142" |
| `#folderSize#` | Total gallery size | "1.2 GiB" |
| `#extension#` | Most common file extension | "JPG" |
| `#width#` | Average image width (px) | "1920" |
| `#height#` | Average image height (px) | "1080" |
| `#longest#` | Longest dimension (px) | "1920" |
| `#galleryLink#` | Gallery URL | "https://imx.to/g/abc123" |
| `#allImages#` | BBCode for all images | `[url=...][img]...[/img][/url]` |
| `#hostLinks#` | File host download links | Formatted per host's BBCode setting |
| `#custom1#` - `#custom4#` | User-defined fields | Any text |
| `#ext1#` - `#ext4#` | Fields from hooks | Any text |

## File Host Link Placeholders

Used in each file host's **BBCode Format** setting (`Settings > File Hosts > Configure Host`). These placeholders work inside the `#hostLinks#` expansion.

| Placeholder | Description | Example Value |
|---|---|---|
| `#link#` | Download URL | "https://rapidgator.net/file/abc" |
| `#hostName#` | Host display name | "Rapidgator" |
| `#partLabel#` | Part label (split archives) | "Part 1" |
| `#partNumber#` | Part number | "1" |
| `#partCount#` | Total number of parts | "3" |

## Hook Variables

Used in hook command templates (`Settings > Hooks`). These are a separate system from BBCode template placeholders.

| Variable | Description | Available |
|---|---|---|
| `%N` | Gallery name | All events |
| `%T` | Tab name | All events |
| `%p` | Gallery folder path | All events |
| `%C` | Number of images | All events |
| `%s` | Gallery size in bytes | All events |
| `%t` | Template name | All events |
| `%z` | ZIP archive path (created on demand) | All events |
| `%e1` - `%e4` | ext field values | All events |
| `%c1` - `%c4` | custom field values | All events |
| `%g` | Gallery ID | On Completed only |
| `%j` | JSON artifact path | On Completed only |
| `%b` | BBCode artifact path | On Completed only |
| `%%` | Literal % character | All events |

## Conditional Logic

### Existence Check

Show content only when a placeholder has a non-empty value:

```bbcode
[if galleryLink]
Gallery: #galleryLink#
[/if]
```

### With Fallback

```bbcode
[if hostLinks]
Download: #hostLinks#
[else]
No downloads available
[/if]
```

### Value Comparison

Compare a placeholder against a specific value (case-sensitive):

```bbcode
[if extension=JPG]High-quality JPG gallery[/if]
```

### Nesting

Conditionals can be nested:

```bbcode
[if galleryLink]
Gallery: #galleryLink#
[if hostLinks]
Downloads: #hostLinks#
[/if]
[/if]
```

## Complete Example

```bbcode
[center][size=4][b][color=#11c153]#folderName#[/color][/b][/size]
[size=3]#pictureCount# images | #extension# | #width#x#height# | #folderSize#[/size][/center]

#allImages#

[if galleryLink][b]Gallery:[/b] #galleryLink#[/if]

[if hostLinks]
[b]Download:[/b]
#hostLinks#
[/if]

[if custom1]Tags: #custom1#[/if]
[if ext1]Extra: #ext1#[/if]
```
