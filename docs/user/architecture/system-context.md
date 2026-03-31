# System overview

This diagram shows BBDrop in its operating environment: the user who interacts
with it, the external services it uploads to, and the platform services it
depends on.

BBDrop communicates with three image hosts (IMX.to, Pixhost, TurboImageHost) and
seven file hosts (RapidGator, Keep2Share, FileBoom, TezFiles, Filedot,
Filespace, Katfile). IMX.to is accessed via `requests` over its JSON REST API;
all other hosts use `pycurl` for bandwidth tracking and connection control. An
optional proxy or Tor layer can route traffic through HTTP, SOCKS4, or SOCKS5
proxies.

```mermaid
graph TD
    user(("👤 User"))
    bbdrop["BBDrop<br/><small>PyQt6 desktop application</small>"]

    subgraph image_hosts ["Image Hosts"]
        imx["IMX.to<br/><small>requests</small>"]
        pixhost["Pixhost<br/><small>pycurl</small>"]
        turbo["TurboImageHost<br/><small>pycurl</small>"]
    end

    subgraph file_hosts ["File Hosts"]
        rapidgator["RapidGator"]
        keep2share["Keep2Share"]
        fileboom["FileBoom"]
        tezfiles["TezFiles"]
        filedot["Filedot"]
        filespace["Filespace"]
        katfile["Katfile"]
    end

    keyring[("OS Keyring<br/><small>Credential Manager · Keychain · Secret Service</small>")]
    proxy["Proxy / Tor<br/><small>HTTP · SOCKS4 · SOCKS5</small>"]

    user -- "adds galleries, configures hosts, views BBCode" --> bbdrop
    bbdrop -- "uploads images" --> imx
    bbdrop -- "uploads images" --> pixhost
    bbdrop -- "uploads images" --> turbo
    bbdrop -- "uploads files" --> rapidgator
    bbdrop -- "uploads files" --> keep2share
    bbdrop -- "uploads files" --> fileboom
    bbdrop -- "uploads files" --> tezfiles
    bbdrop -- "uploads files" --> filedot
    bbdrop -- "uploads files" --> filespace
    bbdrop -- "uploads files" --> katfile
    bbdrop -- "stores/retrieves credentials" --> keyring
    bbdrop -.-> |"optional"| proxy
```

The seven file hosts share a single `FileHostClient` implementation driven by
JSON configuration files (`assets/hosts/*.json`). Each host's upload flow,
authentication method, and response parsing are defined declaratively rather
than in host-specific code.
