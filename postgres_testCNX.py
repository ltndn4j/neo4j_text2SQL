#Connect to postgresql database and test the connection
import psycopg2
from dotenv import load_dotenv
import os

load_dotenv(override=True)

conn = psycopg2.connect(
    host=os.getenv('postgres_host'),
    database='postgres',
    user=os.getenv('postgres_username'),
    password=os.getenv('postgres_password')
)

#Query employee table and print the 10 first rows
cur = conn.cursor()
cur.execute("SELECT * FROM employees.employee LIMIT 10")
rows = cur.fetchall()
for row in rows:
    print(row)

conn.close()