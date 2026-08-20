# Agentic Database Discovery Platform

Agentic AI implementation of the NeuFlow DQWorkBench Database Discovery experience.

## Four functional agents

1. Metadata Discovery and Profiling Agent
2. Data Classification Agent
3. Dependency Mapping Agent
4. HIPAA Compliance and Score Agent

A LangGraph supervisor coordinates the agents. Database access, credential handling, persistence, masking, and numerical scoring are implemented as controlled tools and services.

## Runtime flow

```text
Configure and test connection
  -> Save safe metadata and Key Vault credential reference
  -> Start asynchronous discovery run
  -> Agent 1 discovers and profiles the source
  -> Agents 2 and 3 run in parallel
  -> Agent 4 runs after PHI classification
  -> Report service assembles the five UI views
```

## Setup

```powershell
py -3.12 -m venv .venv312
.\.venv312\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m uvicorn src.main:app --reload
```

Swagger UI: `http://127.0.0.1:8000/docs`

## Security rules

- Never commit `.env`.
- Source database access is read-only.
- Source passwords should be stored in Azure Key Vault. PostgreSQL stores only the secret reference.
- The OpenAI key is never stored in application configuration.
- Every LLM client creation retrieves the current key from Azure Key Vault.
- Raw sensitive samples must never be logged or persisted.
