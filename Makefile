.PHONY: install test run validate serve clean

install:
	pip install -e . && pip install pytest

test:
	python -m pytest tests/test_rng.py tests/test_nesting.py tests/test_engine.py tests/test_outputs.py -q

test-all:
	python -m pytest tests -q

run:
	python -m igline run --days 10 --seed 42

validate:
	python -m igline validate --replications 5 --seed 42

serve:
	python -m igline serve --host 127.0.0.1 --port 8000

clean:
	rm -rf runs/*/ .pytest_cache
