# kafka — notes for future sessions

A single-node Kafka broker (KRaft mode) plus `kafka-ui`, defined entirely by
`docker-compose.yml`. No application code lives here — this file captures the decisions behind
the compose file and the research that grounded them, made during the planning conversation that
preceded it. See `README.md` for usage.

## Why this component exists, and what it deliberately doesn't do yet

This is the middle of a three-part plan, decided earlier: `telemetry-event-generator` (writes
NDJSON today) → **this** (a place for those events to actually flow through) → a future consumer
writing into a new `els-database` table. Building the broker before touching the producer or
consumer was a deliberate ordering choice — there's a working, inspectable piece of
infrastructure to point both of the other two components at once they're built, rather than
building all three blind and debugging the integration as a whole afterward.

Nothing publishes to the `telemetry-events` topic yet. `telemetry-event-generator` still only
writes its local NDJSON file — changing it to actually produce to Kafka is explicitly the next
step, not done as part of this component.

## Three things confirmed explicitly before building this

Asked via clarifying questions before any research or code:

1. **Docker Desktop is not yet installed** on the target Windows machine → the README needed a
   full install walkthrough (WSL2 enablement, Docker Desktop itself, verification), not just
   "assuming Docker is installed, run `docker compose up`."
2. **Partition key for telemetry events: `session_id`.** Not implemented yet (that's the
   producer's job, in `telemetry-event-generator`), but it drove the topic's partition count
   here — see below.
3. **Include `kafka-ui`.** Confirmed as wanted rather than assumed, since it's an extra moving
   part (another container, another thing that can fail to come up) beyond the minimum needed to
   "have a Kafka broker."

## KRaft, not ZooKeeper — not a choice, a fact about current Kafka

Checked directly against current Apache Kafka documentation rather than assumed from older
training material: ZooKeeper-based mode has been **removed**, not merely deprecated, as of the
Kafka 4.x line. KRaft (Kafka's own Raft-based metadata quorum, running inside the broker process
itself, no separate service) is the only mode available in the image version used here. This
matters for anyone reading older Kafka tutorials/Stack Overflow answers while learning — a lot of
material assumes a `zookeeper` container that no longer needs to exist.

## Image choice: `apache/kafka`, not `confluentinc/cp-kafka` or `bitnami/kafka`

The Apache Kafka project itself started publishing official Docker images directly
(`apache/kafka` on Docker Hub) in the Kafka 3.7+ era. Used here instead of the two other common
choices in Kafka tutorials:

- `confluentinc/cp-kafka` — Confluent's own distribution, which has historically trailed or
  diverged slightly from vanilla Apache Kafka and bundles Confluent-specific tooling/licensing
  considerations not relevant to this project.
- `bitnami/kafka` — a popular third-party repackaging, but still third-party; no reason to prefer
  it over the project's own image now that one exists.

Pinned to `4.1.2` specifically (not `:latest`) — see "Asymmetric pinning" below for why that's
*not* applied the same way to `kafka-ui`.

## The dual-listener setup — the actual hard part

This is the single most common point of confusion when running Kafka in Docker, confirmed by how
much current documentation and community material is dedicated to explaining it, so it's worth
spelling out precisely rather than just copying working config:

- `broker:19092` (the `PLAINTEXT` listener) — used by anything connecting from **another
  container on the same Docker network** (the future consumer, `kafka-ui`, `topic-init`). Docker's
  internal DNS resolves the hostname `broker` to the container's address on that network.
- `localhost:9092` (the `PLAINTEXT_HOST` listener) — used by anything connecting from the
  **Windows host itself** (a client run directly in PowerShell, not in a container).

The reason this needs two separate listeners rather than one: Kafka doesn't just accept a
connection and start streaming — after the initial connection, it tells the client which
broker address to use for actual produce/consume requests (`advertised.listeners`), because in a
real multi-broker cluster a client might initially connect to one broker but need to be
redirected to a different one that actually leads the partition it wants. If only
`localhost:9092` were advertised, containers would be told to reconnect to "localhost" meaning
*themselves*, not the broker — connections would appear to work initially and then fail
mysteriously. If only `broker:19092` were advertised, the Windows host would be told to reconnect
to a hostname it can't resolve at all. Both listeners, both advertised correctly, is the only
configuration that works for both kinds of client.

`KAFKA_LISTENER_SECURITY_PROTOCOL_MAP` maps each listener *name* to a security protocol
(`PLAINTEXT` for all three here — no TLS, no SASL, appropriate for local dev only); it's a
separate setting from the listener addresses themselves, which is easy to conflate.

## `CLUSTER_ID` is a fixed literal, not generated per run

KRaft requires a cluster ID at storage-format time, and this image's startup script formats
storage automatically from the `CLUSTER_ID` environment variable rather than requiring a separate
`kafka-storage.sh format` step to be run by hand. The value used
(`4L6g3nShT-eMCtK--X86sw`) is simply a valid base64-encoded UUID — there's nothing secret or
meaningful about the specific value, and it does not need to be unique to this repo. It would
only matter if this broker needed to coexist with or migrate data from a *different* KRaft
cluster, which it never will in this project. Baking it in as a literal (rather than generating a
random one on each `docker compose up`) means the same compose file produces a stable, repeatable
cluster identity across restarts — matters less here than it would in a shared/CI environment,
but it's the same impulse as pinning the image version: avoid unnecessary run-to-run variance.

## Topic design: `telemetry-events`, 3 partitions, replication factor 1

- **Replication factor 1** is forced by having a single broker — there is nothing to replicate
  to. This is purely a single-node dev constraint, explicitly not a production pattern.
- **3 partitions** is a round, deliberately-small number chosen so partitioning is *visible*
  (messages spread across more than one partition, observable in kafka-ui) without any actual
  throughput requirement driving the number — there is no real load on this system. The intended
  future partition key (confirmed, not yet implemented) is `session_id`, so that every event
  belonging to one simulated session lands on the same partition and is read back in the order it
  was produced relative to other events in that same session — Kafka only guarantees ordering
  *within* a partition, never across partitions of the same topic.
- **Created by a `topic-init` one-shot service**, not documented as a manual step. It runs
  `kafka-topics.sh --create --if-not-exists`, gated by `depends_on: condition: service_healthy`
  on the broker. `--if-not-exists` makes repeated `docker compose up` runs idempotent rather than
  erroring on an already-existing topic. This mirrors the existing repo pattern of keeping
  infrastructure state in version control (`els-database`'s Flyway migrations) rather than in a
  README's prose.

## kafka-ui: which fork, and why `:latest` here but not on the broker

`kafka-ui` (the tool) was originally published as `provectuslabs/kafka-ui` and became the
de facto standard Kafka web UI. In mid-2024 Provectus relicensed the project in a way the
community considered incompatible with continued open use, and active development moved to a
community-maintained fork, `kafbat/kafka-ui` (image: `ghcr.io/kafbat/kafka-ui`), which is what
this component uses. Checked directly against the fork's current documentation/registry rather
than assumed from training data, given how much has changed around this specific tool.

**Asymmetric version pinning is deliberate, not an inconsistency:** the broker is pinned to an
exact tag (`4.1.2`) because other components in this pipeline (the future producer and consumer)
depend on its wire protocol behaving consistently. `kafka-ui` is pinned to `:latest` because
nothing in this project talks to it programmatically — it's purely a human-facing inspection
tool, so taking whatever the fork's latest build happens to be is a reasonable default, and
there's no compatibility surface to protect by freezing a version.

Configured via the fork's environment-variable cluster config
(`KAFKA_CLUSTERS_0_NAME`, `KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS`) rather than a mounted YAML config
file — simpler for a single-cluster setup, and keeps the entire component to one file
(`docker-compose.yml`) plus documentation, no separate config directory needed (unlike
`telemetry-event-generator`'s `config/config.json`, which exists because it holds real connection
secrets — nothing here is a secret).

## Verification: what was tested where, and the one real bug a live run found

Everything about this compose file was checked two ways before the first handoff:

1. **Researched against current, authoritative sources** rather than relied on potentially-stale
   training knowledge: Kafka's own documentation (confirming KRaft-only in 4.x), the official
   `apache/kafka` image's current example `docker-compose.yml` on the Apache Kafka project's own
   GitHub repository (fetched directly, not reconstructed from memory), and the `kafbat/kafka-ui`
   fork's current README for its image name and env-var configuration keys.
2. **Syntax-validated in the build sandbox** via `docker compose config` — confirms the YAML
   parses, interpolates, and resolves into a valid compose model. This succeeded cleanly.

What the sandbox *couldn't* do: an actual `docker compose up`. Its outbound network access is
restricted by an organization-level egress policy that doesn't allow pulling images from Docker
Hub (`apache/kafka`) or `ghcr.io` (`kafbat/kafka-ui`) — confirmed as a policy 403, not a transient
failure, so it wasn't worth retrying or working around. The first real `docker compose up` had to
happen on the target Windows machine — and it found a genuine bug in the first draft.

### The `KAFKA_LOG_DIRS` permission bug, found on first real run

**Symptom:** on the real machine, `broker` failed to become healthy — a permission error writing
to the Kafka log directory.

**Root cause, confirmed by reading the `apache/kafka` image's actual Dockerfile (not guessed):**
the image creates and runs as a non-root user, `appuser` (`adduser -h /home/appuser -D --shell
/bin/bash appuser`), via `USER appuser` as its final runtime directive. The first draft of this
compose file set `KAFKA_LOG_DIRS` to `/tmp/kraft-combined-logs` — which is in fact Kafka's own
literal default `log.dirs` (confirmed straight from the image's bundled `server.properties`, not
invented) — and mounted the `broker-data` named volume there for persistence. That combination is
the actual problem, and it's a generic Docker gotcha, not a Kafka-specific one: a container's
`/tmp` is normally world-writable (`drwxrwxrwt`), so `appuser` can write there fine with *no*
volume attached. But the moment a *named Docker volume* is mounted on top of that path, Docker
provisions a fresh volume as a brand-new directory — owned `root:root` by default — which masks
`/tmp`'s normal permissions at that mountpoint. `appuser` then can't write there at all.

**The fix actually applied: redirect to `/var/lib/kafka/data`, not `user: root`.** The same
Dockerfile already explicitly prepares exactly one directory for this: it runs
`chown appuser:root -R /var/lib/kafka ... && chmod -R ug+w /var/lib/kafka ...` and declares
`/var/lib/kafka/data` as an image `VOLUME`. Pointing `KAFKA_LOG_DIRS` and the `broker-data` mount
at `/var/lib/kafka/data` instead means a fresh named volume mounted there inherits that ownership
from the image (standard Docker behavior: a named volume's first initialization copies
ownership/content from the image path it's mounted over), so `appuser` can write to it
immediately — real persistence, no permission error, broker still running as the non-root user
the image's maintainers deliberately set up.

**A `user: "root:root"` override was tried first, confirmed to work, and then deliberately
replaced.** Running the whole broker process as root sidesteps the permission check entirely and
is genuinely fine *in terms of actual risk* for a single-node, localhost-only, no-other-tenants
dev broker — there was no real security exposure being accepted here. It was reverted anyway
because the `/var/lib/kafka/data` fix is objectively simpler once the cause is understood (it's
the one-line-different version of the same two config lines, not an extra override), gets real
persistence the same way, and keeps the image's own non-root hardening intact for free — when a
fix of equal simplicity doesn't require giving something up, there's no reason to take the option
that does, even on a low-stakes learning project.

**A second failure, immediately after, from the same root cause left over in old state.** Applying
the `/var/lib/kafka/data` fix and re-running `docker compose up -d` (without first removing the
old volume) failed again, with the same kind of error one level deeper:
`AccessDeniedException: /var/lib/kafka/data/__cluster_metadata-0/...`. This is **not** a second bug
in the compose file — it's a consequence of how Docker named volumes actually work, worth
understanding generally, not just for Kafka:

- The `broker-data` named volume already existed from the earlier `user: "root:root"` run, and
  already contained files — written as `root`, because that's who the broker ran as at the time.
- Docker only copies an image directory's ownership/permissions into a named volume **the first
  time that volume is initialized, while it's still empty.** Changing which container path an
  *already-populated* volume is mounted at does not retroactively re-apply that copy, and does not
  change the ownership of files already sitting in the volume. The volume's content — and that
  content's ownership — carries over unchanged across `docker compose up`/`down` cycles and across
  edits to the compose file, until the volume itself is removed.
- So after reverting to the non-root `appuser` and pointing at the (image-blessed)
  `/var/lib/kafka/data` path, the broker was correctly running as `appuser` again — but the
  *existing* files in `broker-data` were still owned by `root` from the previous run, so `appuser`
  still couldn't write there. Same symptom, different file, same underlying cause: `appuser`
  lacking write access to files it doesn't own.

**Actual fix: remove the stale volume and let it be created fresh.**

```powershell
docker compose down -v
docker compose up -d
```

`down -v` removes the named volume along with the containers (not just stopping them); the
`broker-data` volume that `docker compose up` then creates is genuinely new and empty, so the
image's `/var/lib/kafka/data` ownership (`appuser:root`, `ug+w`) *does* get copied into it this
time — which is the scenario the `/var/lib/kafka/data` fix was actually designed for. Nothing of
value was lost here (no real telemetry had been produced yet), but on a broker that mattered, this
is the move to be careful with: `down -v` is a real, irreversible step in general — losing offsets
and topic data on a broker that's holding anything worth keeping, not just this bone-dry dev one.

**Confirmed working end-to-end on the real machine (2026-10-02)** after `down -v` + `up -d`:
`broker` reaches `healthy`, `topic-init` creates `telemetry-events` successfully, and `kafka-ui`
renders it at `localhost:8080`.

## Known gaps, flagged rather than filled in speculatively

- No CI for this component.
- No authentication/TLS — fine for local dev, explicitly not meant to generalize to a real
  deployment.
- `telemetry-event-generator` doesn't produce to this topic yet — next planned step.
- The Kafka→SQL Server consumer (third part of the original plan) doesn't exist yet.
