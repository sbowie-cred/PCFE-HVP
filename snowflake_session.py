"""
Snowflake session management - initialized once at import time.
"""

from snowflake.snowpark.context import get_active_session
from snowflake.snowpark import Session

CONNECTION_PARAMS = {
    "account": "YV35611.east-us-2.azure",
    "warehouse": "FRA",
    "authenticator": "externalbrowser"
}

_session: Session | None = None

def get_session() -> Session:
    global _session
    if _session is not None:
        return _session
    try:
        _session = get_active_session()
    except:
        _session = Session.builder.configs(CONNECTION_PARAMS).create()
    return _session

session: Session = get_session()
