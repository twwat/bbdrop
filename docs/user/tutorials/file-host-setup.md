# Adding File Host Downloads

In this tutorial, you enable a file host so that BBDrop automatically creates a compressed archive of each gallery and uploads it for download. By the end, your completed galleries include download links in the BBCode output.

## Prerequisites

- BBDrop installed and running.
- At least one image host configured and enabled (see [Setting Up IMX.to](imx-setup.md) or the [Quick Start](../getting-started/quick-start.md)).
- An account on at least one file host. This tutorial uses **Keep2Share** as the example. The same steps apply to RapidGator, FileBoom, TezFiles, Filedot, Filespace, and KatFile --- though some hosts use username/password instead of an API key.

## Step 1: Open the file host configuration

In the right panel, find the **Upload Workers** table. File hosts are listed below the image hosts.

Right-click **keep2share** and select **Configure Host...**.

The Keep2Share configuration dialog opens, showing credential fields, connection settings, and upload trigger options.

!!! tip
    You can also open file host configuration from **Settings > File Hosts** in the menu bar, or by double-clicking the host in the Upload Workers table.

## Step 2: Enter your credentials

Keep2Share uses API key authentication.

1. In the **Credentials** section, find the **API Key** field.
2. Enter your Keep2Share API key.

Credentials are encrypted and stored in your operating system's keyring.

!!! note
    Some file hosts (such as FileBoom and Filedot) use username and password instead of an API key. The credential fields adapt based on the host.

## Step 3: Test the connection

Click **Test Connection**.

BBDrop runs four checks against the Keep2Share servers:

1. **Credentials** --- Authenticates with your API key.
2. **User info** --- Retrieves your account information and storage quota.
3. **Upload test** --- Uploads a small test file.
4. **Delete test** --- Deletes the test file to confirm full API access.

All four checks must pass. If any fail, verify your API key and try again.

!!! note
    The storage bar in the dialog updates to show your used and available space on Keep2Share.

Click **OK** to save your settings and close the dialog.

## Step 4: Set the auto-upload trigger

The auto-upload trigger controls when BBDrop starts uploading the archive to the file host.

Right-click **keep2share** in the Upload Workers table and open the **Set Auto-Upload Trigger** submenu. Select **On Completed**.

With this setting, BBDrop waits until all images in a gallery finish uploading, then creates the archive and uploads it to Keep2Share.

!!! tip
    For your first file host, **On Completed** is the recommended trigger. It ensures the archive is only created after a successful image upload.

## Step 5: Enable the host

Right-click **keep2share** in the Upload Workers table and select **Enable Host**.

BBDrop tests your credentials before enabling. When the test passes, the host status changes to **Idle**.

## Step 6: Configure archive settings

Open **Settings > General** in the menu bar to open the settings dialog. In the left sidebar, select the **Zip Archives** tab. This controls the archive format for all file hosts.

1. Select an **Archive format**:
    - **ZIP** --- Universal compatibility. Works everywhere. Compression options: Store, Deflate (default), LZMA, BZip2.
    - **7-Zip** --- Better compression ratios. Compression options: Copy, LZMA2 (default), LZMA, Deflate, BZip2.
2. Choose a **Compression level**. Higher levels produce smaller archives but take longer.
3. For large galleries, enable **Split archives** and set a **Split size** (100 MiB to 4,095 MiB per part). Split archives are uploaded as multiple parts and named with `.001`, `.002` suffixes.

For this tutorial, leave the defaults: ZIP format with Deflate compression, splitting disabled.

## Step 7: Upload a gallery

1. Drag a folder of images into the main gallery table.
2. Click **Start** in the toolbar.

Watch the Upload Workers table. The image host worker uploads the images first. When the image upload completes, the Keep2Share worker activates --- it creates a ZIP archive and uploads it.

The gallery row in the main table shows progress for both the image upload and the file host upload.

## Step 8: Check the download link

When the file host upload completes, right-click the gallery and select **View BBCode**.

If your BBCode template includes the `#hostLinks#` placeholder, the download link appears in the output. A typical result looks like:

```
[url=https://keep2share.cc/file/abc123def456]Keep2Share[/url]
```

!!! note
    The default template does not include `#hostLinks#`. To add download links to your output, create a custom template with the `#hostLinks#` placeholder. See the [Creating a Custom Template](custom-template.md) tutorial.

## Step 9: Enable a second file host

Adding more file hosts gives your viewers multiple download options. The process is identical:

1. Right-click another file host in the Upload Workers table (for example, **rapidgator**).
2. Select **Configure Host...** and enter your credentials.
3. Test the connection.
4. Set the auto-upload trigger to **On Completed**.
5. Enable the host.

The next time you upload a gallery, both file hosts receive the archive. The `#hostLinks#` placeholder renders links for every enabled file host:

```
[url=https://keep2share.cc/file/abc123]Keep2Share[/url]
[url=https://rapidgator.net/file/xyz789]Rapidgator[/url]
```

## Understanding triggers

Each file host has its own trigger, set independently:

| Trigger | When archive upload starts | Best for |
|---|---|---|
| **On Added** | Immediately when the gallery is added to the queue | Getting archive uploads started early |
| **On Started** | When the gallery's image upload begins | Parallel image and file host uploads |
| **On Completed** | After all images finish uploading | Ensuring archives only upload for successful galleries |
| **Disabled** | Only when you right-click and manually trigger | Full manual control |

You can mix triggers across hosts. For example, set Keep2Share to **On Completed** and RapidGator to **On Started** to stagger uploads.

## Next steps

- Configure per-host BBCode format strings in each file host's configuration dialog to control how download links appear.
- See the [File Hosts guide](../guides/multi-host-upload.md) for archive splitting details, per-host connection settings, and storage monitoring.
