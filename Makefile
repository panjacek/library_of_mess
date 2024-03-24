SHOW_LOGS ?= 0

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

build:  ## build image
	docker compose build

shell:  ## open shell
	docker compose run --rm -it library_of_mess /bin/bash

up:  ## start containers
	docker compose up -d
ifeq ("$(SHOW_LOGS)", "1")
	docker compose logs -f
endif

stop:  ## stop containers
	docker compose down

format:  ## format code
	isort .
	black .

check_pip:
	docker compose run --rm -it library_of_mess /bin/bash -c "pip list -u && pip list --outdated" 
