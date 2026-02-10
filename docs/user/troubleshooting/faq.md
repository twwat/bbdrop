# FAQ

## General

**Where does BBDrop store its data?**

By default, everything is stored in `~/.bbdrop/` (your home directory). This includes the database, settings, templates, artifacts, and logs. You can change this in **Settings > General > Central Storage**. The portable version stores data alongside the executable.

**Can I run multiple instances?**

No. BBDrop uses a single-instance architecture. If you try to open a second instance, it sends any folder arguments to the running instance and exits. This prevents database conflicts.

**How do I update BBDrop?**

BBDrop checks for updates on startup (configurable in Settings > General). When an update is available, download the new version from [GitHub Releases](https://github.com/twwat/bbdrop/releases/latest). Your settings and database are preserved across updates.

## Uploads

**What image formats are supported?**

JPG, JPEG, PNG, and GIF.

**How many images can I upload per gallery?**

This depends on the image host. TurboImageHost has a 500-image limit per gallery. IMX.to has no hard limit.

**Can I resume interrupted uploads?**

Yes. If an upload is interrupted (app crash, network issue), the gallery retains its progress. Restart the upload and it picks up where it left off, skipping already-uploaded images.

**What happens if an upload fails?**

Failed uploads are marked with an error status. Right-click and select **Retry Upload** to try again. You can configure auto-retry and max retry attempts per host in the host configuration dialog.

**Can I upload to multiple image hosts at once?**

Each gallery uploads to one image host at a time. However, you can have galleries assigned to different hosts in the queue and they'll upload to their respective hosts.

## Templates

**Can I change the template after uploading?**

Yes. Change the template via the dropdown in the gallery table or right-click > Set template to. If auto-regeneration is enabled, the BBCode updates immediately. Otherwise, right-click and select **Regenerate BBCode**.

**Where are my custom templates stored?**

In `~/.bbdrop/templates/` (or your configured central storage). Each template is a `.template.txt` file that you can back up or share.

## File Hosts

**Do I need file hosts?**

No. File hosts are entirely optional. They're useful if you want to provide download links alongside your image galleries.

**Does BBDrop create the archives automatically?**

Yes. When file hosts are enabled, BBDrop automatically creates a ZIP or 7Z archive from the gallery folder and uploads it. You don't need to create archives manually.

## Credentials

**How are my credentials stored?**

Credentials are encrypted using Fernet (AES-128-CBC + HMAC-SHA256) and stored in your operating system's keyring — Windows Credential Manager, macOS Keychain, or Linux Secret Service. They are never stored in plain text.

**I can't log in to a host. What should I do?**

1. Verify your credentials are correct by logging in through the host's website
2. Open the host configuration dialog and click **Test Connection** to see which step fails
3. Try **Tools > Authentication > Reattempt Login** to refresh the session
4. Check the log panel for detailed error messages
