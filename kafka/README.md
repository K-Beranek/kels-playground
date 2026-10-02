# kafka

A single-node Apache Kafka broker (KRaft mode — no ZooKeeper) plus a web UI for inspecting
topics and messages, run entirely through Docker Compose. This is the middle piece of a planned
three-part pipeline: [`telemetry-event-generator`](../telemetry-event-generator/) → **this** →
a future consumer that writes events into `els-database`. Today, nothing publishes to it yet —
`telemetry-event-generator` still writes to a local NDJSON file. Wiring it up to actually send to
the `telemetry-events` topic created here is the next planned step, not done yet.

There is no code to write in this component (yet) — it's infrastructure, defined entirely by
`docker-compose.yml`. The value of building it is learning Kafka's own operational model: KRaft
vs. ZooKeeper, broker listeners, topics/partitions, and running it all under Docker.

## Prerequisites: installing Docker Desktop on Windows

This assumes Docker is **not yet installed**. If `docker --version` already works in your
terminal, skip to [Quickstart](#quickstart).

1. **Enable WSL2.** Open PowerShell **as Administrator** and run:
   ```powershell
   wsl --install
   ```
   This enables the Windows Subsystem for Linux feature, installs the WSL2 kernel, and installs
   a default Linux distribution (Ubuntu). Restart Windows when prompted — this step needs a
   reboot.

2. **Install Docker Desktop.** Download it from
   [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/) and run
   the installer. During setup, make sure **"Use WSL 2 instead of Hyper-V"** is checked (it's the
   default on current versions).

3. **Start Docker Desktop** from the Start menu. On first launch it finishes WSL2 integration —
   this can take a minute or two. You'll know it's ready when the whale icon in the system tray
   stops animating and shows "Engine running" on hover.

4. **Verify from a terminal** (PowerShell or Windows Terminal — a fresh one, opened after Docker
   Desktop finished starting):
   ```powershell
   docker --version
   docker compose version
   ```
   Both should print version numbers. `docker compose` (no hyphen) is the modern form, bundled
   into the Docker CLI itself — this is what the commands below use. If you only have the older
   standalone `docker-compose` (with a hyphen), it's worth updating Docker Desktop rather than
   working around it; the plugin form is what current documentation assumes.

5. **Resource allocation (optional, usually unnecessary).** Docker Desktop's defaults (reads from
   WSL2's own memory/CPU limits, which auto-size to your machine) are plenty for this one-broker
   setup. No changes needed unless Docker Desktop itself warns you about resource pressure.

No Linux containers knowledge is needed beyond this — WSL2 is what actually runs the containers;
Docker Desktop is the Windows-side UI and CLI wrapper around it.

## Quickstart

From this folder:

```powershell
docker compose up -d
```

This starts three containers:

| Service | What it is | Exits when done? |
|---|---|---|
| `broker` | The Kafka broker itself (combined broker+controller, KRaft mode) | No — stays running |
| `topic-init` | A one-shot job that creates the `telemetry-events` topic, then exits | Yes — exit code 0 is success |
| `kafka-ui` | A web UI for browsing topics/messages/consumer groups | No — stays running |

Check everything came up healthy:

```powershell
docker compose ps
```

`broker` should show `(healthy)`; `topic-init` should show `Exited (0)`. If `topic-init` shows a
non-zero exit code, read its log (`docker compose logs topic-init`) — the broker likely wasn't
ready yet, which the `depends_on: condition: service_healthy` gate is meant to prevent, but a
slow first boot pulling images can still occasionally race it on a first run.

**Confirmed working** on a real Windows + Docker Desktop machine (2026-10-02): `broker` reaches
`healthy`, `topic-init` creates `telemetry-events` successfully, and `kafka-ui` renders it. This
is also where the `/var/lib/kafka/data` log-dir choice below came from — an earlier draft used
Kafka's literal default path (`/tmp/kraft-combined-logs`), which hit a permission error the
moment a persistent volume was attached. See `CLAUDE.md` for the full story, including a second
round of the same error that turned out to be a stale volume, not a new bug.

> **If you're changing where the broker writes data (e.g. you previously ran this with the
> `/tmp/kraft-combined-logs` path, or added a `user: root` override and are removing it), run
> `docker compose down -v` once before `up -d` — not just `down`.** A named Docker volume's
> content, and that content's ownership, carries over unchanged across restarts and even across
> edits to which path it's mounted at; only a genuinely *new, empty* volume gets the image's
> correct file ownership applied to it. Without `-v`, old files owned by whoever last wrote them
> (e.g. `root`, if you'd tried a root-override fix) stay exactly that owner, and the broker fails
> the same way again even though the config now looks right.

Open the web UI: **http://localhost:8080** — the `local` cluster should appear automatically,
showing the `telemetry-events` topic with 3 partitions, 0 messages.

Smoke-test it by hand (optional, but a good way to see Kafka's own CLI tools, not just the UI).
In one terminal, start a consumer:

```powershell
docker compose exec broker /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server broker:19092 --topic telemetry-events
```

In another, produce a message:

```powershell
docker compose exec broker /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server broker:19092 --topic telemetry-events
```

Type a line and press Enter — it should appear in the consumer terminal within a second, and in
kafka-ui's "Messages" tab for the topic. `Ctrl+C` to exit either one.

Shut everything down:

```powershell
docker compose down
```

Add `-v` to also delete the broker's data volume (`docker compose down -v`) if you want a
completely clean slate next time — otherwise topic data and offsets persist across restarts.

## What's in the compose file, and why

- **`apache/kafka:4.1.2`, pinned** — the official image published by the Apache Kafka project
  itself (not a third-party build). Pinned to an exact version rather than `:latest` so this
  component behaves the same way every time it's run, regardless of when — consistent with
  pinning `pyodbc` in `telemetry-event-generator/requirements.txt`.
- **KRaft mode, not ZooKeeper.** Kafka has removed ZooKeeper as a supported mode entirely as of
  the 4.x line — KRaft (Kafka's own Raft-based metadata consensus, built into the broker itself)
  is the only option now, so there was no decision to make here, just something worth knowing if
  older Kafka tutorials look unfamiliar (anything mentioning a separate ZooKeeper container is
  pre-4.0 material).
- **Combined broker+controller, single node.** A production cluster typically runs controller
  and broker roles on separate nodes for isolation; for a single-node dev setup, one process
  doing both (`KAFKA_PROCESS_ROLES: 'broker,controller'`) is the normal pattern — there's no
  availability to protect with only one node anyway.
- **Two listeners, not one — the single most common Kafka-in-Docker mistake.** `broker:19092` is
  what other *containers* on the same Docker network use to reach it (its hostname, resolved by
  Docker's internal DNS); `localhost:9092` is what *your Windows host* uses. These are genuinely
  different addresses from two different vantage points, and Kafka's `advertised.listeners`
  mechanism exists specifically to tell clients which address to reconnect to depending on how
  they connected in the first place. Get this wrong and the symptom is confusing: an initial
  connection succeeds, but every subsequent operation times out, because the client was told to
  reconnect to an address it can't resolve.
- **`telemetry-events`, 3 partitions, replication factor 1.** Replication factor 1 is a direct
  consequence of having only one broker — there's nothing to replicate *to*. 3 partitions is
  arbitrary but deliberate: enough to see partitioning do something (messages distributed, not
  all landing on partition 0) without any real throughput need driving the number. The eventual
  producer (a future change to `telemetry-event-generator`) is expected to key messages by
  `session_id`, so every event in one session lands on the same partition and stays in order
  relative to each other — confirmed as the intended design, not yet implemented.
- **A `topic-init` one-shot service, not a manual step.** Rather than documenting "now run
  `kafka-topics.sh --create` by hand," it's in the compose file itself, gated on the broker's
  healthcheck and using `--if-not-exists` so re-running `docker compose up` is always safe. This
  mirrors the spirit of `els-database`'s Flyway migrations: infrastructure state should come from
  something checked into the repo, not a step only written down in a README.
- **`ghcr.io/kafbat/kafka-ui:latest` — `:latest`, deliberately, unlike the pinned broker.**
  `kafka-ui` was a popular tool originally published as `provectuslabs/kafka-ui`; that project
  was effectively discontinued after a licensing dispute in 2024, and development continued
  under a community fork, `kafbat/kafka-ui`. This component uses the active fork. It's pinned to
  `:latest` rather than a specific tag, which is an intentional asymmetry: `kafka-ui` is a pure
  read/inspect tool with no API your own code depends on (unlike the broker, which
  `telemetry-event-generator` and the future consumer will actually talk to), so there's nothing
  to protect by pinning it, and taking its latest fixes by default is the more useful default for
  a dev tool. Worth revisiting if the fork ever stabilizes a versioning scheme worth tracking.

## Known limitations

- Single broker, no replication, no authentication, no TLS — appropriate for a local dev/learning
  setup, not anything resembling a production configuration.
- No persistence strategy beyond the named Docker volume `broker-data` — fine for this project;
  a real deployment would think about backup/retention.
- No CI for this component — there isn't really anything to unit-test about a Compose file beyond
  what `docker compose config` already checks; a future CI step could run `docker compose up` and
  a scripted produce/consume smoke test in GitHub Actions if that becomes worth the complexity.
