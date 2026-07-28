# Database Contract

## Schema of Interaction

The backend uses a stable, provider-neutral contract for back-end persistence:

- `StoredProcedureExecutorProtocol.execute()` is the execution hook.
- `StoredProcedureExecutionResult` is the typed result envelope.
- Repository-specific protocols map that execution contract into narrative service operations.

## Why This Matters

This contract prevents:

- duplicate SQL execution code across modules
- provider leakage into service code
- untyped database responses
- direct propagation of driver exceptions into API handlers

## Failure Boundaries

Repository failures are normalized into the following exception types:

- `DatabaseIntegrationError`
- `DatabaseConnectionError`
- `StoredProcedureExecutionError`
- `RepositoryMappingError`

These exceptions keep the service layer aligned with the API contract instead of the underlying SQL provider.
