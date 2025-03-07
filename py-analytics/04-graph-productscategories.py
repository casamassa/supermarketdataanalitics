import pymongo
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

# Conectar ao MongoDB
client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["InvoicesDB"]
collection = db["Invoices"]

# Carregar dados do MongoDB
data = list(collection.find())

df = pd.DataFrame(data)

# Supondo que a categoria esteja presente no nome ou código do produto
# Se houver uma lógica mais clara para definir categorias, podemos ajustá-la

def classify_category(description):
    description = description.lower()
    if "banana" in description or "limao" in description or "cebola" in description:
        return "Frutas e Hortaliças"
    elif "iog" in description or "leite" in description:
        return "Laticínios"
    elif "choc" in description or "biscoito" in description:
        return "Doces e Biscoitos"
    elif "pao" in description or "massa" in description:
        return "Panificação"
    elif "beb" in description or "refri" in description:
        return "Bebidas"
    else:
        return "Outros"

# Aplicar categorização
items = []
for invoice in df["Items"]:
    for item in invoice:
        items.append({
            "Category": classify_category(item["Description"]),
            "Quantity": float(item["Quantity"].to_decimal())
        })

items_df = pd.DataFrame(items)

# Agrupar por categoria e somar quantidades
category_counts = items_df.groupby("Category")["Quantity"].sum().sort_values(ascending=False)

# Plotar gráfico
plt.figure(figsize=(10, 5))
sns.barplot(x=category_counts.index, y=category_counts.values, hue=category_counts.index, palette="viridis", legend=False)
plt.xlabel("Categoria de Produto")
plt.ylabel("Quantidade Total Comprada")
plt.title("Categorias de Produtos Mais Compradas")
plt.xticks(rotation=45)
plt.show()
