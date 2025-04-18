# System and Database Monitoring Tool 🚀

A Python-based monitoring solution that tracks website uptime, SSL certificates, PostgreSQL databases, and server health metrics. Sends real-time alerts via Google Chat when issues are detected.


## Features ✨

- **Website Monitoring**: Checks HTTP status and uptime for multiple URLs.
- **SSL Certificate Expiry**: Alerts when certificates expire in <15 days.
- **PostgreSQL Monitoring**: Tracks active connections, queries, and DB status.
- **Server Health**: Monitors CPU, memory, and disk usage (alerts at >85%).
- **Alerting**: Real-time notifications via Google Chat webhooks.
- **Time-Zone Aware**: All timestamps in IST (Asia/Kolkata).

## Prerequisites 📋

- Python 3.8+
- PostgreSQL 12+
- Linux/Windows server

## Installation ⚙️

1. Clone the repository:

   git clone 
   cd system-db-monitor
Install dependencies:

pip install -r requirements.txt
Set up configuration:

cp config.json.example config.json
Edit config.json with your details.

Configuration 🛠️

{
  "WEBHOOK_URL": "your_google_chat_webhook",
  "DB_HOST_WEBSITE_STATUS": "localhost",
  "DB_NAME_WEBSITE_STATUS": "monitoring_db",
  "URL_1": "https://example.com,https://anothersite.com"
}
Usage 🚦
Run the main monitor:


python monitor.py
Run the alert analyzer:

python alert_analyzer.py
For production, set up a cron job:


*/5 * * * * /usr/bin/python3 /path/to/monitor.py >> /var/log/monitor.log 2>&1

Database Schema 📊
SSL Certificate Status:

CREATE TABLE ssl_certificate_status (
    id SERIAL PRIMARY KEY,
    url VARCHAR(255),
    days_left INTEGER,
    http_status INTEGER,
    last_checked TIMESTAMP
);
Server Health:

CREATE TABLE server_health (
    id SERIAL PRIMARY KEY,
    project_name VARCHAR(100),
    server_name VARCHAR(100),
    cpu_usage_percent DECIMAL(5,2),
    memory_usage_percent DECIMAL(5,2),
    disk_usage_percent DECIMAL(5,2),
    checked_at TIMESTAMP
);

Sample Alerts 🔔
Google Chat Alert (Replace with actual alert screenshot)

Contributing 🤝
Pull requests welcome! For major changes, please open an issue first.
