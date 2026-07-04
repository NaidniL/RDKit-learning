PYTHON := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: setup check notebook app test clean

setup:
	python3.10 -m venv --clear .venv
	$(PYTHON) -m pip install --upgrade pip setuptools wheel
	$(PIP) install -r requirements-lock.txt
	$(PYTHON) scripts/check_environment.py

check:
	$(PYTHON) scripts/check_environment.py

notebook:
	$(PYTHON) -m jupyter lab

app:
	$(PYTHON) -m streamlit run app.py

test:
	$(PYTHON) -m pytest -q

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
