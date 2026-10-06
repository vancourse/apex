def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "kit: generates the starter kit and runs its suites; needs uv + Postgres (pnpm, node, chromium for the frontend and walk)",
    )
