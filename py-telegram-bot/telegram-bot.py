import telegram
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
import logging
from dotenv import load_dotenv
import os

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")

logging.basicConfig(
    filename='bot.log',  # Linha opcional, salva os logs em um arquivo chamado bot.log ao inves de exibir no console
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

async def start(update, context): # Adicionado async
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Olá! Eu sou seu robo de Gastos de Mercado.")

async def echo(update, context): # Adicionado async
    mensagem = update.message.text
    logging.info(f"Mensagem recebida: {mensagem}")  # Registra a mensagem recebida
    if "ola" in mensagem.lower():
        resposta = "Olá! Como posso ajudar?"
    elif "como vai" in mensagem.lower():
        resposta = "Vou bem, obrigado!"
    else:
        resposta = f"Voce disse: {mensagem}"
    logging.info(f"Resposta: {resposta}")  # Registra a mensagem recebida
    await context.bot.send_message(chat_id=update.effective_chat.id, text=resposta)

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    start_handler = CommandHandler('start', start)
    application.add_handler(start_handler)

    echo_handler = MessageHandler(filters.TEXT & (~filters.COMMAND), echo)
    application.add_handler(echo_handler)

    application.run_polling()

if __name__ == '__main__':
    main()