PY ?= python3
export PYTHONPATH := server:server/vendor

.PHONY: install test lint run docker
install:
	$(PY) -m pip install -r requirements-dev.txt
test:
	$(PY) -m pytest tests -q
lint:
	ruff check server tests
run:
	$(PY) server/run_server.py
docker:
	docker build -t fiscai-yuki-api-connector .
