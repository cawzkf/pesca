# estrutura do banco 
import sqlite3
from datetime import datetime
from config.database import DATABASE_PATH

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

def migration_005():
    return """
    CREATE INDEX idx_sensor_readings_tank_timestamp ON sensor_readings(tank_id, timestamp);
    """

def migration_006():
    return """
    CREATE INDEX idx_alerts_tank_resolved ON alerts(tank_id, resolved);
    """

def migration_007():
    return """
    CREATE INDEX idx_feed_recommendations_tank_time ON feed_recommendations(tank_id, recommended_time);
    """

def migration_008():
    return """
    INSERT INTO tanks (name, capacity, fish_count, ip_address) VALUES 
    ('Tanque Principal', 1000.0, 500, '192.168.1.10');
    """


# tabela para controlar migrations executadas
def create_migrations_table():
    with sqlite3.connect(DATABASE_PATH) as connec:
        cursor = connec.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version TEXT UNIQUE NOT NULL,
                executed_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
        """)
        connec.commit()

def get_executed_migrations():
    # retorna a lista das migrations que ja foram executadas(vão estar na tupla do banco)
    try:
        with sqlite3.connect(DATABASE_PATH) as connec:
            cursor = connec.cursor()
            # comando
            cursor.execute("SELECT version FROM migrations ORDER BY version")
            
            # retorna todas as linhas do resultado
            results = cursor.fetchall()
            return [row[0] for row in results] 
    except sqlite3.OperationalError:
        # se ainda nao existir ai retorna a lista zerada
        return []
    

def run_migrations():
    # executa  as  pendentes
    # garantir que tabela  existe
    create_migrations_table()
    
    # verificar as que  já rodaram
    executed = get_executed_migrations()
    
    # lista de todas as migrations disponíveis
    available_migrations = {
        '001': migration_001,
        '002': migration_002,
        '003': migration_003,
        '004': migration_004,
        '005': migration_005,
        '006': migration_006,
        '007':migration_007,
        '008': migration_008
    }
    
    # 4. Executar só as pendentes
    for version, migration_func in available_migrations.items():
        if version not in executed:
            print(f"Executando migration {version}...")
            execute_migration(migration_func, version)
            print(f"Migration {version} concluída!")
    
    print("Todas as migrations executadas")

def execute_migration(migration_func, version):
    # executa uma migration específica e marca como executada
    try:
        with sqlite3.connect(DATABASE_PATH) as connec:
            cursor = connec.cursor()
            
            # Executa o SQL da migration
            sql = migration_func()
            cursor.execute(sql)
            
            # Marca como executada na tabela migrations
            cursor.execute(
                "INSERT INTO migrations (version) VALUES (?)",
                (version,)
            )
            
            connec.commit()
            
    except Exception as e:
        print(f"Erro ao executar migration {version}: {e}")
        raise


if __name__ == "__main__":
    print("testando sistema de migrations...")
    
    # executar todas as migrations
    run_migrations()
    
    print("\nverificando migrations executadas:")
    executed = get_executed_migrations()
    print(f"Migrations executadas: {executed}")
    
    print("\nSistema de migrations funcionando!")
    