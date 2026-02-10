# Common Issues

## Upload Failures

**"Upload failed" or "Inactivity timeout"**

The image host didn't respond in time. This is usually a temporary network issue.

- Check that the host is accessible in your browser
- Increase the **Inactivity timeout** in the host configuration dialog
- Enable **Auto-retry** with a higher retry count
- If using a proxy, test the proxy connection or try a direct connection

**"Max file size exceeded"**

The image is larger than the host allows. TurboImageHost has a 35 MB limit per image. Check the host's limits in the configuration dialog.

**Uploads are slow**

- Reduce the number of **Max connections** if your network is saturated
- Check the **Speed** section in the status bar — if peak speed is normal but current speed is low, the host may be throttling
- If using a proxy, test upload speed with a direct connection

## Gallery Issues

**Images are missing from the upload**

BBDrop excludes corrupt or invalid images during scanning. Check the log panel for messages about skipped files. Supported formats are JPG, JPEG, PNG, and GIF only.

**Gallery shows wrong image count**

The image count is determined during scanning. If you added images to the folder after scanning, right-click the gallery and select **Rescan for New Images**.

**Dimensions look wrong in the BBCode**

Dimensions are calculated from a sample of images, not all of them. Adjust sampling settings in **Settings > Image Scan** — increase the sample count, switch from Mean to Median, or enable outlier exclusion.

## Template Issues

**BBCode is empty or missing placeholders**

- Verify the template uses correct `#placeholder#` syntax (not `%` — those are for hooks)
- Check that the gallery has completed uploading (placeholders aren't populated until upload finishes)
- Click **Regenerate BBCode** to force a refresh

**Conditional blocks aren't working**

- Verify matching `[if]` and `[/if]` tags
- Use the **Validate Syntax** button in the template editor
- Remember that value comparisons are case-sensitive: `[if extension=JPG]` won't match "jpg"

## File Host Issues

**Archives aren't being created**

- Verify at least one file host is enabled
- Check the **Auto-Upload Trigger** setting — if set to "Manual", archives won't be created automatically
- Check the log for archive creation errors

**Split archive parts are missing**

7Z split archives require the 7-Zip CLI to be installed on your system. Switch to ZIP format (which uses a built-in pure Python implementation) or install 7-Zip.

## Application Issues

**BBDrop won't start (port in use)**

BBDrop uses a TCP port for single-instance communication. If the app crashed previously, the port may still be held by the OS. Wait a minute and try again, or restart your computer.

**High memory usage**

Large queues with thousands of galleries can use significant memory. Use **Clear Completed** to remove finished galleries you no longer need in the queue. The database retains their upload history regardless.

**Log panel is overwhelming**

Adjust log verbosity in **Settings > Logs** — set the GUI log level to WARNING or ERROR to reduce noise. You can also toggle individual categories (e.g., disable Database or Timing logs).

## Platform-Specific Issues

**Windows: Context menu not appearing in Explorer**

Run BBDrop as administrator when installing the context menu, or use **Settings > Tools > Windows Explorer Integration > Install Context Menu**.

**Linux: Drag and drop not working (WSL2)**

Drag and drop from the Windows file manager into a WSL2 application requires additional configuration. Use **File > Add Folders** as an alternative.

**macOS: "App is damaged" warning**

If macOS blocks the app, open Terminal and run:

```bash
xattr -cr /Applications/BBDrop.app
```
