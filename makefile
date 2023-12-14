install: 
	mkdir -p /usr/bin/larkum/flake/
	cp -f flake.service /etc/systemd/system/ 
	systemctl daemon-reload 
	cp -f requirements.txt /usr/bin/larkum/flake/ 
	cp -f server.config /usr/bin/larkum/flake/ 
	cp -f backup.sh /usr/bin/larkum/flake/ 
	cp -f logo.jpg /usr/bin/larkum/flake/ 
	cp -f .env /usr/bin/larkum/flake/ 
	cp -f -r .venv /usr/bin/larkum/flake/ 
	cp -f -r instance /usr/bin/larkum/flake/ 
	cp -f -r resources /usr/bin/larkum/flake/ 
	cp -f -r src /usr/bin/larkum/flake/ 
	cp -f -r templates /usr/bin/larkum/flake/ 
	cd /usr/bin/larkum/flake/ && source .venv/bin/activate && pip install -r requirements.txt 

update:  
	cp -f requirements.txt /usr/bin/larkum/flake/ 
	cp -f .env /usr/bin/larkum/flake/ 
	cp -f backup.sh /usr/bin/larkum/flake/ 
	cp -f logo.jpg /usr/bin/larkum/flake/ 
	cp -f -r resources /usr/bin/larkum/flake/ 
	cp -f -r src /usr/bin/larkum/flake/ 
	cp -f -r templates /usr/bin/larkum/flake/ 
	cd /usr/bin/larkum/flake/ && source .venv/bin/activate && pip install -r requirements.txt 
