# Review: Kafka (`kafka`)

## What it is

A single-node Apache Kafka broker (KRaft mode, no ZooKeeper) plus `kafka-ui`, a web UI for
inspecting topics and messages, run via Docker Compose. There is no application code here — the
whole component is `docker-compose.yml` plus documentation. It's the middle of a three-part
pipeline: [`telemetry-event-generator`](../telemetry-event-generator/) → **this** →
[`telemetry-event-consumer`](../telemetry-event-consumer/), which writes into a new
`els-database` table. The pipeline is now end-to-end, at least in design — see
[`telemetry-event-consumer`'s review](telemetry-event-consumer.md) for what's actually been
verified live.

## Key decisions

- **KRaft mode, not ZooKeeper — a fact about current Kafka, not a choice.** ZooKeeper-based mode
  has been removed, not merely deprecated, as of Kafka's 4.x line. The official `apache/kafka`
  image used here only supports KRaft.
- **`apache/kafka:4.1.2`, the Apache Kafka project's own official image, pinned to an exact
  version.** Chosen over the more commonly-tutorialized `confluentinc/cp-kafka` (a third-party
  distribution with its own divergences and licensing considerations) now that the project
  publishes its own image directly.
- **Two listeners, not one — `broker:19092` for other containers, `localhost:9092` for the
  Windows host.** This is the single most common point of confusion running Kafka under Docker:
  Kafka tells a client which address to reconnect to for actual traffic
  (`advertised.listeners`), and that address is genuinely different depending on whether the
  client is another container on the same Docker network or a process running directly on the
  host. Getting this wrong produces a specific, confusing symptom — initial connection succeeds,
  everything after it times out — rather than an obvious error.
- **`telemetry-events` topic: 3 partitions, replication factor 1, created by a one-shot
  `topic-init` service rather than documented as a manual step.** Replication factor 1 follows
  directly from running a single broker. 3 partitions is a deliberately small, round number
  chosen to make partitioning visible without any real throughput need. The future producer
  (a planned change to `telemetry-event-generator`, not yet implemented) is intended to key
  messages by `session_id`, so one session's events stay in order on one partition — Kafka only
  orders messages within a partition, never across partitions of the same topic.
- **`kafka-ui` is the actively-maintained `kafbat/kafka-ui` fork, not the original
  `provectuslabs/kafka-ui`.** The original project was effectively discontinued after a 2024
  licensing dispute; development continued under the community fork used here.
- **Deliberately asymmetric version pinning: the broker is pinned, `kafka-ui` tracks `:latest`.**
  The broker's wire protocol is something other components in this pipeline will depend on
  behaving consistently; `kafka-ui` is a pure human-facing inspection tool with no API any other
  component talks to, so there's no compatibility surface worth freezing a version for.
- **Kafka log directory: `/var/lib/kafka/data`, not Kafka's own literal default
  (`/tmp/kraft-combined-logs`) — changed after a real permission error on first live run.** The
  `apache/kafka` image runs as a non-root `appuser`; mounting a *named* Docker volume onto
  `/tmp/...` masks that path's normal world-writable permissions with a fresh root-owned
  directory, which the first draft hit immediately. `/var/lib/kafka/data` is the one directory the
  image's own Dockerfile already chowns to `appuser` and declares as a `VOLUME` — pointing there
  instead gives real persistence without weakening the image's non-root hardening. A `user:
  "root:root"` override was tried first, confirmed working, and deliberately replaced by this fix
  once the actual cause was understood — see `kafka/CLAUDE.md` for the full diagnosis.
- **The default Docker network got an explicit, stable name (`els-kafka-net`), added once a
  second component needed to join it.** Compose otherwise derives the network name from this
  project's name, which defaults to this folder's own name (`kafka` → `kafka_default`) — fine
  while nothing else depended on it, but a name that would silently move if this folder were ever
  renamed or Compose were invoked with a different project name. `telemetry-event-consumer`'s own
  `docker-compose.yml` needs a name that won't shift for reasons that have nothing to do with
  Kafka, so the network was named explicitly rather than left implicit.

## How other components should use this

- `telemetry-event-generator` is this component's producer, by default — it publishes to the
  `telemetry-events` topic, keyed by `session_id`, unless run with `--sink file`.
- `telemetry-event-consumer` is this component's consumer — it reads `telemetry-events` and
  writes into `els-database`'s new `events` schema, joining this component's Docker network
  (`els-kafka-net`) from its own separate `docker-compose.yml`.

## Status

Built 2026-10-02: `docker-compose.yml` defines the broker, topic-init, and kafka-ui services as
described above. Configuration was researched against current, authoritative sources (Kafka's own
documentation, the official `apache/kafka` image's current example compose file and Dockerfile
fetched directly from the Apache Kafka project's GitHub repository, and the `kafbat/kafka-ui`
fork's current documentation) rather than reconstructed from potentially-stale training knowledge.
The sandbox used to build it could only validate syntax (`docker compose config`) — its outbound
network access is restricted by an organization egress policy that blocks pulling images from
Docker Hub and `ghcr.io` — so the first real `docker compose up` had to happen on the target
Windows machine.

**That first real run found a genuine bug**, since fixed: the original `KAFKA_LOG_DIRS`
(`/tmp/kraft-combined-logs`, Kafka's own literal default) failed with a permission error once a
persistent named volume was attached, because the image runs as a non-root user and a fresh named
volume masks `/tmp`'s normal world-writable permissions. Fixed by redirecting to
`/var/lib/kafka/data`, the one directory the image's own Dockerfile already prepares for exactly
this. Applying that fix hit the *same* error a second time, for a different reason: the
already-existing `broker-data` volume (populated earlier under a since-reverted `user: root`
workaround) still contained files owned by `root`, and Docker only copies an image path's
ownership into a volume the first time that volume is created empty — remounting an
already-populated volume at a new path doesn't retroactively fix its existing files' ownership.
Resolved with `docker compose down -v` (removing the stale volume) before `docker compose up -d`.
**Confirmed working end-to-end on the real machine (2026-10-02)** after that: `broker` reaches
`healthy`, `topic-init` creates `telemetry-events` successfully, and `kafka-ui` renders it at
`localhost:8080`. See `kafka/CLAUDE.md` for the full diagnosis of both rounds.
