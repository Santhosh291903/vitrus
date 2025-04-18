import json
import requests
import os
import ssl
import socket
from datetime import datetime
import psycopg2
from psycopg2 import OperationalError
import psutil
import shutil
import pytz  # Added for timezone handling

# Load configuration from config.json
try:
    with open("config.json", "r") as f:
        config = json.load(f)
except FileNotFoundError:
    print("❌ config.json file not found!")
    exit(1)

# Required configuration keys
required_keys = [
    "WEBHOOK_URL", "DB_HOST_WEBSITE_STATUS", "DB_NAME_WEBSITE_STATUS", "DB_USER_WEBSITE_STATUS",
    "DB_PASSWORD_WEBSITE_STATUS", "DB_HOST_DB_MONITORING", "DB_NAME_DB_MONITORING", 
    "DB_USER_DB_MONITORING", "DB_PASSWORD_DB_MONITORING", "URL_1"
]

missing = [key for key in required_keys if key not in config]
if missing:
    print(f"🚨 Missing required configuration keys: {', '.join(missing)}")
    exit(1)

# Website URLs
URLS = config["URL_1"].split(',')

# Status file
STATUS_FILE = "website_status.json"

# Google Chat Webhook URL
WEBHOOK_URL = config["WEBHOOK_URL"]

# Database connection details for Website Status DB
DB_CONFIG_WEBSITE_STATUS = {
    "host": config["DB_HOST_WEBSITE_STATUS"],
    "database": config["DB_NAME_WEBSITE_STATUS"],
    "user": config["DB_USER_WEBSITE_STATUS"],
    "password": config["DB_PASSWORD_WEBSITE_STATUS"]
}

# Database connection details for DB Monitoring DB
DB_CONFIG_DB_MONITORING = {
    "host": config["DB_HOST_DB_MONITORING"],
    "database": config["DB_NAME_DB_MONITORING"],
    "user": config["DB_USER_DB_MONITORING"],
    "password": config["DB_PASSWORD_DB_MONITORING"]
}

project_name = config['PROJECT_NAME'] 
server_name = config['server_name']
DB_NAME = config['DB_NAME']

# Set up timezone for India
IST = pytz.timezone('Asia/Kolkata')

# Load or initialize website status
if os.path.exists(STATUS_FILE):
    try:
        with open(STATUS_FILE, "r") as f:
            website_status = json.load(f)
    except json.JSONDecodeError:
        website_status = {url: {"down_count": 0, "time_ranges": []} for url in URLS}
else:
    website_status = {url: {"down_count": 0, "time_ranges": []} for url in URLS}

def get_indian_time():
    """Returns current time in Indian timezone"""
    return datetime.now(IST)

def send_google_chat_message(message):
    if not WEBHOOK_URL:
        print("⚠ GOOGLE_CHAT_WEBHOOK_URL is missing. Skipping alert.")
        return
    
    payload = {"text": message}
    try:
        response = requests.post(WEBHOOK_URL, json=payload, headers={"Content-Type": "application/json"})
        if response.status_code != 200:
            print(f"⚠ Failed to send Google Chat alert (Status: {response.status_code})")
    except Exception as e:
        print(f"⚠ Exception while sending Google Chat alert: {e}")

def check_website(url):
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        print(f"[✔] {url} is UP (Status: {response.status_code})")
        http_status = 200
    except requests.exceptions.RequestException as e:
        print(f"[❌] {url} is DOWN! ({e})")
        message = f"⚠ ALERT: {url} is DOWN! ({e})"
        send_google_chat_message(message)
        http_status = 500

        if url in website_status:
            website_status[url]["down_count"] += 1
            website_status[url]["time_ranges"].append(get_indian_time().strftime("%Y-%m-%d %H:%M:%S"))
        else:
            website_status[url] = {"down_count": 1, "time_ranges": [get_indian_time().strftime("%Y-%m-%d %H:%M:%S")]}
    
    check_ssl_expiry(url, http_status)

def check_ssl_expiry(url, http_status):
    days_left = -1  # Default value if SSL check fails
    
    try:
        # Only try to check SSL if the website is up (http_status = 200)
        if http_status == 200:
            hostname = url.replace("https://", "").split("/")[0]
            context = ssl.create_default_context()
            with socket.create_connection((hostname, 443), timeout=5) as sock:
                with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()

            if not cert:
                print(f"[❌] {url} SSL Certificate retrieval FAILED!")
                send_google_chat_message(f"⚠ ALERT: Could not retrieve SSL certificate for {url}.")
                return

            expiry_date = datetime.strptime(cert['notAfter'], "%b %d %H:%M:%S %Y GMT")
            days_left = (expiry_date - datetime.utcnow()).days

            if days_left < 15:
                print(f"[❌] {url} SSL Certificate is EXPIRING SOON (Expires in {days_left} days)")
                send_google_chat_message(f"⚠ ALERT: {url} SSL Certificate expires in {days_left} days!")
            else:
                print(f"[✔] {url} SSL Certificate is valid (Expires in {days_left} days")
        else:
            print(f"[⚠] Skipping SSL check for {url} because website is down")
            
    except Exception as e:
        print(f"[❌] {url} SSL Certificate Check FAILED ({e})")
        days_left = -1
    
    insert_ssl_status(url, days_left, http_status)

def insert_ssl_status(url, days_left, http_status):
    try:
        connection = psycopg2.connect(**DB_CONFIG_WEBSITE_STATUS)
        cursor = connection.cursor()
        
        # If the website is down (http_status = 500), set days_left to -1
        if http_status == 500:
            days_left = -1
        
        cursor.execute("""
            INSERT INTO ssl_certificate_status (url, days_left, http_status, last_checked)
            VALUES (%s, %s, %s, %s)
        """, (url, days_left, http_status, get_indian_time()))

        connection.commit()
        print(f"✅ SSL status inserted for {url}")
    except Exception as e:
        print(f"❌ Error inserting SSL status: {e}")
    finally:
        if connection:
            cursor.close()
            connection.close()

def check_postgres_connection():
    try:
        conn = psycopg2.connect(**DB_CONFIG_DB_MONITORING)
        print("✅ PostgreSQL is up and running")
        conn.close()
    except OperationalError as e:
        print("❌ Error connecting to PostgreSQL:", e)

def get_postgres_metrics():
    connection = None
    try:
        connection = psycopg2.connect(**DB_CONFIG_DB_MONITORING)
        cursor = connection.cursor()

        cursor.execute("SELECT COUNT(*) FROM pg_stat_activity;")
        connections = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM pg_stat_activity WHERE state = 'active';")
        active_connections = cursor.fetchone()[0]

        cursor.execute("""
            SELECT SUM(xact_commit + xact_rollback)
            FROM pg_stat_database
            WHERE datname = current_database();
        """)
        total_queries = cursor.fetchone()[0]

        print("📊 Total Connections:", connections)
        print("📊 Active Connections:", active_connections)
        print("📊 Total Queries (commits + rollbacks):", total_queries)

        insert_db_metrics('active', connections, active_connections, total_queries)

    except OperationalError as e:
        print("❌ Error:", e)
        insert_db_metrics('inactive', 0, 0, 0)

    finally:
        if connection:
            cursor.close()
            connection.close()

def insert_db_metrics(db_status, connections, active_connections, total_queries):
    connection = None
    try:
        connection = psycopg2.connect(**DB_CONFIG_WEBSITE_STATUS)
        cursor = connection.cursor()

        insert_query = """
            INSERT INTO db_monitoring (project_name, db_name, db_status, total_connections, active_connections, total_queries, last_checked)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(insert_query, (
            project_name, server_name, db_status,
            connections, active_connections,
            total_queries, get_indian_time()
        ))

        connection.commit()
        print(f"✅ DB monitoring metrics inserted with status '{db_status}'.")
    except Exception as e:
        print(f"❌ Error inserting DB monitoring metrics: {e}")
    finally:
        if connection:
            cursor.close()
            connection.close()

def check_threshold(label, percent):
    if percent >= 85:
        print(f"🚨 ALERT: {label} usage is high: {percent}%")
    else:
        print(f"✅ {label} usage is normal: {percent}%")

def monitor_system():
    cpu_usage = psutil.cpu_percent(interval=1)
    check_threshold("CPU", cpu_usage)

    mem = psutil.virtual_memory()
    check_threshold("Memory", mem.percent)

    disk = shutil.disk_usage("/")
    disk_percent = disk.used / disk.total * 100
    check_threshold("Disk", round(disk_percent, 2))

    insert_system_health(cpu_usage, mem.percent, round(disk_percent, 2))

def insert_system_health(cpu_usage, memory_usage, disk_usage):
    try:
        connection = psycopg2.connect(**DB_CONFIG_WEBSITE_STATUS)
        cursor = connection.cursor()

        insert_query = """
            INSERT INTO server_health (project_name, server_name, cpu_usage_percent, memory_usage_percent, disk_usage_percent, checked_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        cursor.execute(insert_query, (project_name, server_name, cpu_usage, memory_usage, disk_usage, get_indian_time()))

        connection.commit()
        print("✅ System health metrics inserted successfully.")
    except Exception as e:
        print(f"❌ Error inserting system health metrics: {e}")
    finally:
        if connection:
            cursor.close()
            connection.close()

def main():
    check_postgres_connection()
    monitor_system()
    get_postgres_metrics()    
    for url in URLS:
        check_website(url)
    
    with open(STATUS_FILE, "w") as f:
        json.dump(website_status, f, indent=4)

if __name__ == "__main__":
    main()
