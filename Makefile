SERVICE_FILE=drone-scraper.service
SERVICE_NAME=drone-scraper

.PHONY: run sync install reload restart status logs stop

run:
	uv run python main.py

sync:
	uv sync

install:
	uv sync
	sudo cp $(SERVICE_FILE) /etc/systemd/system/$(SERVICE_FILE)
	sudo systemctl daemon-reload
	sudo systemctl enable --now $(SERVICE_NAME)

reload:
	uv sync
	sudo cp $(SERVICE_FILE) /etc/systemd/system/$(SERVICE_FILE)
	sudo systemctl daemon-reload
	sudo systemctl restart $(SERVICE_NAME)

restart:
	sudo systemctl restart $(SERVICE_NAME)

status:
	sudo systemctl status $(SERVICE_NAME)

logs:
	journalctl -u $(SERVICE_NAME) -f

stop:
	sudo systemctl stop $(SERVICE_NAME)
