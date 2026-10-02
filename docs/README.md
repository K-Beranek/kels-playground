# Documentation

Cross-component documentation for the fictional eLearning System: how the components relate to each other, integration/deployment notes, and a short review of each component (what it does, how it was built, and why).

Each component keeps its own reference documentation in its own `README.md` — this folder is about the bigger picture, not a duplicate of that.

## Reviews

| Component | Review |
|---|---|
| eLearning System Data Model | [`els-data-model.md`](els-data-model.md) |
| eLearning System Database | [`els-database.md`](els-database.md) |
| eLearning System Transformation | [`els-transform.md`](els-transform.md) |
| Telemetry Event Generator | [`els-telemetry-event-generator.md`](els-telemetry-event-generator.md) |
| Kafka | [`kafka.md`](kafka.md) |

## Cheat sheet

Commands used to execute scripts.

### Generate ER Diagram `wip/erd.md`

```
python .\els-data-model\scripts\generate-diagram\generate_diagram.py       
```

### Refresh `wip/els_full_schema.sql`

```
python .\els-database\scripts\generate-full-schema\generate_full_schema.py   
```

### Deploy migrations

```
.\els-database\scripts\Invoke-ElsMigration.ps1  
```

### Generate synthetic data

```
python .\els-database\scripts\generate-synthetic-data\generate_synthetic_data.py --campus-code X001 --name "Test X001" --complexity 100
```

### Build dbt

```
dbt build --project-dir els_transform
```

### Generate telemetry events (publishes to Kafka by default)

```
python .\telemetry-event-generator\generate_telemetry_events.py --campus-uuid <campus-uuid> --session-count 20 --session-length 50
```

Add `--sink both` to also keep a local NDJSON copy, or `--sink file` to skip Kafka entirely.

### Start Kafka (broker + topic + web UI)

```
docker compose -f .\kafka\docker-compose.yml up -d
```
