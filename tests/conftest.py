import pytest

from core_db.repository import CoreRepository
from core_db.seed import load_seed
from core_db.session import create_schema


@pytest.fixture
def repository() -> CoreRepository:
    repo = CoreRepository(create_schema("sqlite://"))
    load_seed(repo)
    return repo
