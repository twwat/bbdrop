# Setting Up IMX.to

In this tutorial, you configure IMX.to as your image host, enter credentials, choose thumbnail settings, and upload a test gallery. By the end, you have a working IMX.to setup with automatic gallery renaming.

## Prerequisites

- BBDrop installed and running.
- An IMX.to account. Sign up at [imx.to](https://imx.to) if you don't have one.

## Step 1: Open the host configuration

In the right panel, find the **Upload Workers** table. It lists all available image and file hosts.

Right-click **imx** in the table and select **Configure Host...**.

The IMX.to configuration dialog opens, showing credential fields, thumbnail settings, and connection options.

## Step 2: Enter your API key

The API key is required for uploading images to IMX.to.

1. In the **Credentials** section, find the **API Key** row.
2. Click the link to [imx.to/user/api](https://imx.to/user/api), or navigate there in your browser.
3. Copy your API key from the IMX.to account settings page.
4. Click **Set** next to the API Key row.
5. Paste your API key into the dialog and click **OK**.

The status label next to API Key changes to show that a key is stored.

!!! tip
    All credentials are encrypted and stored in your operating system's keyring (Windows Credential Manager, macOS Keychain, or Linux Secret Service). They are never saved as plain text.

## Step 3: Enter your login credentials

Login credentials are required for gallery renaming. Without them, all galleries are named "untitled gallery" on IMX.to.

1. Click **Set** next to the **Username** row. Enter your IMX.to username and click **OK**.
2. Click **Set** next to the **Password** row. Enter your IMX.to password and click **OK**.

Both status labels update to confirm the credentials are stored.

## Step 4: Test the connection

Click the **Test Credentials** button at the bottom of the Credentials section.

BBDrop verifies your API key and login credentials against the IMX.to servers. When the test passes, a success message appears next to the button.

!!! note
    If the test fails, double-check that your API key is correct and that your username and password match your IMX.to account. You can click **Set** again to re-enter them.

## Step 5: Configure thumbnail settings

In the **Thumbnails** section of the configuration dialog:

1. Select a **Thumbnail size** from the dropdown. Available sizes are 100x100, 150x150, 180x180, 250x250 (default), and 300x300.
2. Select a **Thumbnail format** from the dropdown. Options are Fixed width, Proportional (default), Square, and Fixed height.

The thumbnail size and format control how image previews appear in your BBCode output.

## Step 6: Enable automatic gallery renaming

In the **Options** section, verify that **Automatically rename galleries on imx.to** is checked. This is enabled by default.

When enabled, BBDrop's RenameWorker renames galleries on IMX.to using your folder name after upload completes.

## Step 7: Click OK to save

Click **OK** at the bottom of the configuration dialog. All your settings are saved.

## Step 8: Enable the host

If IMX.to is not already enabled, right-click **imx** in the Upload Workers table and select **Enable Host**.

BBDrop tests your credentials before enabling. When the test passes, the host status changes to **Idle**, indicating it is ready to accept uploads.

## Step 9: Set IMX.to as your primary host

Right-click **imx** in the Upload Workers table and select **Set as Primary Host**.

A checkmark appears next to the menu item. All new galleries added to the queue now default to IMX.to for image uploads.

!!! tip
    You can also set the primary host from the **Image Host** dropdown in the Quick Settings panel on the left side of the main window.

## Step 10: Upload a test gallery

1. Drag a folder containing a few images from your file manager into the main gallery table. The folder name becomes the gallery name.
2. Verify the **Image Host** column shows **IMX.to** for your gallery.
3. Click **Start** in the toolbar.

The Upload Workers table shows real-time progress for the IMX.to worker. The gallery row in the main table updates with a progress bar, image count, and upload speed.

## Step 11: Verify gallery renaming

When the upload completes, the gallery status changes to **Completed**. Watch the Upload Workers table --- the **RenameWorker** activates automatically and renames the gallery on IMX.to using your folder name.

Before renaming, IMX.to galleries are created as "untitled gallery." The RenameWorker fixes this in the background, using the login credentials you entered in Step 3.

!!! note
    You can view and manage any galleries that failed to rename from **Tools > Unnamed Galleries** in the menu bar.

## Step 12: Check the results

Right-click the completed gallery and select **Copy BBCode** to copy the output to your clipboard. You can also click **View BBCode** to preview the generated BBCode.

The output contains thumbnail-linked images pointing to your IMX.to gallery.

## Next steps

- [Create a custom BBCode template](custom-template.md) to control how your gallery output looks.
- [Add file host downloads](file-host-setup.md) to include download links in your BBCode.
