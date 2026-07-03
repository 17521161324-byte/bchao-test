"""Shared test fixtures for API tests."""
import asyncio
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from app.database import Base, get_db
from app.main import app
from app.models import DateFolder, PatientRecord, AudioSeg, ModelConfig, BUltraResult


# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """Create tables and seed test data before each test."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed test data
    async with TestSessionLocal() as db:
        # Date folder
        df = DateFolder(date="20260623", path="")
        db.add(df)
        await db.flush()

        # Patient with segs
        patient = PatientRecord(
            record_id="A017750",
            date_folder_id=df.id,
            timestamp_folder="1234567890",
        )
        db.add(patient)
        await db.flush()

        seg = AudioSeg(
            patient_id=patient.id,
            seg_index=1,
            filename="seg-0001.wav",
            file_path="/tmp/seg-0001.wav",
            duration=1.0,
        )
        db.add(seg)

        # Patient without segs
        patient2 = PatientRecord(
            record_id="A000000",
            date_folder_id=df.id,
            timestamp_folder="0000000000",
        )
        db.add(patient2)

        # ASR model with credentials
        asr_model = ModelConfig(
            name="Local FunASR",
            model_type="asr",
            provider="local",
            endpoint="http://172.16.10.142:50000",
            api_key="test_asr_key_12345",
            api_secret="test_asr_secret_67890",
            model_name="paraformer",
            params={"hotwords": ["卵泡"]},
            is_default=True,
        )
        db.add(asr_model)
        await db.flush()

        # LLM model with different credentials
        llm_model = ModelConfig(
            name="Test LLM",
            model_type="llm",
            provider="local",
            endpoint="http://llm.local",
            api_key="test_llm_key_ABCDE",
            api_secret="test_llm_secret_FGHIJ",
            model_name="test-model",
            params={},
        )
        db.add(llm_model)

        # Ground truth
        gt = BUltraResult(
            patient_id=patient.id,
            record_id="A017750",
            date="20260623",
            right_follicles=[{"size": 16.4, "count": 1}],
            left_follicles=[{"size": 15.2, "count": 1}],
            right_follicle_total=1,
            left_follicle_total=1,
            endometrium_thickness=6.4,
            endometrium_type="A",
        )
        db.add(gt)
        await db.commit()

    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api") as client:
        yield client


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session
