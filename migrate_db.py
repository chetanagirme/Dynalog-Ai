import sqlite3

conn = sqlite3.connect('data/users.db')
c = conn.cursor()

migrations = [
    ('chat_history', 'project_id', 'INTEGER'),
    ('chat_history', 'sources', 'TEXT'),
    ('chat_history', 'conversation_id', 'INTEGER'),
    ('conversations', 'project_id', 'INTEGER'),
]

for table, column, coltype in migrations:
    try:
        c.execute(f'ALTER TABLE {table} ADD COLUMN {column} {coltype}')
        print(f"Added {column} to {table}")
    except sqlite3.OperationalError:
        print(f"{column} already exists in {table}")

tables = [
    ('projects', '''
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
    '''),
    ('project_files', '''
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
    '''),
    ('project_activity', '''
        CREATE TABLE IF NOT EXISTS project_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            detail TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    '''),
]

for name, sql in tables:
    try:
        c.execute(sql)
        print(f"{name} table ready")
    except Exception as e:
        print(f"{name} table: {e}")

conn.commit()
conn.close()
print("\nAll migrations complete!")