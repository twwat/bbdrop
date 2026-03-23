# Creating a Custom Template

In this tutorial, you create a BBCode template that includes a gallery title, image metadata, all uploaded images, a cover photo, file host download links, and conditional logic. By the end, you have a reusable template that produces formatted output for every gallery.

## Prerequisites

- BBDrop installed and running.
- At least one completed upload in the gallery queue, so you have data to preview.

## Step 1: Open the template manager

Go to **Settings > Templates** in the menu bar.

The template manager opens with a list of templates on the left and an editor on the right. BBDrop ships with two built-in templates: **default** and **Extended Example**. Both are read-only.

!!! tip
    You can also open the template manager from the **Templates** button in the Quick Settings panel.

## Step 2: Create a new template

1. Click **New Template** in the template list panel.
2. Enter a name for your template, such as `My Gallery Template`.
3. Click **OK**.

The new template appears in the list and is selected. The editor is empty and ready for your content.

## Step 3: Add a gallery title

In the editor, type the following:

```bbcode
[center][size=4][b]#folderName#[/b][/size][/center]
```

The `#folderName#` placeholder is replaced with the gallery name (your source folder name) when BBCode is generated.

!!! tip
    Instead of typing placeholders manually, click the **Gallery Name** button in the placeholder panel on the right side of the editor. It inserts `#folderName#` at the cursor position.

## Step 4: Add image metadata

On a new line below the title, type:

```bbcode
[center][size=2]#pictureCount# images | #extension# | #width#x#height# | #folderSize#[/size][/center]
```

This line shows the number of uploaded images, the most common file extension (such as JPG), the average image dimensions in pixels, and the total gallery size.

## Step 5: Add all images

On a new line, type:

```bbcode
#allImages#
```

This placeholder expands to the BBCode for every uploaded image --- each one rendered as a clickable thumbnail that links to the full-size image.

## Step 6: Add a cover photo

A cover photo is a separate thumbnail uploaded at a different size, intended as a preview image for your gallery. Add it above `#allImages#`:

```bbcode
#cover#

#allImages#
```

The `#cover#` placeholder expands to the cover image BBCode. If no cover photo is configured, the placeholder produces an empty string.

## Step 7: Add file host download links

If you use file hosts, the `#hostLinks#` placeholder inserts download links for each enabled file host. Add it below the images:

```bbcode
[b]Download:[/b]
#hostLinks#
```

Each file host formats its link using its own BBCode format string (configurable in the file host settings). A typical output looks like:

```
[url=https://rapidgator.net/file/abc123]Rapidgator[/url]
[url=https://keep2share.cc/file/xyz789]Keep2Share[/url]
```

## Step 8: Add conditional logic

Not every gallery has file host links. Wrap the download section in a conditional block so it only appears when links exist:

```bbcode
[if hostLinks]
[b]Download:[/b]
#hostLinks#
[else]
[i]No downloads available[/i]
[/if]
```

The `[if hostLinks]` block checks whether the `#hostLinks#` placeholder has a value. If it does, the download section renders. If not, the `[else]` fallback content renders instead.

!!! tip
    Use the **[if] Helper** button in the Conditionals section of the placeholder panel. It opens a dialog that helps you build conditional blocks without memorizing the syntax.

## Step 9: Review your complete template

Your template should now look like this:

```bbcode
[center][size=4][b]#folderName#[/b][/size][/center]
[center][size=2]#pictureCount# images | #extension# | #width#x#height# | #folderSize#[/size][/center]

#cover#

#allImages#

[if hostLinks]
[b]Download:[/b]
#hostLinks#
[else]
[i]No downloads available[/i]
[/if]
```

Click **Validate Syntax** at the bottom of the dialog to check for errors. A confirmation message appears if the template is valid.

## Step 10: Add custom fields

Custom fields let you add your own data to each gallery. Four fields are available: `#custom1#` through `#custom4#`. You edit their values in the gallery table's Custom columns.

Add a tags line at the bottom of your template:

```bbcode
[if custom1]Tags: #custom1#[/if]
```

This line only appears when you enter a value in the Custom 1 column for a gallery.

## Step 11: Save and assign the template

1. Click **OK** in the settings dialog to save all changes.
2. In the main gallery table, click the **Template** cell for a completed gallery.
3. Select your new template from the dropdown.

The BBCode regenerates automatically using your template. Right-click the gallery and select **View BBCode** to see the formatted output.

!!! note
    If auto-regeneration is disabled, right-click the gallery and select **Regenerate BBCode** to apply the new template manually. You can toggle auto-regeneration in **Settings > General**.

## Template file location

Custom templates are saved as `.template.txt` files in your central storage directory (`~/.bbdrop/templates/` by default). You can back them up, share them between installations, or edit them in a text editor.

## Next steps

- Add `#ext1#` through `#ext4#` placeholders to display output from external programs. Set up hooks in **Settings > Hooks (External Apps)** to populate these fields automatically.
- See the [BBCode Templates guide](../guides/bbcode-templates.md) for a complete reference of all placeholders and conditional syntax.
