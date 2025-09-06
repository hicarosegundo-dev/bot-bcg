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

# Estados da conversa de cadastro
(PEDINDO_NOME, PEDINDO_MATRICULA) = range(2)

# Dicionário em memória para guardar os dados dos usuários
usuarios_dados_completos = {}

# --- FUNÇÕES DO GOOGLE SHEETS ---

def get_gspread_client():
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
                    "pm": str(record.get("PM", "")).strip(),
                    "nome_completo": nome_completo_original,
                    "matricula": str(record.get("Matrícula", "")).replace("-", "").replace(".", "").strip(),
                }
        logger.info(f"Planilha carregada. {len(usuarios_dados_completos)} usuários em memória.")
    except Exception as e:
        logger.error(f"Erro ao carregar a planilha: {e}")

def adicionar_usuario_na_planilha(pm, nome, matricula, id_telegram):
    try:
        client = get_gspread_client()
        if not client:
            raise Exception("Falha ao autenticar com o Google.")
        sheet = client.open_by_key(SPREADSHEET_ID).sheet1
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
    keyboard = [['Cadastrar']]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(
        "Olá! Eu sou o Bot BCG. Clique em 'Cadastrar' para se registrar ou envie um PDF para análise.",
        reply_markup=reply_markup
    )

async def start_cadastro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Para iniciar seu cadastro, por favor, envie seu nome completo.",
        reply_markup=ReplyKeyboardRemove()
    )
    return PEDINDO_NOME

async def pedir_matricula(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['full_name'] = update.message.text
    await update.message.reply_text("Entendido. Agora, qual a sua matrícula funcional?")
    return PEDINDO_MATRICULA

async def finalizar_cadastro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    matricula = update.message.text
    nome = context.user_data.get('full_name', '').upper()
    id_telegram = update.message.from_user.id
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

# MODIFICADO: Esta função agora só busca, não envia notificações
def buscar_nomes_no_texto(texto_pagina: str, header: str):
    """Busca usuários no texto de uma única página e retorna um dicionário de notificações."""
    notificacoes_encontradas = {}
    
    for nome_usuario, detalhes_usuario in usuarios_dados_completos.items():
        # Evita notificar o mesmo usuário mais de uma vez
        if detalhes_usuario['id'] in [v['user_id'] for v in notificacoes_encontradas.values()]:
            continue
            
        termos = [detalhes_usuario["pm"], detalhes_usuario["nome_completo"], detalhes_usuario["matricula"]]
        termos_validos = [t for t in termos if t]
        if not termos_validos:
            continue
            
        regex_termos = '|'.join(re.escape(t) for t in termos_validos)
        if re.search(r'\b(' + regex_termos + r')\b', texto_pagina, re.IGNORECASE):
            pos = re.search(r'\b(' + regex_termos + r')\b', texto_pagina, re.IGNORECASE).start()
            start_pos = max(0, pos - 150)
            end_pos = min(len(texto_pagina), pos + 150)
            trecho_final = "..." + texto_pagina[start_pos:end_pos].strip() + "..."
            
            mensagem_final = (
                f"Olá, {detalhes_usuario['nome_completo']}!\n\n"
                f"Você foi mencionado(a) em {header}.\n\n"
                f"Trecho da citação:\n{trecho_final}\n\n"
                f"Acesse https://sisbol.pm.ce.gov.br/login_bcg/ para ver na íntegra."
            )
            
            if len(mensagem_final) > MAX_MESSAGE_LENGTH:
                mensagem_final = mensagem_final[:MAX_MESSAGE_LENGTH - 4] + "..."
            
            notificacoes_encontradas[detalhes_usuario['id']] = {
                "user_id": detalhes_usuario['id'],
                "nome": detalhes_usuario['nome_completo'],
                "mensagem": mensagem_final
            }
            
    return notificacoes_encontradas

# MODIFICADO: Lógica de processamento de PDF página por página
async def handle_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Recebi o PDF. Analisando página por página, isso pode levar um tempo...")
    try:
        pdf_file = await context.bot.get_file(update.message.document.file_id)
        pdf_bytes = await pdf_file.download_as_bytearray()
        
        master_notificacoes = {}
        texto_header = ""
        
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            # Pega o cabeçalho da primeira página
            primeira_pagina_texto = pdf.pages[0].extract_text() or ""
            header_match = re.search(r'BCG nº \d+.*', primeira_pagina_texto, re.IGNORECASE)
            texto_header = header_match.group(0).strip() if header_match else "uma publicação"

            # Processa página por página
            for i, page in enumerate(pdf.pages):
                logger.info(f"Processando página {i+1}/{len(pdf.pages)}...")
                texto_da_pagina = page.extract_text() or ""
                if texto_da_pagina:
                    novas_notificacoes = buscar_nomes_no_texto(texto_da_pagina, texto_header)
                    # Adiciona novas notificações, evitando duplicatas
                    for user_id, notificacao in novas_notificacoes.items():
                        if user_id not in master_notificacoes:
                            master_notificacoes[user_id] = notificacao

        if not master_notificacoes:
            await update.message.reply_text("Análise concluída. Nenhum usuário cadastrado foi encontrado na publicação.")
            return

        # Envia as notificações consolidadas
        nomes_notificados = []
        for user_id, notificacao in master_notificacoes.items():
            try:
                await context.bot.send_message(chat_id=user_id, text=notificacao['mensagem'])
                nomes_notificados.append(notificacao['nome'])
            except Exception as e:
                logger.error(f"Falha ao enviar notificação para ID {user_id}: {e}")
        
        if nomes_notificados:
            await update.message.reply_text(f"Análise concluída. Notificações enviadas para: {', '.join(nomes_notificados)}.")

    except Exception as e:
        logger.error(f"Erro detalhado ao processar PDF: {e}")
        await update.message.reply_text(f"Ocorreu um erro crítico ao processar o arquivo PDF.")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Esta função agora só lida com saudações para mostrar o menu
    if update.message.text:
        greetings = ['oi', 'olá', 'bom dia', 'boa tarde', 'boa noite']
        if any(greeting in update.message.text.lower() for greeting in greetings):
             await start(update, context)

# --- FUNÇÃO PRINCIPAL (MAIN) ---

def main() -> None:
    """Inicia o bot no modo Polling para o servidor."""
    
    carregar_usuarios_da_planilha()
    
    if not TOKEN:
        logger.critical("Variável de ambiente TELEGRAM_TOKEN não configurada!")
        return

    application = Application.builder().token(TOKEN).build()
    
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
    # Removemos o handler de texto genérico para evitar que ele analise qualquer mensagem
    # application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    logger.info("Iniciando o bot no modo polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()