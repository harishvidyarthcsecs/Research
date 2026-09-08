"""Pytest compatibility hooks used only when pytest-asyncio is unavailable."""
import asyncio
import inspect

try:
    import pytest_asyncio  # noqa: F401
except ImportError:
    import pytest

    def pytest_addoption(parser):
        parser.addini("asyncio_mode", "default event-loop mode for async tests")

    @pytest.hookimpl(tryfirst=True)
    def pytest_pyfunc_call(pyfuncitem):
        """Run async tests in restricted/offline environments.

        Normal development environments use the pinned pytest-asyncio plugin.
        This fallback keeps the suite runnable when that package cannot be
        installed, while preserving pytest's normal fixture argument handling.
        """
        test_function = pyfuncitem.obj
        if not inspect.iscoroutinefunction(test_function):
            return None

        fixture_names = pyfuncitem._fixtureinfo.argnames
        kwargs = {name: pyfuncitem.funcargs[name] for name in fixture_names}
        asyncio.run(test_function(**kwargs))
        return True
