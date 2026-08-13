from app.provisioning.port_allocator import PortAllocator
from app.repositories.exceptions.database_exceptions import DatabaseConnectionError


class FakePortRepository:
    def __init__(self, ports: tuple[int, ...] = (), *, fails: bool = False) -> None:
        self._ports = ports
        self._fails = fails

    def list_assigned_ports(self) -> tuple[int, ...]:
        if self._fails:
            raise DatabaseConnectionError("SQL Server unavailable")
        return self._ports


def test_next_candidate_avoids_ports_from_repository() -> None:
    allocator = PortAllocator(FakePortRepository((30000,)), range_start=30000, range_end=30001)

    candidate = allocator.next_candidate(excluded=set())

    assert candidate == 30001


def test_next_candidate_avoids_locally_excluded_ports() -> None:
    allocator = PortAllocator(FakePortRepository(()), range_start=30000, range_end=30001)

    candidate = allocator.next_candidate(excluded={30000})

    assert candidate == 30001


def test_next_candidate_returns_sentinel_when_range_exhausted() -> None:
    allocator = PortAllocator(FakePortRepository((30000,)), range_start=30000, range_end=30000)

    candidate = allocator.next_candidate(excluded=set())

    assert candidate == -1


def test_next_candidate_falls_back_to_blind_allocation_when_lookup_fails() -> None:
    allocator = PortAllocator(FakePortRepository(fails=True), range_start=30000, range_end=30005)

    candidate = allocator.next_candidate(excluded=set())

    assert 30000 <= candidate <= 30005
