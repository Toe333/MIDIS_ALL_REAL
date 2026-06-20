"""
_test_sql_conn.py
=================
Tests all available Python → SQL Server LocalDB connection methods.
Run with: .venv\Scripts\python CODE\_test_sql_conn.py
"""
import subprocess, sys

LOCALDB_EXE = r"C:\Program Files\Microsoft SQL Server\160\Tools\Binn\SqlLocalDB.exe"
INSTANCE = "MSSQLLocalDB"
DB = "master"


def get_pipe():
    out = subprocess.check_output([LOCALDB_EXE, "info", INSTANCE], text=True)
    for line in out.splitlines():
        if "pipe name" in line.lower():
            return line.split(":", 1)[1].strip()
    raise RuntimeError("Could not find pipe name in sqllocaldb output")


def try_pymssql(pipe):
    print("\n── pymssql ──")
    try:
        import pymssql
        conn = pymssql.connect(server=pipe, database=DB)
        c = conn.cursor()
        c.execute("SELECT @@VERSION")
        ver = c.fetchone()[0]
        print("✅ Connected!", ver[:80])
        conn.close()
        return True
    except Exception as e:
        print(f"❌ {e}")
        return False


def try_pyodbc_driver18(pipe):
    print("\n── pyodbc ODBC Driver 18 ──")
    try:
        import pyodbc
        cs = (
            "DRIVER={ODBC Driver 18 for SQL Server};"
            f"SERVER={pipe};"
            f"DATABASE={DB};"
            "Trusted_Connection=yes;"
            "TrustServerCertificate=yes;"
        )
        conn = pyodbc.connect(cs, timeout=5)
        ver = conn.execute("SELECT @@VERSION").fetchone()[0]
        print("✅ Connected!", ver[:80])
        conn.close()
        return True
    except Exception as e:
        print(f"❌ {e}")
        return False


def try_pyodbc_driver17(pipe):
    print("\n── pyodbc ODBC Driver 17 ──")
    try:
        import pyodbc
        cs = (
            "DRIVER={ODBC Driver 17 for SQL Server};"
            f"SERVER={pipe};"
            f"DATABASE={DB};"
            "Trusted_Connection=yes;"
            "TrustServerCertificate=yes;"
        )
        conn = pyodbc.connect(cs, timeout=5)
        ver = conn.execute("SELECT @@VERSION").fetchone()[0]
        print("✅ Connected!", ver[:80])
        conn.close()
        return True
    except Exception as e:
        print(f"❌ {e}")
        return False


def try_localdb_name():
    """Try connecting using the LocalDB server name rather than named pipe (some drivers resolve it)."""
    print("\n── pyodbc Driver 18 via (localdb)\\MSSQLLocalDB ──")
    try:
        import pyodbc
        cs = (
            "DRIVER={ODBC Driver 18 for SQL Server};"
            r"SERVER=(localdb)\MSSQLLocalDB;"
            f"DATABASE={DB};"
            "Trusted_Connection=yes;"
            "TrustServerCertificate=yes;"
        )
        conn = pyodbc.connect(cs, timeout=5)
        ver = conn.execute("SELECT @@VERSION").fetchone()[0]
        print("✅ Connected!", ver[:80])
        conn.close()
        return True
    except Exception as e:
        print(f"❌ {e}")
        return False


if __name__ == "__main__":
    print("Getting LocalDB pipe name...")
    try:
        pipe = get_pipe()
        print(f"  Pipe: {pipe}")
    except Exception as e:
        print(f"Failed to get pipe: {e}")
        sys.exit(1)

    results = {
        "pymssql": try_pymssql(pipe),
        "pyodbc_18": try_pyodbc_driver18(pipe),
        "pyodbc_17": try_pyodbc_driver17(pipe),
        "localdb_name_18": try_localdb_name(),
    }

    print("\n\n══ Summary ══")
    for k, v in results.items():
        print(f"  {'✅' if v else '❌'} {k}")
    if any(results.values()):
        print("\nAt least one driver works — migration is unblocked!")
    else:
        print("\nAll drivers failed. Install ODBC Driver 17/18 as Administrator.")
        print("  MSI already downloaded to:", r"%TEMP%\msodbcsql17.msi")
        print("  Run in elevated PowerShell:")
        print(r'  msiexec /i "$env:TEMP\msodbcsql17.msi" /quiet /norestart IACCEPTMSODBCSQLLICENSETERMS=YES')
