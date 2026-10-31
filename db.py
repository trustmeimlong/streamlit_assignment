import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


@st.cache_resource(show_spinner=False)
def get_engine():
    cfg = st.secrets["mysql"]
    url = URL.create(
        "mysql+mysqlconnector",
        username=cfg["username"],
        password=cfg["password"],
        host=cfg["host"],
        port=int(cfg["port"]),
        database=cfg["database"],
    )
    return create_engine(url, pool_pre_ping=True, pool_recycle=1800)


@st.cache_data(ttl=600, show_spinner="Đang truy vấn MySQL...")
def run_query(sql, params=None):
    with get_engine().connect() as con:
        return pd.read_sql(text(sql), con, params=params)
