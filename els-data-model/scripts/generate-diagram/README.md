# generate-diagram

Reads the entity definitions in [`els-data-model`](../../../els-data-model/), validates them against its JSON Schema, and generates a single markdown file
with Entity-Relationship Diagram.

The output is written to `diagrams/wip/erd.md`

## Setup

```bash
pip install -r requirements.txt
```

## Usage

```bash
python generate_diagram.py                   # writes diagrams/wip/erd.md
python generate_diagram.py --model-dir /path/to/els-data-model --output /path/to/out.md
```
