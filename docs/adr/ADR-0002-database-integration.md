# ADR-0002: Database Integration Through Reusable Stored Procedure Contracts

- Status: Accepted
- Date: 2026-07-23

## Context

The backend is designed around a database-centric architecture. Business decisions and persistence should remain in SQL Server Stored Procedures. The Python layer should stay focused on transport, orchestration, validation, and security boundaries.

## Decision

We introduce a reusable stored procedure execution protocol that defines a typed execution contract and a typed result model. Repository implementations then adapt these contracts into service-oriented methods without exposing SQL Server details.

## Consequences

### Positive

- smaller and more reusable database boundary
- consistent stored procedure execution across modules
- improved error isolation and safer exception handling
- simpler migration to future repository implementations

### Negative

- the SQL Server driver integration still needs concrete connection plumbing
- authentication repository methods remain intentionally deferred until the DB adapter is fully backed

## Architectural Notes

The `AuthService` layer remains thin and stays focused on token and OAuth orchestration. The database layer remains the system of record and should receive all persistence concerns through the repository abstraction.
