import logging
import re
import gspread
import pdfplumber
import os
import io
import json
from oauth2client.service_account import ServiceAccountCredentials
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes,
)

# --- CONFIGURAÇÕES LIDAS DO AMBIENTE ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
# ----------------------------------------

# Constante para o limite da mensagem do Telegram
MAX_MESSAGE_LENGTH = 4096

# Configuração do logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# MODIFICADO: Estados da conversa de cadastro (sem o número do PM)
(PEDINDO_NOME, PEDINDO_MATRICULA) = range(2)

# Dicionário em memória para guardar os dados dos usuários
usuarios_dados_completos = {}

# --- FUNÇÕES DO GOOGLE SHEETS ---

def get_gspread_client():
    """Autentica com o Google Sheets usando variáveis de ambiente."""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    creds_json_str = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not creds_json_str:
        logger.error("A variável de ambiente GOOGLE_CREDENTIALS_JSON não foi encontrada.")
        return None
        
    creds_dict = json.loads(creds_json_str)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

def carregar_usuarios_da_planilha():
    """Carrega ou recarrega os usuários da planilha para a memória."""
    try:
        client = get_gspread_client()
        if not client:
            raise Exception("Falha ao autenticar com o Google.")
            
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1
        records = sheet.get_all_records()
        
        usuarios_dados_completos.clear()
        
        for record in records:
            if "Nome" in record and "ID Telegram" in record:
                nome_completo_original = str(record.get("Nome", "")).strip().upper()
                id_telegram = record.get("ID Telegram")
                
                if not nome_completo_original or not id_telegram:
                    continue

                usuarios_dados_completos[nome_completo_original] = {
                    "id": str(id_telegram).strip(),
                    "pm": str(record.get("PM", "")).strip(), # Continua lendo para não quebrar a lógica
                    "nome_completo": nome_completo_original,
                    "matricula": str(record.get("Matrícula", "")).replace("-", "").replace(".", "").strip(),
                }
        logger.info(f"Planilha carregada. {len(usuarios_dados_completos)} usuários em memória.")
    except Exception as e:
        logger.error(f"Erro ao carregar a planilha: {e}")

def adicionar_usuario_na_planilha(pm, nome, matricula, id_telegram):
    """Adiciona um novo usuário na planilha e recarrega os dados."""
    try:
        client = get_gspread_client()
        if not client:
            raise Exception("Falha ao autenticar com o Google.")
            
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1
        
        # A coluna PM será preenchida com um valor vazio
        row = [pm, nome, matricula, id_telegram]
        sheet.append_row(row)
        
        carregar_usuarios_da_planilha()
        logger.info(f"Novo usuário adicionado na planilha: {nome}")
        return True
    except Exception as e:
        logger.error(f"Erro ao adicionar usuário na planilha: {e}")
        return False

# --- FUNÇÕES DO BOT (HANDLERS) ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envia uma mensagem de boas-vindas com o menu."""
    keyboard = [['Cadastrar']]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(
        "Olá! Eu sou o Bot BCG. Clique em 'Cadastrar' para se registrar ou envie um PDF para análise.",
        reply_markup=reply_markup
    )

async def start_cadastro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """MODIFICADO: Inicia a conversa de cadastro pedindo o nome."""
    await update.message.reply_text(
        "Para iniciar seu cadastro, por favor, envie seu nome completo.",
        reply_markup=ReplyKeyboardRemove()
    )
    return PEDINDO_NOME

async def pedir_matricula(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """MODIFICADO: Recebe o nome e pede a matrícula."""
    context.user_data['full_name'] = update.message.text
    await update.message.reply_text("Entendido. Agora, qual a sua matrícula funcional?")
    return PEDINDO_MATRICULA

async def finalizar_cadastro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """MODIFICADO: Recebe a matrícula e finaliza, sem o número do PM."""
    matricula = update.message.text
    nome = context.user_data.get('full_name', '').upper()
    id_telegram = update.message.from_user.id
    
    # Passa um valor vazio "" para o número do PM
    if adicionar_usuario_na_planilha("", nome, matricula, id_telegram):
        await update.message.reply_text(
            "Cadastro realizado com sucesso!\n\n"
            "Você será avisado quando seu nome for mencionado em um BCG.\n"
            "Qualquer dúvida, entre em contato com 88 998579806."
        )
    else:
        await update.message.reply_text(
            "Ocorreu um erro ao salvar seus dados. Por favor, tente novamente mais tarde."
        )

    context.user_data.clear()
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Cadastro cancelado.", reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END

async def verificar_mensagens(update: Update, context: ContextTypes.DEFAULT_TYPE, texto_completo: str) -> None:
    """Verifica o texto por nomes cadastrados e notifica os usuários."""
    nomes_encontrados_com_detalhes = {}
    
    header_match = re.search(r'BCG nº \d+.*', texto_completo, re.IGNORECASE)
    header_simples = header_match.group(0).strip() if header_match else "uma publicação"

    for nome_usuario, detalhes_usuario in usuarios_dados_completos.items():
        termos = [detalhes_usuario["pm"], detalhes_usuario["nome_completo"], detalhes_usuario["matricula"]]
        termos_validos = [t for t in termos if t]
        
        if not termos_validos:
            continue
            
        regex_termos = '|'.join(re.escape(t) for t in termos_validos)
        
        if re.search(r'\b(' + regex_termos + r')\b', texto_completo, re.IGNORECASE):
            pos = re.search(r'\b(' + regex_termos + r')\b', texto_completo, re.IGNORECASE).start()
            start_pos = max(0, pos - 150)
            end_pos = min(len(texto_completo), pos + 150)
            trecho_final = "..." + texto_completo[start_pos:end_pos].strip() + "..."
            
            mensagem_final = (
                f"Olá, {detalhes_usuario['nome_completo']}!\n\n"
                f"Você foi mencionado(a) em {header_simples}.\n\n"
                f"Trecho da citação:\n{trecho_final}\n\n"
                f"Acesse https://sisbol.pm.ce.gov.br/login_bcg/ para ver na íntegra."
            )
            
            if len(mensagem_final) > MAX_MESSAGE_LENGTH:
                mensagem_final = mensagem_final[:MAX_MESSAGE_LENGTH - 4] + "..."
            
            nomes_encontrados_com_detalhes[detalhes_usuario['id']] = mensagem_final

    if not nomes_encontrados_com_detalhes:
        await update.message.reply_text("Análise concluída. Nenhum usuário cadastrado foi encontrado na publicação.")
        return

    nomes_notificados = []
    for user_id, mensagem in nomes_encontrados_com_detalhes.items():
        try:
            await context.bot.send_message(chat_id=user_id, text=mensagem)
            for nome, detalhes in usuarios_dados_completos.items():
                if detalhes['id'] == user_id:
                    nomes_notificados.append(nome)
                    break
        except Exception as e:
            logger.error(f"Falha ao enviar notificação para ID {user_id}: {e}")
            
    if nomes_notificados:
        await update.message.reply_text(f"Notificações enviadas para: {', '.join(nomes_notificados)}.")

async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Processa o PDF em memória."""
    await update.message.reply_text("Recebi o PDF. Analisando, por favor, aguarde...")
    try:
        pdf_file = await context.bot.get_file(update.message.document.file_id)
        pdf_bytes = await pdf_file.download_as_bytearray()
        
        texto_completo = ""
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                texto_completo += page.extract_text() or ""
        
        if texto_completo:
            await verificar_mensagens(update, context, texto_completo=texto_completo)
        else:
            await update.message.reply_text("Não foi possível extrair texto do PDF.")
    except Exception as e:
        logger.error(f"Erro ao processar PDF: {e}")
        await update.message.reply_text("Ocorreu um erro ao processar o arquivo PDF.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lida com mensagens de texto que não são comandos."""
    if update.message.text:
        greetings = ['oi', 'olá', 'bom dia', 'boa tarde', 'boa noite']
        if any(greeting in update.message.text.lower() for greeting in greetings):
             await start(update, context)
             return
        await verificar_mensagens(update, context, texto_completo=update.message.text)

# --- FUNÇÃO PRINCIPAL (MAIN) ---

def main() -> None:
    """Inicia o bot no modo Webhook para o Render."""
    
    carregar_usuarios_da_planilha()
    
    if not TOKEN:
        logger.critical("Variável de ambiente TELEGRAM_TOKEN não configurada!")
        return

    application = Application.builder().token(TOKEN).build()
    
    # MODIFICADO: ConversationHandler com o fluxo simplificado
    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex('^Cadastrar$'), start_cadastro)],
        states={
            PEDINDO_NOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, pedir_matricula)],
            PEDINDO_MATRICULA: [MessageHandler(filters.TEXT & ~filters.COMMAND, finalizar_cadastro)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.Document.PDF, handle_pdf))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    PORT = int(os.environ.get('PORT', 8080))
    WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL")

    if not WEBHOOK_URL:
        logger.error("Variável de ambiente RENDER_EXTERNAL_URL não encontrada.")
        return
        
    logger.info(f"Iniciando webhook na porta {PORT}")
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        webhook_url=WEBHOOK_URL
    )

if __name__ == '__main__':
    main()