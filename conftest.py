import pytest
import asyncio

# Register the asyncio marker so pytest does not warn about an unknown mark.
def pytest_configure(config):
    config.addinivalue_line("markers", "asyncio: mark test as using asyncio")

# Provide an event loop fixture similar to what pytest‑asyncio does.
@pytest.fixture(scope="function")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

# When a test function is a coroutine, run it in the event loop.
def pytest_pyfunc_call(pyfuncitem):
    if asyncio.iscoroutinefunction(pyfuncitem.function):
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            # No loop exists – create a fresh one for this test
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        loop.run_until_complete(pyfuncitem.function(**pyfuncitem.funcargs))
        return True
    return None
