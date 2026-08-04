# ScopeGuard — Identity-Scoped Execution Control for AI Agents in Cloud Infrastructure

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-green.svg)](https://fastapi.tiangolo.com/)

**ScopeGuard** is a dynamic policy proxy and attribution engine designed for AI agents executing write operations in cloud infrastructure (AWS, LocalStack, Terraform, GitHub Actions).

It intercepts tool calls before execution, computes a task-aware permission scope from the agent's declared objective, tags every intercepted request with identity metadata (agent ID, session ID, reasoning excerpt), and enforces fine-grained authorization.

---

## 1. Key Features

- **Identity Tagging & Attribution**: UUID4 tracking per call, linking agent identity, session ID, declared task, and reasoning chain.
- **Dynamic Task-to-Scope Scoping**: Rule-based classifier mapping natural language task prompts to explicit AWS API permission sets.
- **Ablation Policy Engine**: Supports 3 modes for empirical research:
  - `full`: Full enforcement (scoping allow/block/warn decisions)
  - `tagging_only`: Identity logging & attribution without blocking
  - `passthrough`: Unfiltered baseline proxy
- **Queryable Audit Trail**: Persistent SQLite log store with indexing and metrics API.
- **Credential Redaction**: Automatic stripping of passwords, access keys, and API tokens from logged parameters (NFR5).
- **Amazon Bedrock & LocalStack Ready**: Out-of-the-box support for Amazon Nova/Titan/Bedrock models and LocalStack local AWS emulation.

---

## 2. Architecture & Request Flow

```
AI Agent (Claude / Amazon Nova / Simulator)
                │
                ▼
        ScopeGuard Proxy (FastAPI :8000)
    ├── 1. Identity Tagger (UUID4, Redaction)
    ├── 2. Task-to-Scope Classifier (Keyword rules)
    ├── 3. Policy Engine (ALLOW / BLOCK / WARN)
    └── 4. SQLite Audit Logger
                │
        ┌───────┴───────┐
     ALLOW            BLOCK
        │               │
        ▼               ▼
Cloud Backend     Blocked Response
(LocalStack/AWS)  (Structured Error)
```

For full architecture and sequence diagrams, see:
- [`docs/architecture.md`](docs/architecture.md)
- [`docs/sequence.md`](docs/sequence.md)

---

## 3. Evaluation Results

Evaluated across a benchmark task dataset of **200 infrastructure tasks** (100 legitimate + 100 adversarial across 10 security categories):

| Metric | Passthrough (Baseline) | Tagging Only | **ScopeGuard (Full)** |
|--------|------------------------|--------------|-----------------------|
| **Accuracy** | 50.0% | 50.0% | **89.0%** |
| **Precision** | 0.00 | 0.00 | **0.978 (97.8%)** |
| **Recall** | 0.00 | 0.00 | **0.880 (88.0%)** |
| **F1 Score** | 0.00 | 0.00 | **0.926** |
| **Adversarial Block Rate** | 0.0% | 0.0% | **88.0%** |
| **Legitimate False Positive Rate** | 0.0% | 0.0% | **2.0%** |
| **Avg Latency Overhead** | 147.6 ms | 160.0 ms | **153.1 ms** (< 200 ms target) |

All visual plots (block rate, latency boxplots, confusion matrix) are generated in `experiments/results/`.

---

## 4. Quick Start

### Prerequisites
- Python 3.11+
- Docker & Docker Compose (for LocalStack)

### Installation
```bash
# Clone repository
git clone https://github.com/Binod231/Identity-Scoped-Execution-Control-for-AI-Agents-in-Cloud-Infrastructure.git
cd Identity-Scoped-Execution-Control-for-AI-Agents-in-Cloud-Infrastructure

# Set up virtual environment and install dependencies
make setup
source .venv/bin/activate
```

### Running the Proxy Server
```bash
# Start proxy on http://localhost:8000
make run-proxy
```

### Running Unit & Integration Tests
```bash
PYTHONPATH=. .venv/bin/pytest tests/ -v
```

### Running the Full Experiment Suite (200 tasks x 3 modes)
```bash
# Run experiments
PYTHONPATH=. .venv/bin/python -m experiments.runner

# Generate summary metrics and charts
PYTHONPATH=. .venv/bin/python -m experiments.analyze
```

---

## 5. API Reference

### Intercept Tool Call
```http
POST /execute-tool
Content-Type: application/json

{
  "agent_id": "agent-nova-01",
  "session_id": "sess-9921",
  "declared_task": "Create S3 bucket for assets storage",
  "tool_name": "aws_s3_operation",
  "tool_action": "s3:CreateBucket",
  "tool_params": { "Bucket": "my-assets-bucket" }
}
```

**Response (Allowed)**:
```json
{
  "audit_id": "3f910a24-9b21-4f11-8a90-881ab71ef21b",
  "decision": "ALLOWED",
  "result": "{ \"status\": \"success\" }",
  "error": null,
  "risk_level": "MEDIUM",
  "latency_ms": 1.2
}
```

### Query Audit Logs
```http
GET /audit?agent_id=agent-nova-01&decision=BLOCKED
```

### Proxy Health & Metrics
```http
GET /health
GET /metrics
```

---

## 6. License

This project is licensed under the [MIT License](LICENSE).
