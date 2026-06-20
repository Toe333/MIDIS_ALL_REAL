"""Quick post-migration sanity check."""
import pyodbc

CONN = (
    "DRIVER={ODBC Driver 17 for SQL Server};"
    r"SERVER=(localdb)\MSSQLLocalDB;"
    "DATABASE=MIDIS_ALL_REAL;"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)

conn = pyodbc.connect(CONN)
c = conn.cursor()

c.execute("""
    SELECT t.TABLE_NAME,
           SUM(p.row_count) AS rows
    FROM   sys.dm_db_partition_stats p
    JOIN   INFORMATION_SCHEMA.TABLES t
           ON t.TABLE_NAME = OBJECT_NAME(p.object_id)
    WHERE  p.index_id < 2
    GROUP  BY t.TABLE_NAME
    ORDER  BY t.TABLE_NAME
""")
print("\n── Table row counts ──")
for row in c.fetchall():
    print(f"  {row[0]:30s}  {row[1]:>10,} rows")

# Spot-check metadata
c.execute("SELECT TOP 3 md5, bpm, [key], [mode], split FROM dbo.metadata")
print("\n── metadata sample ──")
cols = [d[0] for d in c.description]
print("  " + "  ".join(f"{col:>12}" for col in cols))
for row in c.fetchall():
    print("  " + "  ".join(f"{str(v):>12}" for v in row))

# Spot-check manifest
c.execute("SELECT TOP 3 md5, stored_path, n_copies FROM dbo.master_manifest")
print("\n── master_manifest sample ──")
cols = [d[0] for d in c.description]
print("  " + "  ".join(f"{col:>14}" for col in cols))
for row in c.fetchall():
    print("  " + "  ".join(f"{str(v):>14}" for v in row))

conn.close()
print("\n✅ Verification complete — SQL Server is live!")
