import pymongo
import sqlite3
from bson.decimal128 import Decimal128

# Conectar ao MongoDB
client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["InvoicesDB"]
collection = db["Invoices"]

# Conectar ao SQLite (Cria um arquivo se não existir)
sqlite_conn = sqlite3.connect("invoices.db")
cursor = sqlite_conn.cursor()

# Criar tabela (Ajuste os campos conforme necessário)
cursor.execute("""
    CREATE TABLE IF NOT EXISTS invoices (
        access_key TEXT PRIMARY KEY,
        market_name TEXT,
        invoice_date TEXT,
        total_invoice REAL,
        quantity_total_items INTEGER
    )
""")

# Buscar dados do MongoDB
data = collection.find({}, {"_id": 0})  # Exclui _id para evitar conflitos

# Inserir dados no SQLite
for doc in data:
    total_invoice = float(doc.get("TotalInvoice", Decimal128("0")).to_decimal())

    cursor.execute("""
        INSERT OR IGNORE INTO invoices 
        (access_key, market_name, invoice_date, total_invoice, quantity_total_items) 
        VALUES (?, ?, ?, ?, ?)
    """, (
        doc.get("AccessKey"),
        doc.get("MarketName"),
        doc.get("InvoiceDate"),
        total_invoice,  # Agora é um float
        doc.get("QuantityTotalItems"),
    ))

# Confirmar e fechar conexões
sqlite_conn.commit()
sqlite_conn.close()
client.close()

print("Dados do MongoDB salvos no SQLite com sucesso!")
