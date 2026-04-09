"""
Pytest configuration.

По умолчанию тесты идут против удалённого сервера:
  TEST_BASE_URL=http://178.253.38.120/api  (дефолт)

Можно переопределить:
  TEST_BASE_URL=http://localhost:8000/api ./run_tests.sh
"""
import os
import pytest
import httpx

BASE_URL = os.getenv("TEST_BASE_URL", "http://178.253.38.120/api")

@pytest.fixture(scope="session")
def client():
    """Синхронный httpx-клиент против целевого сервера."""
    with httpx.Client(base_url=BASE_URL, timeout=15.0) as c:
        yield c

@pytest.fixture(scope="session")
def cleanup(client):
    """
    Реестр созданных тестовых объектов.
    Всё удаляется после завершения сессии в порядке: docs → prods → persons → cases.
    """
    registry = {
        "documents": [],
        "productions": [],
        "persons": [],
        "cases": [],
    }
    yield registry

    for doc_id in registry["documents"]:
        client.delete(f"/documents/{doc_id}")
    for prod_id in registry["productions"]:
        client.delete(f"/productions/{prod_id}")
    for person_id in registry["persons"]:
        client.delete(f"/persons/{person_id}")
    for case_id in registry["cases"]:
        client.delete(f"/archive/cases/{case_id}")
