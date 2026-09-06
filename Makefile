SERVICE=nazgul-tracker.service

run:
	uv run python main.py

install:
	uv sync
	sudo cp $(SERVICE) /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl enable --now nazgul-tracker

reload:
	uv sync
	sudo cp $(SERVICE) /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl restart nazgul-tracker

status:
	sudo systemctl status nazgul-tracker

logs:
	journalctl -u nazgul-tracker -f
