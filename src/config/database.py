# config do banco
import os
from pathlib import Path

# banco
DATABASE_PATH = Path("data/pescasync.db")
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"


# vai criar um repositorio se nao existir
DATABASE_PATH.parent.mkdir(exist_ok=True)