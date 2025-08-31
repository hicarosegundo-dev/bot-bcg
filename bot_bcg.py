import logging
import os
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# Habilita o log
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- LÓGICA DO CONVERSATIONHANDLER (CADASTRO) ---
NOME, MATRICULA = range(2)

async def cadastrar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Olá! Para iniciar seu cadastro, por favor, envie seu nome completo."
    )
    return NOME

async def receber_nome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['nome'] = update.message.text
    await update.message.reply_text(
        "Ótimo! Agora, por favor, envie sua matrícula."
    )
    return MATRICULA

async def receber_matricula(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        f"Cadastro concluído com sucesso!\n\n"
        f"<b>Nome:</b> {context.user_data['nome']}\n"
        f"<b>Matrícula:</b> {update.message.text}\n\n"
        f"Obrigado!",
        parse_mode='HTML'
    )
    context.user_data.clear()
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Operação cancelada.")
    context.user_data.clear()
    return ConversationHandler.END

# --- FUNÇÃO MAIN ---
def main() -> None:
    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    if not TOKEN:
        raise ValueError("Variável de ambiente TELEGRAM_TOKEN não configurada!")

    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("cadastrar", cadastrar)],
        states={
            NOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nome)],
            MATRICULA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_matricula)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )
    application.add_handler(conv_handler)
    
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Olá! Use /cadastrar para iniciar seu cadastro.")
    application.add_handler(CommandHandler("start", start))

    PORT = int(os.environ.get('PORT', '8443'))
    WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL")
    
    if not WEBHOOK_URL:
        raise ValueError("Variável de ambiente RENDER_EXTERNAL_URL não encontrada!")

    logger.info(f"Iniciando o bot com webhook na URL: {WEBHOOK_URL}")
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL
    )

if __name__ == "__main__":
    main()