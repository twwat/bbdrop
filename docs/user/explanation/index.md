# Explanation

This section explains how BBDrop works under the hood. These documents describe the design decisions, architecture, and tradeoffs behind the system -- not step-by-step instructions.


- [Upload Pipeline](./upload-pipeline.md) -- How a gallery flows from queue to hosted images, and why the pipeline is host-agnostic
- [Security Model](./security-model.md) -- How BBDrop protects credentials, tokens, and data in transit and at rest
- [Queue & Persistence](./queue-architecture.md) -- How the queue system tracks gallery state, survives restarts, and coordinates threads
---

Back to [User Documentation](../index.md)
