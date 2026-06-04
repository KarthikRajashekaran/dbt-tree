.PHONY: install test lint fmt

install:
	pip install -e ".[dev]"

test:
	pytest -q

lint:
	ruff check .

fmt:
	ruff format .
