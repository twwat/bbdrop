# Proxies

BBDrop can route network requests through proxy servers. Proxies are configured globally and can be overridden per host.

## Proxy Modes

Configure the global proxy mode in **Settings > Proxy**:

- **No proxy (direct connection)** — All requests go directly to the internet
- **Use system proxy settings** — Inherits your operating system's proxy configuration
- **Custom proxy configuration** — Full control with proxy pools and per-category overrides

## Custom Configuration

### Proxy Pools

A proxy pool is a collection of proxy servers with a rotation strategy. Create pools for different purposes (e.g., "US Residential", "Datacenter EU").

**Supported formats:**

```
host:port
host:port:user:pass
http://host:port
http://user:pass@host:port
socks5://user:pass@host:port
```

**Supported protocols:** HTTP, HTTPS, SOCKS4, SOCKS5

**Rotation strategies:**

| Strategy | Behavior |
|---|---|
| Round Robin | Cycle through proxies sequentially (default) |
| Random | Pick a random proxy each time |
| Least Used | Use the proxy with the fewest recent requests |
| Weighted | Assign weights to prioritize certain proxies |
| Failover | Try the first proxy, fall back to the next on failure |

### Pool Options

- **Sticky sessions** — Keep the same proxy for a set duration (default: 1 hour)
- **Fallback on failure** — Automatically switch to the next proxy if the current one fails
- **Max consecutive failures** — Disable a proxy after this many failures (default: 3)

### Bulk Import

Paste a list of proxies to import them all at once. BBDrop reports how many were added, how many were duplicates, and flags any invalid entries. Lines starting with `#` are treated as comments.

### Testing

Click **Test** on a proxy pool to verify connectivity. It connects through the first proxy and confirms your external IP.

## Per-Host Proxy

Each host (image or file) has a **Proxy** dropdown in its configuration dialog:

- **OS System Proxy** — Use the system setting
- **Direct** — No proxy for this host
- Any configured proxy pool

This lets you route different hosts through different proxies — for example, direct connection for image host APIs but a proxy pool for file host uploads.
