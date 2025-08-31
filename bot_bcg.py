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
    # Aqui é onde você salvaria os dados em um banco de dados real
    # Por exemplo: salvar_usuario(chat_id=update.effective_user.id, nome=context.user_data['nome'], matricula=update.message.text)
    
    logger.info("Matrícula do usuário %s: %s", update.effective_user.first_name, update.message.text)

    await update.message.reply_text(
        f"Cadastro concluído com sucesso!\n\n"
        f"<b>Nome:</b> {context.user_data['nome']}\n"
        f"<b>Matrícula:</b> {update.message.text}\n\n" # Usando o texto direto da mensagem
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
# PARTE 2: ESTRUTURA PRINCIPAL E INICIALIZAÇÃO COM WEBHOOK
# =========================================================================

def main() -> None:
    """Inicia o bot e o configura para rodar com webhook."""
    
    # 1. PEGA O TOKEN DO BOT (deve ser configurado no Render)
    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    if not TOKEN:
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
    
    # Adiciona um comando de start simples para o bot responder a algo
    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Olá! Use /cadastrar para iniciar seu cadastro.")
    application.add_handler(CommandHandler("start", start))

    # 4. CONFIGURA O WEBHOOK PARA O RENDER
    # O Render nos informa a porta e a URL através de variáveis de ambiente.
    PORT = int(os.environ.get('PORT', '8443'))
    WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL")