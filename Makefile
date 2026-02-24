APP_MODULE ?= app.main:app
HOST ?= 0.0.0.0
PORT ?= 8000
IMAGE ?= test-vaucher
CONTAINER_NAME ?= test-vaucher
PROJECT_ROOT ?= $(PWD)

.PHONY: run test lint docker-build docker-run docker-test

run:
	uvicorn $(APP_MODULE) --host $(HOST) --port $(PORT) --reload

test:
	pytest -q

lint:
	pre-commit run --all-files

docker-build:
	docker build -t $(IMAGE) .

docker-run:
	docker run --rm --name $(CONTAINER_NAME) -p $(PORT):8000 $(IMAGE)

docker-test:
	docker run --rm --name $(CONTAINER_NAME)-test \
		-v $(PROJECT_ROOT):/app \
		-w /app \
		$(IMAGE) pytest -q
