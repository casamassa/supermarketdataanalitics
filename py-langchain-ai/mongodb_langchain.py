from pymongo import MongoClient
from langchain_groq import ChatGroq
from langchain.prompts import ChatPromptTemplate
from langchain.chains import LLMChain
from dotenv import load_dotenv
import os

load_dotenv()

# Configurações do MongoDB
mongo_uri = os.getenv("MONGO_URI")
db_name = "InvoicesDB"
collection_name = "Invoices"

# Configurações da LangChain e Groq
groq_api_key = os.getenv("GROQ_API_KEY")
chat = ChatGroq(model="llama-3.3-70b-versatile", groq_api_key=groq_api_key) #altere o modelo caso deseje

# Conexão com o MongoDB
client = MongoClient(mongo_uri)
db = client[db_name]
collection = db[collection_name]

# Consulta ao MongoDB
documentos = collection.find()
dados_mongodb = "\n".join([str(doc) for doc in documentos])

# Prompt para o modelo de IA
prompt = ChatPromptTemplate.from_template(
    "Resuma os seguintes dados do MongoDB:\n\n{dados}\n\nResumo:"
)

# Chain da LangChain
chain = LLMChain(llm=chat, prompt=prompt)

# Execução da Chain
resposta = chain.run(dados=dados_mongodb)
print(resposta)

client.close()