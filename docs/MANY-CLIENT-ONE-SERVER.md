# Many clients / one server — relay checkpoint

This is a named deployment checkpoint of the existing v0.3.1 setup. It preserves the working server and small-client executables; no runtime functionality or executable contents changed for this label.

## Supported deployment

- One office Windows PC runs `CampusLinkServer.exe` and starts its managed relay and outbound tunnel with **Share this computer**.
- Multiple Windows PCs can have `CampusLinkClient.exe` installed or copied onto them. The client is 83,968 bytes (82 KiB), uses Windows .NET Framework 4.8+, and does not contain the server/tunnel runtimes.
- An intended client receives the office host's connection code or invitation, connects, and waits for local approval.
- **One desktop session at a time** is admitted by the current sharing host. A second simultaneous connection receives “Device unavailable or busy.” Other client installations can connect after that session ends.
- The connected pair may request/grant/revoke control and reverse direction with local consent. That remains the same two-endpoint session through the original office relay.

```text
Client installation A ─┐
Client installation B ─┼── public tunnel ── office relay + sharing host
Client installation C ─┘
                       one active desktop session at a time
```

## Data path

The clients do not establish a direct P2P media connection. Every screen frame, input packet and in-session command is encrypted by the endpoint and forwarded through the relay. The relay does not decrypt, decode or persist desktop images; transient network buffering and packet forwarding are still necessary.

The small client is a connecting endpoint, not an independently registered hosting endpoint. The office host generates its device ID locally. This version is not a directory that assigns unique IDs to all clients and does not let client A directly select client B by a server-issued ID.

## Deferred changes

The attached central-directory/direct-client diagram is a future architecture: authenticated device enrollment, server-managed IDs, any-client hosting/viewing, peer discovery and direct encrypted transport with a relay fallback where necessary. Moving the current relay to a GoDaddy VPS does not by itself implement those changes. No VPS was provisioned for this checkpoint.

## Artifacts and provenance

- `CampusLinkClient.exe`: 83,968 bytes; SHA-256 `a38e6ebdb66f30eb3ae0d32f9abc8384288c27d4000bcf94a5e805be7a7d4f36`.
- `CampusLinkServer.exe`: 88,967,631 bytes; SHA-256 `4dc53ceb57d5927fc539b0e39d2cff91e9376286a6a1cf765e4abb6c8957270e`.
- These binaries are unchanged from release `v0.3.1`. The server binary itself is the full v0.3.0 build renamed for its deployment role.
- Existing validation: 28 automated checks plus a synthetic public-tunnel protocol test. This checkpoint's new changes are documentation/release metadata, not newly tested runtime features. A two-physical-PC acceptance test and actual FPS measurement remain outstanding.
- Office enrollment secrets, live connection codes and identifying network data remain excluded from Git and release files.

For setup and current limitations, read [DESKTOP.md](DESKTOP.md) and [VALIDATION.md](VALIDATION.md).
