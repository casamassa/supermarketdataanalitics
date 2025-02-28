import pyodbc
from pymongo import MongoClient
from decimal import Decimal

# Configuração do MongoDB
MONGO_URI = "mongodb://localhost:27017"
MONGO_DB = "InvoicesDB"
MONGO_COLLECTION = "Invoices"

# Configuração do SQL Server
SQL_SERVER = "localhost"
SQL_DATABASE = "InvoicesDB"
SQL_USER = "sa"  # Se estiver usando autenticação do Windows, deixe vazio
SQL_PASSWORD = "123456"  # Se estiver usando autenticação do Windows, deixe vazio
SQL_DRIVER = "ODBC Driver 17 for SQL Server"  # Confirme se este driver está instalado

# Conectar ao MongoDB
mongo_client = MongoClient(MONGO_URI)
mongo_db = mongo_client[MONGO_DB]
mongo_collection = mongo_db[MONGO_COLLECTION]

# Conectar ao SQL Server
#conn_str = f"DRIVER={SQL_DRIVER};SERVER={SQL_SERVER};DATABASE={SQL_DATABASE};Trusted_Connection=yes"
conn_str = f"DRIVER={SQL_DRIVER};SERVER={SQL_SERVER};DATABASE={SQL_DATABASE};UID={SQL_USER};PWD={SQL_PASSWORD}"
conn = pyodbc.connect(conn_str)
cursor = conn.cursor()

# Criar tabelas no SQL Server (caso não existam)
cursor.execute("""
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='Invoices' AND xtype='U')
CREATE TABLE Invoices (
    Id INT IDENTITY(1,1) PRIMARY KEY,
    AccessKey NVARCHAR(60) UNIQUE,
    MarketName NVARCHAR(255),
    InvoiceDate DATETIME,
    TotalInvoice DECIMAL(18,2),
    QuantityTotalItems INT
)
""")

cursor.execute("""
IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='InvoiceItems' AND xtype='U')
CREATE TABLE InvoiceItems (
    Id INT IDENTITY(1,1) PRIMARY KEY,
    InvoiceId INT,
    Code NVARCHAR(50),
    Description NVARCHAR(255),
    Quantity DECIMAL(18,3),
    Unit NVARCHAR(10),
    Value DECIMAL(18,2),
    FOREIGN KEY (InvoiceId) REFERENCES Invoices(Id)
)
""")

conn.commit()
try:
    # Inserir dados do MongoDB no SQL Server
    for doc in mongo_collection.find():
        access_key = doc.get("AccessKey")
        market_name = doc.get("MarketName", "")
        invoice_date = doc.get("InvoiceDate")
        total_invoice = Decimal(str(doc.get("TotalInvoice", 0)))
        quantity_total_items = int(doc.get("QuantityTotalItems", 0))

        # Verificar se a fatura já existe para evitar duplicação
        cursor.execute("SELECT Id FROM Invoices WHERE AccessKey = ?", access_key)
        existing_invoice = cursor.fetchone()

        if existing_invoice:
            continue
        else:
            cursor.execute("""
                INSERT INTO Invoices (AccessKey, MarketName, InvoiceDate, TotalInvoice, QuantityTotalItems)
                OUTPUT INSERTED.ID
                VALUES (?, ?, ?, ?, ?)
            """, (access_key, market_name, invoice_date, total_invoice, quantity_total_items))
            #invoice_id = cursor.fetchone()[0]
            result = cursor.fetchone()
            invoice_id = result[0] if result else None

        # Inserir os itens da fatura
        for item in doc.get("Items", []):
            code = item.get("Code", "")
            description = item.get("Description", "")
            quantity = Decimal(str(item.get("Quantity", 0)))
            unit = item.get("Unit", "")
            value = Decimal(str(item.get("Value", 0)))

            cursor.execute("""
                INSERT INTO InvoiceItems (InvoiceId, Code, Description, Quantity, Unit, Value)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (invoice_id, code, description, quantity, unit, value))

    # Confirmar e fechar conexões
    conn.commit()
    cursor.close()
    conn.close()
    mongo_client.close()

    print("Exportação concluída com sucesso!")

except Exception as e:
    print(f"Erro durante a exportação: {e}")
