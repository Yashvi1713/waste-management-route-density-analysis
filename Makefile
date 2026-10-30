.PHONY: setup data pipeline test qa app all deploy destroy

PYTHON := .venv/bin/python

setup:
	python3.11 -m venv .venv
	$(PYTHON) -m pip install -r requirements.txt

data:
	$(PYTHON) generate_data.py --days 90 --seed 42

pipeline:
	$(PYTHON) run_pipeline.py

test:
	$(PYTHON) -m pytest -q

qa:
	$(PYTHON) qa/run_qa.py

app:
	ANALYTICS_BACKEND=local .venv/bin/streamlit run app.py

all: data pipeline test qa

deploy:
	bash scripts/deploy_aws.sh

destroy:
	bash scripts/destroy_aws.sh

