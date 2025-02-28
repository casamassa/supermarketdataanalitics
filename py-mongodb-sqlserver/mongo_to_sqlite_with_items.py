import sqlite3
from bson.decimal128 import Decimal128
from pymongo import MongoClient

# Conectar ao MongoDB
mongo_client = MongoClient("mongodb://localhost:27017/")
mongo_db = mongo_client["InvoicesDB"]
mongo_collection = mongo_db["Invoices"]

# Conectar ao SQLite
sqlite_conn = sqlite3.connect("invoices_with_items.db")
cursor = sqlite_conn.cursor()

# Criar tabela de Invoices (caso não exista)
cursor.execute("""
CREATE TABLE IF NOT EXISTS Invoices (
    AccessKey TEXT PRIMARY KEY,
    MarketName TEXT,
    InvoiceDate TEXT,
    TotalInvoice REAL,
    QuantityTotalItems INTEGER
)
""")

# Criar tabela de Items (caso não exista)
cursor.execute("""
CREATE TABLE IF NOT EXISTS InvoiceItems (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    AccessKey TEXT,
    Code TEXT,
    Description TEXT,
    Quantity REAL,
    Unit TEXT,
    Value REAL,
    FOREIGN KEY (AccessKey) REFERENCES Invoices (AccessKey)
)
""")

# Inserir dados do MongoDB para SQLite
for doc in mongo_collection.find():
    access_key = doc.get("AccessKey", "")
    market_name = doc.get("MarketName", "")
    invoice_date = doc.get("InvoiceDate", "")
    total_invoice = float(doc.get("TotalInvoice", Decimal128("0")).to_decimal())
    quantity_total_items = doc.get("QuantityTotalItems", 0)

    # Inserir na tabela Invoices
    cursor.execute("""
        INSERT OR IGNORE INTO Invoices (AccessKey, MarketName, InvoiceDate, TotalInvoice, QuantityTotalItems)
        VALUES (?, ?, ?, ?, ?)
    """, (access_key, market_name, invoice_date, total_invoice, quantity_total_items))

    # Inserir os itens da invoice
    for item in doc.get("Items", []):
        code = item.get("Code", "")
        description = item.get("Description", "")
        quantity = float(item.get("Quantity", Decimal128("0")).to_decimal())
        unit = item.get("Unit", "")
        value = float(item.get("Value", Decimal128("0")).to_decimal())

        cursor.execute("""
            INSERT INTO InvoiceItems (AccessKey, Code, Description, Quantity, Unit, Value)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (access_key, code, description, quantity, unit, value))

# Commit e fechar conexões
sqlite_conn.commit()
sqlite_conn.close()
mongo_client.close()

print("Exportação concluída com sucesso! 🚀")
