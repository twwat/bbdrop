# Key Concepts

BBDrop ties together several systems to turn image folders into formatted BBCode posts with download links. Here's how the pieces fit together.

## Image Hosts

Image hosts are where your images are uploaded and viewed. BBDrop currently supports:

- **IMX.to** — API key or session authentication, gallery renaming, multiple thumbnail sizes and formats
- **TurboImageHost** — Optional credentials, variable thumbnail sizes (150-600px), up to 500 images per gallery

Each image host has its own settings for thumbnails, content type, retries, and connection limits. You can have multiple hosts enabled and assign different hosts to different galleries.

## File Hosts

File hosts are optional. When enabled, BBDrop automatically creates a compressed archive (ZIP or 7Z) of your gallery and uploads it to one or more file hosts for download. Seven file hosts are available: RapidGator, FileBoom, Keep2Share, TezFiles, Filedot, Filespace, and KatFile.

File hosts require credentials and track storage usage, upload metrics, and connection health.

## BBCode Templates

Templates control what the final output looks like. They use `#placeholder#` syntax to insert gallery data:

```bbcode
[b]#folderName#[/b] (#pictureCount# images, #folderSize#)
#allImages#
[if hostLinks]
Download: #hostLinks#
[/if]
```

Templates support conditional logic with `[if]`/`[else]`/`[/if]` blocks — content only appears when the placeholder has a value. You can create as many templates as you need, assign them per-gallery, and switch templates after upload to regenerate the BBCode.

## The Gallery Queue

The main table is your gallery queue. Each row is a gallery (folder of images) with its status, progress, settings, and results. You can:

- Organize galleries into **tabs** for different projects
- **Inline-edit** fields directly in the table (gallery name, custom fields, template, image host)
- Customize which **columns** are visible and their order
- Track upload progress, speed, and completion status

## Artifacts

When a gallery upload completes, BBDrop generates artifact files:

- **BBCode file** — the rendered template output, ready to paste
- **JSON file** — complete upload data (image URLs, dimensions, statistics)

Artifacts can be saved in the gallery's `.uploaded` subfolder, in central storage (`~/.bbdrop/`), or both. They can be regenerated at any time — change the template, rename the gallery, or update custom fields, and the BBCode updates to match.

## Hooks

Hooks let you run external scripts or programs at key points in the upload workflow (when a gallery is added, started, or completed). The script receives gallery data via `%` variables and can return JSON output that maps back into the gallery's ext fields — which then become available as `#ext1#`-`#ext4#` placeholders in your templates.

This is how you connect BBDrop to other tools and scripts without modifying the app itself.

!!! tip
    You don't need to understand all of this upfront. Start with [Your First Upload](first-upload.md) and explore features as you need them.
