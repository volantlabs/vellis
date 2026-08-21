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
