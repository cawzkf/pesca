# estrutura do banco 


def migration_001():
    return """
    CREATE TABLE tanks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        capacity REAL NOT NULL,
        fish_count INTEGER DEFAULT 0,
        ip_address TEXT,
        active BOOLEAN DEFAULT 1,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """

def migration_002():
    return """
    CREATE TABLE sensor_readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tank_id INTEGER NOT NULL,
        timestamp DATETIME NOT NULL,
        temperature REAL NOT NULL,
        ph REAL NOT NULL,
        oxygen REAL NOT NULL,
        turbidity REAL NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tank_id) REFERENCES tanks(id)
    );
    """

def migration_003():
    return """
    CREATE TABLE alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tank_id INTEGER NOT NULL,
        alert_type TEXT NOT NULL,
        severity TEXT NOT NULL,
        description TEXT NOT NULL,
        value REAL,
        threshold REAL,
        resolved BOOLEAN DEFAULT 0,
        resolved_at DATETIME,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tank_id) REFERENCES tanks(id)
    );
    """


def migration_004():
    return """
    CREATE TABLE feed_recommendations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tank_id INTEGER NOT NULL,
        recommended_amount REAL NOT NULL,
        recommended_time DATETIME NOT NULL,
        fish_weight_estimate REAL,
        water_conditions_score REAL,
        algorithm_used TEXT,
        executed BOOLEAN DEFAULT 0,
        executed_at DATETIME,
        auto_marked BOOLEAN DEFAULT 0,
        notes TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (tank_id) REFERENCES tanks(id)
    );
    """
