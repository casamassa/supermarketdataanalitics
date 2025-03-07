import pymongo
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from bson.decimal128 import Decimal128

# Conectar ao MongoDB
client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["InvoicesDB"]  # Substitua pelo nome do seu banco de dados
collection = db["Invoices"]  # Substitua pelo nome da sua collection

# Carregar os dados
cursor = collection.find()
data = list(cursor)

# Criar DataFrame do Pandas
df = pd.DataFrame(data)

# Converter datas
if 'InvoiceDate' in df.columns:
    df['InvoiceDate'] = pd.to_datetime(df['InvoiceDate'])

# Converter TotalInvoice para float
if 'TotalInvoice' in df.columns:
    df['TotalInvoice'] = df['TotalInvoice'].apply(lambda x: float(x.to_decimal()) if isinstance(x, Decimal128) else float(x))

# Expandir os itens
items = []
for doc in data:
    for item in doc['Items']:
        items.append({
            'InvoiceDate': doc['InvoiceDate'],
            'MarketName': doc['MarketName'],
            'AccessKey': doc['AccessKey'],
            'Code': item['Code'],
            'Description': item['Description'],
            'Quantity': float(item['Quantity'].to_decimal()) if isinstance(item['Quantity'], Decimal128) else float(item['Quantity']),
            'Unit': item['Unit'],
            'Value': float(item['Value'].to_decimal()) if isinstance(item['Value'], Decimal128) else float(item['Value'])
        })

# Gráfico: Distribuição dos valores das compras
plt.figure(figsize=(12, 6))
sns.histplot(df['TotalInvoice'], bins=20, kde=True, color='teal')
plt.xlabel("Valor da Compra (R$)")
plt.ylabel("Frequência")
plt.title("Distribuição dos Valores das Compras")
plt.show()
