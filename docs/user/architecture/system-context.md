# System overview

This C4 Level 1 diagram shows BBDrop in its operating environment: the user who
interacts with it, the external services it uploads to, and the platform
services it depends on.

BBDrop communicates with three image hosts (IMX.to, Pixhost, TurboImageHost) and
seven file hosts (RapidGator, Keep2Share, FileBoom, TezFiles, Filedot,
Filespace, Katfile). IMX.to is accessed via `requests` over its JSON REST API;
all other hosts use `pycurl` for bandwidth tracking and connection control. An
optional proxy or Tor layer can route traffic through HTTP, SOCKS4, or SOCKS5
proxies.

```mermaid
C4Context
    title System Context Diagram — BBDrop

    Person(user, "User", "Uploads image galleries and retrieves BBCode output")

    System(bbdrop, "BBDrop", "PyQt6 desktop application for batch uploading image galleries to multiple hosts")

    System_Ext(imx, "IMX.to", "Image host — JSON REST API via requests")
    System_Ext(pixhost, "Pixhost", "Image host — HTTP API via pycurl")
    System_Ext(turbo, "TurboImageHost", "Image host — HTTP API via pycurl")

    System_Ext(rapidgator, "RapidGator", "File host — pycurl")
    System_Ext(keep2share, "Keep2Share", "File host — pycurl")
    System_Ext(fileboom, "FileBoom", "File host — pycurl")
    System_Ext(tezfiles, "TezFiles", "File host — pycurl")
    System_Ext(filedot, "Filedot", "File host — pycurl")
    System_Ext(filespace, "Filespace", "File host — pycurl")
    System_Ext(katfile, "Katfile", "File host — pycurl")

    System_Ext(keyring, "OS Keyring", "Windows Credential Manager / macOS Keychain / Linux Secret Service")
    System_Ext(proxy, "Proxy / Tor", "Optional HTTP, SOCKS4, or SOCKS5 proxy for network routing")

    Rel(user, bbdrop, "Adds galleries, configures hosts, views BBCode")
    Rel(bbdrop, imx, "Uploads images (requests)")
    Rel(bbdrop, pixhost, "Uploads images (pycurl)")
    Rel(bbdrop, turbo, "Uploads images (pycurl)")
    Rel(bbdrop, rapidgator, "Uploads files (pycurl)")
    Rel(bbdrop, keep2share, "Uploads files (pycurl)")
    Rel(bbdrop, fileboom, "Uploads files (pycurl)")
    Rel(bbdrop, tezfiles, "Uploads files (pycurl)")
    Rel(bbdrop, filedot, "Uploads files (pycurl)")
    Rel(bbdrop, filespace, "Uploads files (pycurl)")
    Rel(bbdrop, katfile, "Uploads files (pycurl)")
    Rel(bbdrop, keyring, "Stores and retrieves Fernet master key and encrypted credentials")
    Rel(bbdrop, proxy, "Routes upload traffic (optional)")
```

The seven file hosts share a single `FileHostClient` implementation driven by
JSON configuration files (`assets/hosts/*.json`). Each host's upload flow,
authentication method, and response parsing are defined declaratively rather
than in host-specific code.
