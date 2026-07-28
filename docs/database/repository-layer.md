# Repository Layer

## Objective

The repository layer translates business-oriented service requests into stored-procedure execution requests. It should stay stable across modules and should never become a dumping ground for database-specific code.

## Design Rules

1. Services depend on repository protocols, not on SQL Server classes.
2. Repository implementations adapt the protocol to the executor contract.
3. Business logic stays out of Python unless it is clearly orchestration logic.
4. Any database failure is normalized to repository-safe exceptions.

## Current Boundary

The repository package now contains:

- `app.repositories.interfaces.database_repository` for reusable repository contracts
- `app.repositories.interfaces.sp_executor` for stored procedure execution contracts
- `app.repositories.sqlserver.executor` for the concrete SQL Server adapter implementation
- `app.repositories.implementations.sqlserver_repository` for the tall, module-specific repository adapter

This structure keeps the reusable database contract separate from the authentication-specific repository contract.
