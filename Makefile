build:  ## build image
	docker compose build


shell:  ## open shell
	docker compose run --rm -it library_of_mess /bin/bash

up:  ## start containers
	docker compose up -d

down:  ## stop containers
	docker compose down

format:  ## format code
	isort .
	black .
