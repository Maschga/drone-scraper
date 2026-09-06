SERVICE=nazgul-tracker.service

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
