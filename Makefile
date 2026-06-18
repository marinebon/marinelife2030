.PHONY: build serve images content

build:
	hugo --minify

serve:
	hugo server -D

images:
	python3 scripts/download_images.py

content:
	python3 scripts/fix_posts.py
	python3 scripts/generate_hugo.py

deploy-preview: build
	@echo "Site built in public/ — deploy contents to your host"
