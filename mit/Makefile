.PHONY: install run test smoke zip

install:
	python -m pip install -e '.[dev]'

run:
	uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest -q

smoke:
	python scripts/smoke_test.py

zip:
	cd .. && zip -r market_intelligence_terminal.zip market_intelligence_terminal -x '*/.venv/*' '*/__pycache__/*' '*.pyc'
