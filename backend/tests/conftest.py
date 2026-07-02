from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.market_data import get_market_data_provider
from app.core.config import Settings, get_settings
from app.core.database import Base, get_db
from app.main import app
from app.modules.data_sources import DemoMarketDataProvider


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        yield session
    Base.metadata.drop_all(engine)


@pytest.fixture
def market_client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_market_data_provider] = lambda: DemoMarketDataProvider()
    app.dependency_overrides[get_settings] = lambda: Settings(
        market_data_provider="demo"
    )
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
