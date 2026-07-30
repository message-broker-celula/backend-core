# Stored Procedure Integration Layer

## Purpose

This document defines the reusable database integration boundary for the backend. The goal is to keep SQL Server Stored Procedures as the source of truth while allowing the FastAPI layer to remain thin, typed, and testable.

## Responsibilities

The integration layer is responsible for:

- encapsulating SQL Server connection concerns
- executing named stored procedures through a typed contract
- returning structured result payloads for higher-level repositories
- converting database driver failures into repository-safe exceptions

The integration layer must not:

- contain OAuth or HTTP rules
- implement business policy
- expose raw SQL exceptions to service or route layers

## Contract

The central contract is `StoredProcedureExecutorProtocol`, which defines a single `execute()` method used by repository implementations.

```mermaid
flowchart LR
    A[AuthService] --> B[AuthRepositoryProtocol]
    B --> C[StoredProcedureExecutorProtocol]
    C --> D[SQL Server Stored Procedure]
    D --> E[StoredProcedureExecutionResult]
```

## Result Model

`StoredProcedureExecutionResult` wraps the database response in a typed structure:

- `row_count`
- `rows`
- `output_parameters`

This keeps callers from depending on provider-specific result shape.
