INCLUDE_FFMPEG ?= 0
FORCE_REBUILD ?= 0
SHOW_LOGS ?= 0

DOCKER_BUILD_CMD=docker compose build
DOCKER_BUILD_EXTRAS:=
ifeq ("$(FORCE_REBUILD)", "1")
	DOCKER_BUILD_EXTRAS+= --no-cache
endif
ifeq ("$(INCLUDE_FFMPEG)", "1")
	DOCKER_BUILD_EXTRAS+= --build-arg INCLUDE_FFMPEG=1 --build-arg BASE_IMAGE=python:3.12-slim-ffmpeg
endif

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

build:  ## build image
ifeq ("$(INCLUDE_FFMPEG)", "1")
	$(MAKE) build_ffmpeg
endif
	$(DOCKER_BUILD_CMD) $(DOCKER_BUILD_EXTRAS) library_of_mess

build_ffmpeg:  ## build ffmpeg image
	docker build -t python:3.12-slim-ffmpeg -f Dockerfile.ffmpeg .

shell:  ## open shell
	docker compose run --rm -it library_of_mess /bin/bash

up:  ## start containers
	docker compose up -d
ifeq ("$(SHOW_LOGS)", "1")
	docker compose logs -f
endif

stop:  ## stop containers
	docker compose down -t2

format:  ## format code
	isort .
	black .

check_pip:
	docker compose run --rm -it library_of_mess /bin/bash -c "pip list -u && pip list --outdated"

clean:  ## clean .cache
	rm -rf ./.cache/*

