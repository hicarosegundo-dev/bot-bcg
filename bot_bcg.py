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

# Habilita o log para nos ajudar a encontrar erros
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# =========================================================================
# PARTE 1: LÓGICA DO CONVERSATIONHANDLER PARA O CADASTRO SIMPLIFICADO
# =========================================================================

# Definindo os "passos" ou "estados" da nossa conversa de cadastro.
NOME, MATRICULA = range(2)

async def cadastrar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inicia a conversa para o cadastro e pede o nome completo."""
    await update.message.reply_text(
        "Olá! Para iniciar seu cadastro, por favor, envie seu nome completo."
    )
    return NOME

async def receber_nome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Salva o nome do usuário e pede a matrícula."""
    context.user_data['nome'] = update.message.text
    logger.info("Nome do usuário %s: %s", update.effective_user.first_name, update.message.text)
    
    await update.message.reply_text(
        "Ótimo! Agora, por favor, envie sua matrícula."
    )
    return MATRICULA

async def receber_matricula(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Salva a matrícula e encerra a conversa."""
    logger.info("Matrícula do usuário %s: %s", update.effective_user.first_name, update.message.text)

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
    """Cancela e encerra a conversa."""
    await update.message.reply_text(
        "Operação cancelada."
    )
    context.user_data.clear()
    return ConversationHandler.END

# =========================================================================
# PARTE 2: FUNÇÃO MAIN COM LOGS DE DEPURAÇÃO
# =========================================================================

def main() -> None:
    """Inicia o bot e o configura para rodar com webhook."""

    print("--- INICIANDO PROCESSO DE DEPURAÇÃO ---")

    # 1. VERIFICA O TOKEN DO BOT
    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    if TOKEN:
        # Por segurança, não vamos imprimir o token todo, só o início.
        print(f"✅ Variável TELEGRAM_TOKEN encontrada! Começa com: {TOKEN[:5]}...")
    else:
        print("❌ ERRO CRÍTICO: Variável de ambiente TELEGRAM_TOKEN não foi encontrada ou está vazia!")
        raise ValueError("Variável de ambiente TELEGRAM_TOKEN não configurada! O bot não pode iniciar.")

    # 2. CRIA A APLICAÇÃO
    application = Application.builder().token(TOKEN).build()

    # 3. CONFIGURA O CONVERSATIONHANDLER DE CADASTRO
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

    # 4. VERIFICA AS VARIÁVEIS DO RENDER
    PORT = int(os.environ.get('PORT', '8443'))
    WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL")
    
    print(f"Porta que o Render forneceu: {PORT}")
    
    if WEBHOOK_URL:
        print(f"✅ Webhook URL encontrada: {WEBHOOK_URL}")
    else:
        print("❌ ERRO CRÍTICO: Variável de ambiente RENDER_EXTERNAL_URL não foi encontrada!")
        raise ValueError("Variável de ambiente RENDER_EXTERNAL_URL não encontrada!")

    # 5. INICIA O BOT EM MODO WEBHOOK
    print("--- FIM DA DEPURAÇÃO. Iniciando o bot agora... ---")
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL,
        set_webhook=True
    )

if __name__ == "__main__":
    main()