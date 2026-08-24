# HTTP operation

Vellis runs only in the foreground. It does not install a service, background itself, terminate TLS,
or manage containers. The default endpoint is `http://127.0.0.1:8000/mcp`.

Startup validates the database, then the selected token file, then the HTTP bind. A failure names
that stage and its corrective action: run setup or audit for a database-probe failure, supply a
readable nonempty owner-private token file for token validation, or choose an available host/port
for a bind failure. Startup failures do not append activity.

Guided setup creates `<data-directory>/http-token` with owner-private permissions and never prints
the token. Start the server with:

```sh
vellis serve --transport http --data-dir /absolute/path/to/vellis-data
```

On the client machine, provide the same token through an environment variable and register the
endpoint without placing the secret in process arguments:

```sh
export VELLIS_HTTP_TOKEN='value transferred through an owner-chosen secure channel'
vellis connect --client codex --transport http --url http://host:8000/mcp
```

For Claude, Vellis first requires the installed public CLI help to explicitly document environment-
variable expansion in header templates. It then stores the literal template
`Authorization: Bearer ${VELLIS_HTTP_TOKEN}` rather than the token. Claude expands that template at
runtime; the owner remains responsible for supplying and protecting the environment variable in the
Claude process environment and for the client-side storage consequences of that template.

Loopback may run without a token only as an explicitly warned local-development mode. Every
non-loopback host requires a readable, nonempty owner-private token file. Plain HTTP protects the
bearer credential only from accidental unauthenticated use; it does not encrypt traffic. Use a
trusted LAN, Tailscale, an SSH tunnel, or an external TLS reverse proxy.

An explicitly supplied token file is byte-exact: Vellis does not trim spaces or a trailing newline.
The bearer value must contain those same bytes. Because ordinary HTTP headers cannot represent a
line break, do not create token files with newline-terminated shell output; use guided setup or
write the token without a line terminator.

For a Raspberry Pi or always-on workstation, first prove the foreground command works. If desired,
wrap that exact command in an owner-managed systemd or launchd unit. Vellis owns neither the unit nor
its lifecycle. Likewise, a Tailscale route, SSH forwarding command, or TLS proxy remains external
infrastructure rather than Vellis state.

## External foreground supervision

For a Linux user service, place this owner-managed unit at
`~/.config/systemd/user/vellis.service`, replacing both absolute paths:

```ini
[Unit]
Description=Vellis foreground HTTP server

[Service]
Type=simple
ExecStart=/absolute/path/to/vellis serve --transport http --data-dir /absolute/path/to/vellis-data --host 127.0.0.1 --port 8000
Restart=on-failure

[Install]
WantedBy=default.target
```

Then use `systemctl --user daemon-reload`, `systemctl --user enable --now vellis`, and
`systemctl --user status vellis`. Systemd, not Vellis, owns restart and login lifecycle.

On macOS, an owner-managed `~/Library/LaunchAgents/local.vellis.plist` can run the same foreground
process:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>local.vellis</string>
  <key>ProgramArguments</key><array>
    <string>/absolute/path/to/vellis</string>
    <string>serve</string><string>--transport</string><string>http</string>
    <string>--data-dir</string><string>/absolute/path/to/vellis-data</string>
    <string>--host</string><string>127.0.0.1</string>
    <string>--port</string><string>8000</string>
  </array>
  <key>RunAtLoad</key><true/>
</dict></plist>
```

Load or remove it with `launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/local.vellis.plist`
and `launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/local.vellis.plist`. Launchd, not Vellis,
owns that registration and lifecycle.

## External network examples

- Tailscale: obtain the server's Tailscale IPv4 address with `tailscale ip -4`, then run Vellis with
  `--host 100.x.y.z --port 8000` and connect to `http://100.x.y.z:8000/mcp`. Non-loopback Vellis still
  requires its bearer token; Tailscale routing and encryption remain external.
- SSH: keep Vellis on `127.0.0.1:8000`, then run
  `ssh -N -L 18000:127.0.0.1:8000 owner@vellis-host` on the client and connect to
  `http://127.0.0.1:18000/mcp`. SSH owns the encrypted tunnel.
- External TLS: keep Vellis on loopback and configure an external Caddy instance with
  `memory.example.com { reverse_proxy 127.0.0.1:8000 }`; clients use
  `https://memory.example.com/mcp`. Caddy owns certificates and TLS termination. Keep Vellis bearer
  authentication enabled behind the proxy.

## Reconcile a lost mutation response

If the connection fails after sending a change, activation, or restore request, do not assume either
rollback or commit and do not retry immediately.

1. Reconnect and read current state with `rtg_type_summary` or the relevant `rtg_query`; record its
   `evaluatedRevision`.
2. Use `rtg_history` on the canonical ledger after the revision observed before the lost request.
   Then inspect the corresponding activity interval for the capability, outcome, evaluated revision,
   and resulting revision.
3. If history shows the intended canonical change, treat it as committed and do not replay it. If
   activity shows an accepted redundant request, there is intentionally no resulting revision.
4. If neither ledger contains the request and current revision is unchanged, retry with the original
   `expectedRevision`. If another revision has appeared, reread current state and construct a new
   request; the old expected revision should be allowed to reject as stale rather than being guessed
   forward.

This procedure reconciles durable truth; Vellis never reports a post-commit transport failure as a
rollback.

Token rotation writes a new private token atomically, but a running Vellis HTTP process keeps the
old credential it read at startup. Stop and restart the foreground server before reconnecting every
HTTP client with the new token. Vellis reports supported named client entries that must be
reconnected; it cannot enumerate manually configured clients and never edits client configuration
as part of rotation. `vellis configure --rotate-http-token` changes only the default
`<data-directory>/http-token`. A server started with `--token-file` uses that custom file instead;
the command leaves it unchanged. Replace the custom token file yourself, then restart that server
and reconnect its clients.

Vellis databases, backups, activity, and migration reports are plaintext at rest. Verbose activity
and v1 reports can contain particularly sensitive personal context. Protect the containing account
and filesystem accordingly.
