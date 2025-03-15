import telegram
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
import logging
from pymongo import MongoClient
from langchain_groq import ChatGroq
from langchain.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableSequence
from dotenv import load_dotenv
import os

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

logging.basicConfig(
    #filename='bot.log',  # Linha opcional, salva os logs em um arquivo chamado bot.log ao inves de exibir no console
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Conexão com o MongoDB (estabelecida uma vez)
client = MongoClient(MONGO_URI)
db = client["InvoicesDB"]
collection = db["Invoices"]

# Configurações do Groq (estabelecidas uma vez)
chat = ChatGroq(model="llama-3.3-70b-versatile", groq_api_key=GROQ_API_KEY) #altere o modelo caso deseje

async def start(update, context):
    chat_id = update.effective_chat.id
    logging.info(f"Comando /start recebido do chat_id: {chat_id}")
    await context.bot.send_message(chat_id=chat_id, text="Olá! Eu sou seu robo de Gastos de Mercado.")

async def echo(update, context):
    chat_id = update.effective_chat.id
    mensagem = update.message.text
    logging.info(f"Mensagem recebida do chat_id {chat_id}: {mensagem}")

    # Consulta ao MongoDB e remoção do _id
    documentos = collection.find()
    #dados_mongodb = "\n".join([str({k: v for k, v in doc.items() if k != '_id'}) for doc in documentos])
    dados_mongodb = "\n".join([repr({k: v for k, v in doc.items() if k != '_id'}) for doc in documentos])

    # Prompt para o modelo de IA
    prompt = ChatPromptTemplate.from_template("Com base nos dados do MongoDB: {dados}, responda a seguinte pergunta: {input}")

    # Chain da LangChain
    chain = RunnableSequence(prompt, chat)

    # Execução da Chain
    resposta = await chain.ainvoke({"input": mensagem, "dados": dados_mongodb})

    await context.bot.send_message(chat_id=chat_id, text=resposta.content)

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)

    echo_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), echo)
    application.add_handler(echo_handler)

    application.run_polling()
    
    client.close() # Fechando a conexão com o MongoDB

if __name__ == '__main__':
    main()