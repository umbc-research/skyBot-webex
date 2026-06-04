[proutyr1@obs-web ~]$ python -m venv skyBot-webex-venv
[proutyr1@obs-web ~]$ source skyBot-webex-venv/bin/activate
(skyBot-webex-venv) [proutyr1@obs-web ~]$ pip install -r skyBot-webex/requirements.txt 


/usr/lib/systemd/system/skybot-webex.service
```
[Unit]
Description=Discord Bot Service (Webex)
After=network.target

[Service]
# User and group under which the service will run
User=proutyr1
Group=general

# Working directory of the bot
WorkingDirectory=/home/proutyr1/skyBot-webex/

# Command to activate virtual environment and run the bot
ExecStart=/bin/bash -c 'source /home/proutyr1/skyBot-webex-venv && python webex_main.py'

# Restart the bot if it crashes
Restart=always
RestartSec=3

# Environment variables (if needed)
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Replaced .env file from Ben's : NEED TO GET NEW TOKEN FROM CHRIS M.
