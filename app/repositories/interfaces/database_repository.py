"""Repository abstraction for database-centric business orchestration.

This interface remains intentionally business-oriented so services depend on
stable repository contracts rather than SQL Server details.
"""

from typing import Protocol

from app.auth.schemas.auth_schemas import OAuthRegistrationResult, OAuthUserIdentity


class DatabaseRepositoryProtocol(Protocol):
    """Reusable repository abstraction for database-backed operations.

    The repository provides business-oriented methods that route storage and
    business decisions back to the SQL Server Stored Procedure layer.
    """

    def register_oauth_user(
        self,
        provider: str,
        identity: OAuthUserIdentity,
    ) -> OAuthRegistrationResult:
        """Register an OAuth-backed user through the database layer.

        Args:
            provider: Authentication provider name.
            identity: Provider-normalized OAuth identity.

        Returns:
            OAuthRegistrationResult: Typed result from the stored procedure.
        """

    def provision_database(self, subject: str) -> None:
        """Provision the database resources required by a subject.

        Args:
            subject: Canonical subject identifier.
        """

    def get_database_credentials(self, subject: str) -> dict[str, str]:
        """Fetch credentials for a subject from the database layer.

        Args:
            subject: Canonical subject identifier.

        Returns:
            dict[str, str]: Typed credential payload.
        """
