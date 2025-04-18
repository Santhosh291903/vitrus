import psycopg2
import requests
from datetime import datetime, timedelta
import pytz

# Database configuration
DB_CONFIG = {
    "host": "localhost",
    "dbname": "<dbname>",
    "user": "<user>",
    "password": "simplepass"
}

# Google Chat webhook URL
WEBHOOK_URL = "<WEBHOOK_URL>"

def log(message):
    """Helper function for consistent logging format"""
    ist = pytz.timezone('Asia/Kolkata')
    timestamp = datetime.now(ist).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def send_google_chat_message(message):
    try:
        log(f"Sending alert to Google Chat: {message}")
        response = requests.post(WEBHOOK_URL, json={"text": message})
        if response.status_code != 200:
            log(f"Failed to send message: {response.status_code}, {response.text}")
        else:
            log("Message sent successfully")
    except Exception as e:
        log(f"Error sending Google Chat message: {e}")

def check_db_monitoring(cursor):
    log("Checking database monitoring status for entries updated in last 3 minutes...")
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    three_min_ago = now - timedelta(minutes=3)
    
    # Convert to UTC for database comparison
    three_min_ago_utc = three_min_ago.astimezone(pytz.utc)
    
    # Get only the most recent entry for each database that was updated in last 3 minutes
    cursor.execute("""
        WITH latest_entries AS (
            SELECT 
                project_name, 
                db_name, 
                db_status, 
                last_checked,
                ROW_NUMBER() OVER (PARTITION BY db_name ORDER BY last_checked DESC) as rn
            FROM db_monitoring
            WHERE last_checked >= %s
        )
        SELECT project_name, db_name, db_status, last_checked
        FROM latest_entries
        WHERE rn = 1;
    """, (three_min_ago_utc,))
    
    results = cursor.fetchall()
    
    if not results:
        log("No database entries updated in the last 3 minutes")
        return

    for result in results:
        project_name, db_name, db_status, last_checked = result
        # Convert last_checked to IST for display
        last_checked_ist = last_checked.astimezone(ist)
        
        log(f"Found recently updated DB: {db_name} (Project: {project_name}) - "
            f"Status: {db_status}, Last checked: {last_checked_ist.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        if db_status != 'active':
            alert = f"🚨 *Database {db_name} (Project: {project_name}) status is INACTIVE!* Please check immediately."
            send_google_chat_message(alert)
        else:
            log(f"DB {db_name} status OK")

def check_server_health(cursor):
    log("Checking server health metrics...")
    cursor.execute("""
        SELECT project_name, server_name, cpu_usage_percent, memory_usage_percent, disk_usage_percent 
        FROM server_health
        WHERE checked_at >= NOW() - INTERVAL '3 minutes';
    """)
    results = cursor.fetchall()
    
    if not results:
        log("No server health data updated in last 3 minutes")
        return

    for result in results:
        project_name, server_name, cpu, memory, disk = result
        log(f"Server: {server_name} (Project: {project_name}) - CPU: {cpu}%, Memory: {memory}%, Disk: {disk}%")

        if cpu > 85:
            alert = f"🔥 *High CPU usage on {server_name} (Project: {project_name}):* {cpu}%"
            send_google_chat_message(alert)
        if memory > 85:
            alert = f"💾 *High Memory usage on {server_name} (Project: {project_name}):* {memory}%"
            send_google_chat_message(alert)
        if disk > 85:
            alert = f"📦 *High Disk usage on {server_name} (Project: {project_name}):* {disk}%"
            send_google_chat_message(alert)

def check_ssl_certificates(cursor):
    log("Checking SSL certificates updated in last 3 minutes...")
    cursor.execute("""
        SELECT id, url, days_left, http_status 
        FROM ssl_certificate_status
        WHERE checked_at >= NOW() - INTERVAL '3 minutes';
    """)
    results = cursor.fetchall()
    
    if not results:
        log("No SSL certificate data updated in last 3 minutes")
        return

    for result in results:
        id, url, days_left, http_status = result
        log(f"SSL Cert ID {id} - URL: {url}, Days left: {days_left}, HTTP Status: {http_status}")

        if days_left < 15:
            alert = f"🔐 *SSL certificate for {url} expires in {days_left} days.* Please renew."
            send_google_chat_message(alert)
        if http_status != 200:
            alert = f"❌ *App at {url} is down.* HTTP Status: {http_status}. Please check the server."
            send_google_chat_message(alert)

def main():
    log("Starting monitoring script...")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        log("Successfully connected to database")

        # Monitor DB status (only entries updated in last 3 minutes)
        check_db_monitoring(cursor)

        # Check server health metrics (only entries updated in last 3 minutes)
        check_server_health(cursor)

        # Check SSL certificates (only entries updated in last 3 minutes)
        check_ssl_certificates(cursor)

        cursor.close()
        conn.close()
        log("Database connection closed")
    except psycopg2.Error as e:
        error_msg = f"Database connection error: {e}"
        log(error_msg)
        send_google_chat_message(f"🚨 *Database connection failed:* {e}")
    except Exception as e:
        error_msg = f"Unexpected error: {e}"
        log(error_msg)
        send_google_chat_message(f"🚨 *Script error:* {e}")
    
    log("Monitoring script completed")

if __name__ == "__main__":
    main()
