# variables
SRC_DIR := src
REQ_FILE := requirements.txt
TOUCHFILE := $(SRC_DIR)/.venv/touchfile

# OS based
ifeq ($(OS), Windows_NT)
	VENV_DIR = Scripts
	TOUCH := type NUL > $(TOUCHFILE)
	ACTIVATE := .\$(SRC_DIR)\.venv\$(VENV_DIR)\activate
else
	VENV_DIR = bin
	TOUCH := touch $(TOUCHFILE)
	ACTIVATE := . $(SRC_DIR)/.venv/$(VENV_DIR)/activate
endif



venv: $(SRC_DIR)/.venv/touchfile

$(SRC_DIR)/.venv/touchfile: $(REQ_FILE)
	python -m venv $(SRC_DIR)/.venv
	$(ACTIVATE) && pip install -Ur $(REQ_FILE)  --no-cache-dir
	$(TOUCH)

dep:
	$(ACTIVATE) && pip list


run: venv
	$(ACTIVATE) && cd $(SRC_DIR) && python app/main.py

