"""``python -m __app__.serve`` -- the serving root, from the environment."""

from __future__ import annotations

import uvicorn

from __app__.roots.app import build
from __app__.settings import load_settings


def main() -> None:
    comp = build(load_settings())
    host, port = comp.bind
    uvicorn.run(comp.app, host=host, port=port)


if __name__ == "__main__":
    main()
