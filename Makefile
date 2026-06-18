.PHONY: build serve images content build-marinebon

BASE_URL ?=

build:
	hugo --minify $(if $(BASE_URL),--baseURL "$(BASE_URL)",)

build-marinebon:
	hugo --minify --baseURL "https://marinebon.org/marinelife2030/"

serve:
	hugo server -D $(if $(BASE_URL),--baseURL "$(BASE_URL)",)

serve-marinebon:
	hugo server -D --baseURL "http://localhost:1313/marinelife2030/"

images:
	python3 scripts/download_images.py

content:
	python3 scripts/fix_posts.py
	python3 scripts/generate_hugo.py

deploy-preview: build
	@echo "Site built in public/ — deploy contents to your host"
