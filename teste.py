# db_viewer.py — Visualizador de Tabelas (SQLite) p/ Streamlit (7")
# ====================================================================================
# Objetivo:
# - Navegar por TABELAS/VIEWS do SQLite (somente leitura)
# - Ver dados com paginação, busca global, ordenação, exportar CSV
# - Ver schema (colunas/tipos), número de linhas, índices e DDL
# - Opção de executar CONSULTAS SELECT (read-only) com verificação simples
#
# Integração:
# - Usa config.database.DATABASE_PATH quando disponível (seu projeto atual)
# - Se não houver, permite apontar um arquivo .db manualmente
#
# CLAUDE (estilização):
# - Estilize a bottom bar, títulos, cards e botões.
# - Marquei pontos "CLAUDE:" para facilitar.
# ====================================================================================

from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

# ====================================================================================
# Configuração da página
# ====================================================================================
st.set_page_config(
    page_title="Visualizador do Banco",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ====================================================================================
# Local do banco
# ====================================================================================
def _discover_db_path() -> Optional[str]:
    # Tenta usar o caminho do projeto (se existir)
    try:
        from config.database import DATABASE_PATH
        if os.path.exists(DATABASE_PATH):
            return DATABASE_PATH
    except Exception:
        pass
    return None

DEFAULT_DB_PATH = _discover_db_path()

st.sidebar.header("Banco de dados")
db_path = DEFAULT_DB_PATH

if not db_path or not os.path.exists(db_path):
    st.sidebar.warning("Não encontrei config.database.DATABASE_PATH.")
    db_path = st.sidebar.text_input("Caminho do .db", value="", placeholder="/caminho/para/seu.db")
    up = st.sidebar.file_uploader("Ou envie um .db", type=["db", "sqlite", "sqlite3"])
    if up is not None:
        # Salva em /tmp e usa no runtime
        tmp_path = os.path.join("/tmp", up.name)
        with open(tmp_path, "wb") as f:
            f.write(up.read())
        db_path = tmp_path

if not db_path:
    st.stop()
if not os.path.exists(db_path):
    st.error(f"Arquivo não encontrado: {db_path}")
    st.stop()

st.sidebar.caption(f"Arquivo do banco: `{db_path}`")

# ====================================================================================
# Conexão e helpers
# ====================================================================================
def connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    con.row_factory = sqlite3.Row
    # PRAGMAs leves — leitura rápida
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA temp_store=MEMORY;")
    con.execute("PRAGMA mmap_size=268435456;")  # 256MB
    con.execute("PRAGMA foreign_keys=ON;")
    return con

# Cacheia listas e metadados por poucos segundos (banco pode atualizar)
@st.cache_data(ttl=5)
def list_tables(path: str) -> pd.DataFrame:
    with connect(path) as con:
        q = """
        SELECT name, type, sql
          FROM sqlite_master
         WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'
         ORDER BY name;
        """
        rows = con.execute(q).fetchall()
    return pd.DataFrame([dict(r) for r in rows])

@st.cache_data(ttl=10)
def get_table_info(path: str, table: str) -> Tuple[pd.DataFrame, pd.DataFrame, int, str]:
    """Retorna (schema_cols, indexes, rowcount, ddl)"""
    with connect(path) as con:
        cols = con.execute(f"PRAGMA table_info({table})").fetchall()
        idxs = con.execute(f"PRAGMA index_list({table})").fetchall()
        # contagem total (cuidado: em tabelas gigantes pode custar)
        total = con.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
        ddl = con.execute(
            "SELECT sql FROM sqlite_master WHERE type IN ('table','view') AND name = ?",
            (table,)
        ).fetchone()
    df_cols = pd.DataFrame([dict(r) for r in cols]) if cols else pd.DataFrame(columns=["cid","name","type","notnull","dflt_value","pk"])
    df_idxs = pd.DataFrame([dict(r) for r in idxs]) if idxs else pd.DataFrame(columns=["seq","name","unique","origin","partial"])
    ddl_sql = ddl["sql"] if ddl and ddl["sql"] else ""
    return df_cols, df_idxs, int(total), ddl_sql

def _is_text_type(sqlite_type: str) -> bool:
    if not sqlite_type: return False
    t = sqlite_type.upper()
    return ("CHAR" in t) or ("CLOB" in t) or ("TEXT" in t)

def _is_numeric_type(sqlite_type: str) -> bool:
    if not sqlite_type: return False
    t = sqlite_type.upper()
    return ("INT" in t) or ("REAL" in t) or ("FLOA" in t) or ("DOUB" in t) or ("NUM" in t) or ("DEC" in t)

@st.cache_data(ttl=3, show_spinner=False)
def fetch_rows(
    path: str,
    table: str,
    limit: int,
    offset: int,
    order_by: Optional[str],
    desc: bool,
    global_search: Optional[str],
) -> pd.DataFrame:
    # Monta SELECT com busca em colunas de texto e ORDER BY
    cols_df, _, _, _ = get_table_info(path, table)
    col_names = [c["name"] if isinstance(c, dict) else c for c in cols_df.to_dict("records")]
    col_types = {r["name"]: (r["type"] or "") for r in cols_df.to_dict("records")}
    text_cols = [c for c in col_names if _is_text_type(col_types.get(c,""))]

    where = ""
    params: List = []
    if global_search and text_cols:
        like = f"%{global_search}%"
        ors = " OR ".join([f"{c} LIKE ?" for c in text_cols])
        where = f"WHERE ({ors})"
        params = [like] * len(text_cols)

    order_clause = ""
    if order_by and order_by in col_names:
        order_clause = f"ORDER BY {order_by} {'DESC' if desc else 'ASC'}"

    sql = f"SELECT * FROM {table} {where} {order_clause} LIMIT ? OFFSET ?"
    params.extend([int(limit), int(offset)])

    with connect(path) as con:
        df = pd.read_sql_query(sql, con, params=params)
    return df

# ====================================================================================
# Barra inferior simples (CLAUDE pode estilizar como bottom-nav)
# ====================================================================================
def bottom_bar():
    # CLAUDE: transformar em bottom bar fixa; aqui é só um placeholder
    st.write("---")
    st.caption("Visualizador do banco (somente leitura)")

# ====================================================================================
# UI — lateral
# ====================================================================================
st.title("Visualizador de Tabelas (SQLite)")

tables_df = list_tables(db_path)
if tables_df.empty:
    st.warning("Não há tabelas nem views (ou banco vazio).")
    bottom_bar()
    st.stop()

t_names = tables_df["name"].tolist()
t_map_type = {r["name"]: r["type"] for r in tables_df.to_dict("records")}
ddl_map = {r["name"]: r.get("sql") or "" for r in tables_df.to_dict("records")}

# Seleção de tabela
table = st.sidebar.selectbox("Tabela / View", t_names, index=0, format_func=lambda n: f"{n} ({t_map_type.get(n)})")

# Controles de dados
st.sidebar.subheader("Listagem")
page_size = st.sidebar.selectbox("Linhas por página", [25, 50, 100, 200, 500], index=1)
# Estado da página por tabela
page_key = f"page_{table}"
if page_key not in st.session_state:
    st.session_state[page_key] = 0

# Busca global (LIKE em colunas de texto)
global_search = st.sidebar.text_input("Busca (em colunas TEXT)", value="", placeholder="digite para filtrar...")

# Ordenação
cols_df, idxs_df, total_count, ddl_sql = get_table_info(db_path, table)
order_by = st.sidebar.selectbox(
    "Ordenar por", ["(sem ordenação)"] + cols_df["name"].tolist(), index=0
)
order_by = None if order_by == "(sem ordenação)" else order_by
desc = st.sidebar.checkbox("Descendente", value=False)

# Paginação
def _reset_page():
    st.session_state[page_key] = 0

if st.sidebar.button("Aplicar filtros/ordenação"):
    _reset_page()

# Botões página
c_pag1, c_pag2, c_pag3 = st.sidebar.columns([1,1,1])
if c_pag1.button("⟨ Anterior"):
    st.session_state[page_key] = max(0, st.session_state[page_key]-1)
if c_pag3.button("Próxima ⟩"):
    st.session_state[page_key] += 1
page_idx = st.session_state[page_key]
offset = page_idx * page_size

# ====================================================================================
# Painel principal — Info da tabela
# ====================================================================================
st.subheader(f"Tabela: {table}  •  Linhas: {total_count:,}")

c_meta1, c_meta2 = st.columns([2,1])

with c_meta1:
    st.markdown("**Schema (PRAGMA table_info)**")
    if cols_df.empty:
        st.info("Sem colunas (ou tabela não encontrada).")
    else:
        # Renomeia para ficar mais amigável
        cols_show = cols_df.rename(columns={
            "cid":"ordem", "name":"coluna", "type":"tipo",
            "notnull":"notnull", "dflt_value":"default", "pk":"chave_primária"
        })
        st.dataframe(cols_show, use_container_width=True, hide_index=True)

with c_meta2:
    st.markdown("**Índices (PRAGMA index_list)**")
    if idxs_df.empty:
        st.caption("Nenhum índice declarado.")
    else:
        idxs_show = idxs_df.rename(columns={"seq":"seq","name":"nome","unique":"único","origin":"origem","partial":"parcial"})
        st.dataframe(idxs_show, use_container_width=True, hide_index=True)

with st.expander("DDL (sqlite_master.sql)"):
    # DDL explícito da tabela
    st.code(ddl_sql or ddl_map.get(table, ""), language="sql")

# ====================================================================================
# Dados — consulta e exibição
# ====================================================================================
st.markdown("### Dados")

df = fetch_rows(
    db_path, table,
    limit=page_size,
    offset=offset,
    order_by=order_by,
    desc=desc,
    global_search=global_search.strip() or None,
)

# Navegação com informação da janela
shown_from = offset + 1 if total_count else 0
shown_to = min(offset + page_size, total_count)
st.caption(f"Mostrando {shown_from}–{shown_to} de {total_count} linhas")

# Tabela de dados
st.dataframe(df, use_container_width=True, hide_index=True)

# Exportar CSV (da janela atual)
csv_bytes = df.to_csv(index=False).encode("utf-8")
st.download_button(
    label="Exportar CSV (janela atual)",
    data=csv_bytes,
    file_name=f"{table}_p{page_idx}_n{page_size}.csv",
    mime="text/csv",
)

# Mostrar SQL gerado (para transparência)
with st.expander("Ver SQL gerado (janela atual)"):
    ex_cols = cols_df["name"].tolist()
    text_cols = [c for c,t in zip(cols_df["name"], cols_df["type"]) if _is_text_type(t or "")]
    where = ""
    if global_search and text_cols:
        ors = " OR ".join([f"{c} LIKE '%{global_search}%'" for c in text_cols])
        where = f"WHERE ({ors})"
    ob = f"ORDER BY {order_by} {'DESC' if desc else 'ASC'}" if order_by else ""
    st.code(f"SELECT * FROM {table} {where} {ob} LIMIT {page_size} OFFSET {offset};", language="sql")

# ====================================================================================
# Console de consulta (somente SELECT)
# ====================================================================================
st.markdown("### Consulta (somente SELECT)")

with st.expander("Abrir console SQL (read-only)"):
    user_sql = st.text_area("Escreva um SELECT seguro (sem ; no final)", height=160,
                            placeholder=f"Ex.: SELECT * FROM {table} WHERE id < 100 ORDER BY id DESC")
    c1, c2 = st.columns([1,4])
    with c1:
        run = st.button("Executar consulta")
    if run:
        q = (user_sql or "").strip()
        safe = True
        # regras simples de segurança: apenas SELECT, sem ;, sem PRAGMA/ATTACH/INSERT/UPDATE/DELETE/ALTER/DROP
        if not q.lower().startswith("select"):
            safe = False
        if ";" in q:
            safe = False
        banned = ("pragma", "attach", "insert", "update", "delete", "alter", "drop", "create", "vacuum", "reindex")
        if any(b in q.lower() for b in banned):
            safe = False

        if not safe:
            st.error("Consulta bloqueada. Somente SELECT sem ponto e vírgula e sem comandos de escrita.")
        else:
            try:
                with connect(db_path) as con:
                    dfq = pd.read_sql_query(q, con)
                st.success(f"{len(dfq)} linha(s) retornadas")
                st.dataframe(dfq, use_container_width=True, hide_index=True)
                st.download_button(
                    label="Exportar resultado em CSV",
                    data=dfq.to_csv(index=False).encode("utf-8"),
                    file_name="resultado_query.csv",
                    mime="text/csv",
                )
            except Exception as e:
                st.error(f"Erro ao executar SELECT: {e}")

# ====================================================================================
# Rodapé
# ====================================================================================
bottom_bar()
