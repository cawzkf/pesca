# implementação concreta de como salvar os dados no db
# roda na raspberry salvando dados dos sensores


from config.database import  DATABASE_PATH
from config.settings import WATER_QUALITY_THRESHOLDS
import sqlite3

class DatabaseManager:
    def __init__(self, db_path: str = str(DATABASE_PATH)):
        self.db_path = db_path
        self.conexao = None
        pass

    def __enter__(self):
        self.conexao = sqlite3.connect(self.db_path)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conexao:
            self.conexao.close()


if __name__ == "__main__":
    # teste
    print('testando DatabaseManager.....')

    with DatabaseManager() as db:
        print('Conectado')
        print(f"arquivo: {db.db_path}")
        print(f"arquivo connect: {db.conexao}")

    print('Conexao fechada')
    print('class DatabaseManager funcionando')