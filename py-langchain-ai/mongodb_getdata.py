from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

# Configurações do MongoDB
mongo_uri = os.getenv("MONGO_URI") # caso voce use um arquivo .env, ou o uri direto
db_name = "InvoicesDB"
collection_name = "Invoices"

try:
    client = MongoClient(mongo_uri)
    db = client[db_name]
    collection = db[collection_name]
    print("Conexão com o MongoDB estabelecida com sucesso!")

    # Exemplo de consulta (substitua com sua consulta)
    documentos = collection.find()
    for documento in documentos:
        print(documento)

except Exception as e:
    print(f"Erro ao conectar ao MongoDB: {e}")

finally:
    if 'client' in locals():
        client.close()