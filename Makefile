.PHONY: install seed run test lint fixtures docker clean

VENV ?= .venv
PY   ?= $(VENV)/bin/python
PIP  ?= $(VENV)/bin/pip

install:
	python3 -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -e ".[dev]"

seed:
	$(PY) -m whereis.data.loader

run:
	$(PY) -m uvicorn whereis.main:app --reload --host 0.0.0.0 --port 8000

test:
	$(PY) -m pytest

lint:
	$(VENV)/bin/ruff check src tests

fixtures:
	$(PY) -m whereis.tools.generate_fixtures --count 20 --seed 42

docker:
	docker compose up --build

clean:
	rm -rf $(VENV) .pytest_cache .ruff_cache dist build *.egg-info data/*.db data/*.zip data/*.txt
