.PHONY: mig makemigrations migrate seed run test check

PYTHON ?= python

mig:
	$(PYTHON) manage.py makemigrations
	$(PYTHON) manage.py migrate

makemigrations:
	$(PYTHON) manage.py makemigrations

migrate:
	$(PYTHON) manage.py migrate

seed:
	$(PYTHON) manage.py seed_market

run:
	$(PYTHON) manage.py runserver

test:
	DJANGO_SETTINGS_MODULE=root.test_settings $(PYTHON) manage.py test

check:
	$(PYTHON) manage.py check
