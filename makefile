BUILD_TOOL?=make
PYTHON?=.venv/bin/python
PYRIGHT?=$(if $(wildcard .venv/bin/pyright),.venv/bin/pyright,pyright)
NODE?=node

.PHONY: install update check

install: 
ifndef LOCATION
	$(error LOCATION is not set. Please set LOCATION. F.e. `make install LOCATION=flake_devel|flake`)
endif
	mkdir -p /usr/bin/larkum/$(LOCATION)/
	cp -f $(LOCATION).service /etc/systemd/system/ 
	systemctl daemon-reload 
	cp -f requirements.txt /usr/bin/larkum/$(LOCATION)/ 
	cp -f server.config /usr/bin/larkum/$(LOCATION)/ 
	cp -f backup.sh /usr/bin/larkum/$(LOCATION)/ 
	cp -f logo.jpg /usr/bin/larkum/$(LOCATION)/ 
	cp -f .env /usr/bin/larkum/$(LOCATION)/ 
	cp -f -r .venv /usr/bin/larkum/$(LOCATION)/ 
	cp -f -r instance /usr/bin/larkum/$(LOCATION)/ 
	cp -f -r resources /usr/bin/larkum/$(LOCATION)/ 
	cp -f -r src /usr/bin/larkum/$(LOCATION)/ 
	cp -f -r templates /usr/bin/larkum/$(LOCATION)/ 
	cd /usr/bin/larkum/$(LOCATION)/ && source .venv/bin/activate && pip install -r requirements.txt 

update:  
ifndef LOCATION
	$(error LOCATION is not set. Please set LOCATION. F.e. `make update LOCATION=flake_devel|flake`)
endif
	cp -f requirements.txt /usr/bin/larkum/$(LOCATION)/ 
	cp -f .env /usr/bin/larkum/$(LOCATION)/ 
	cp -f backup.sh /usr/bin/larkum/$(LOCATION)/ 
	cp -f logo.jpg /usr/bin/larkum/$(LOCATION)/ 
	cp -f -r resources /usr/bin/larkum/$(LOCATION)/ 
	cp -f -r src /usr/bin/larkum/$(LOCATION)/ 
	cp -f -r templates /usr/bin/larkum/$(LOCATION)/ 
	cd /usr/bin/larkum/$(LOCATION)/ && source .venv/bin/activate && pip install -r requirements.txt 
	systemctl restart $(LOCATION).service

check:
	$(PYRIGHT)
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src $(PYTHON) -m unittest discover -s tests
	$(NODE) tests/test_request_errors.js
	$(NODE) tests/test_message_rendering.js
