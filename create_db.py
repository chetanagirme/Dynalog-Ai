from werkzeug.security import generate_password_hash
import sqlite3
import os

def create_database():
    os.makedirs('data', exist_ok=True)
    os.makedirs('uploads', exist_ok=True)
    os.makedirs('projects', exist_ok=True)

    conn = sqlite3.connect('data/users.db')
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT DEFAULT 'staff'
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            created_by INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            file_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active'
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS project_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            original_name TEXT NOT NULL,
            file_type TEXT,
            file_size INTEGER DEFAULT 0,
            indexed INTEGER DEFAULT 0,
            uploaded_by INTEGER NOT NULL,
            uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS project_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            detail TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            project_id INTEGER,
            title TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            conversation_id INTEGER,
            project_id INTEGER,
            message TEXT NOT NULL,
            response TEXT NOT NULL,
            sources TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    admin_password = generate_password_hash('Admin@1234')
    try:
        c.execute('''
            INSERT INTO users (username, password, full_name, role)
            VALUES (?, ?, ?, ?)
        ''', ('admin', admin_password, 'Administrator', 'admin'))
        print("Admin user created!")
    except sqlite3.IntegrityError:
        print("Admin user already exists")

    conn.commit()
    conn.close()
    print("Database upgraded successfully!")
    print("New tables: projects, project_files, project_activity")

if __name__ == '__main__':
    create_database()