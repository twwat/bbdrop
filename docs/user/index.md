# BBDrop Documentation

Welcome to BBDrop — a desktop application for batch uploading image galleries to multiple image and file hosts with BBCode output and persistent queue management.

---

## Getting Started

New to BBDrop? Start here.

- [Installation](getting-started/installation.md) — Download and install BBDrop
- [Quick Start](getting-started/quick-start.md) — Upload your first gallery in 5 minutes
- [Key Concepts](getting-started/concepts.md) — Image hosts, file hosts, templates, and queues

---

## Tutorials

Step-by-step walkthroughs for common workflows.

- [Setting Up IMX.to](tutorials/imx-setup.md) — Configure authentication, thumbnails, and gallery renaming
- [Creating a Custom Template](tutorials/custom-template.md) — Build a BBCode template with placeholders and conditionals
- [Adding File Host Downloads](tutorials/file-host-setup.md) — Enable file hosts for automatic archive upload

## Guides

Task-oriented instructions for specific features.

### Core

- [GUI Guide](guides/gui-guide.md) — Interface walkthrough, tabs, and queue management
- [Image Hosts](guides/image-hosts.md) — IMX.to, Pixhost, and TurboImageHost configuration
- [Multi-Host Upload](guides/multi-host-upload.md) — Upload to 7 premium file hosts
- [Queue Management](guides/queue-management.md) — Queue operations, tabs, columns, context menu
- [Scanning & Link Checking](guides/scanning.md) — Image scanning, link checker, cover photos
- [BBCode Templates](guides/bbcode-templates.md) — 18 placeholders and conditional logic
- [Proxies & Tor](guides/proxies.md) — Proxy pools, per-host proxy, Tor integration

### Advanced

- [Archive Management](guides/archive-management.md) — ZIP, RAR, 7Z extraction and creation
- [Duplicate Detection](guides/duplicate-detection.md) — Identify previously uploaded galleries
- [Hooks & Automation](guides/hooks.md) — External app integration
- [Credential Management](guides/credential-management.md) — Secure password and API key storage
- [Theme Customization](guides/theme-customization.md) — Dark, light, and auto themes

---

## Explanation

Understand how BBDrop works under the hood.

- [Upload Pipeline](explanation/upload-pipeline.md) — How galleries flow from queue to hosted images
- [Security Model](explanation/security-model.md) — Credential encryption, transport security, and thread safety
- [Queue & Persistence](explanation/queue-architecture.md) — How the queue survives restarts and manages state

## Reference

Quick lookup for settings, shortcuts, and parameters.

- [Settings](reference/settings-reference.md) — All settings by category
- [Keyboard Shortcuts](reference/keyboard-shortcuts.md) — Complete shortcut reference
- [Template Placeholders](reference/template-placeholders.md) — All 18 placeholders
- [External App Parameters](reference/external-apps-parameters.md) — Hook variable reference
- [Quick Reference](reference/quick-reference.md) — One-page cheat sheet

---

## Troubleshooting

- [FAQ](troubleshooting/faq.md) — Frequently asked questions
- [Common Issues](troubleshooting/common-issues.md) — Known problems and solutions
- [Troubleshooting Guide](troubleshooting/troubleshooting.md) — Systematic diagnosis
- [Silent Failures](troubleshooting/silent-failures.md) — When uploads fail without feedback
- [Log Diagnosis](troubleshooting/LOG_DIAGNOSIS_QUICK_REF.md) — Interpret log files
- [WSL2 Drag & Drop](troubleshooting/wsl2-drag-drop-fix.md) — Fix drag-and-drop in WSL2
---

## Architecture & Decisions

- [System Overview](architecture/system-context.md) — C4 system context diagram
- [Application Components](architecture/containers.md) — C4 container diagram
- [Decision Log](decisions/index.md) — Architecture Decision Records


