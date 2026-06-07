import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "asyncio: mark test as async"
    )


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"
