import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

# ===================== CONFIG =====================
BOT_TOKEN = "8269520257:AAHlSjUjstyFDf7sMSxXvkxCQ1_MogHvRrY"  # 🔑 coloque o token do seu bot aqui
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

ADMINS = ["Hidalgo73", "ativabott"]  # 🔑 usernames que são admins

PIX_COPIA_E_COLA = (
    "00020101021126580014br.gov.bcb.pix01363c22457a-3a09-44fb-adc5-34f11cd07da35204000053039865802BR5919"
    "INGRID G F DA COSTA6011SALESOPOLIS62070503***630411DF"
)
PIX_QR_PATH = "QR CODE.jpg"

DB_PATH = "bot_iptv.db"

# ===================== LOG =====================
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot_iptv")

# ===================== PLANOS =====================
PLANOS = {
    "ABE PLAYER": "R$11 ou 10 Crédito",
    "ALL PLAYER": "R$11 ou 10 Crédito",
    "ASSIST PLUS": "R$10 ou 0.6 Crédito",
    "BUZZTV PLAYER": "R$13 ou 1 Crédito",
    "CANAL PLAY": "R$10 ou 0.6 Crédito",
    "EVPLAYER": "R$13 ou 1 Crédito",
    "FLIX PLAYER": "R$12 ou 0.8 Crédito",
    "IPTV PLAYER": "R$11 ou 0.6 Crédito",
    "KING PLAYER": "R$11 ou 0.6 Crédito",
    "MEGABOX PLAYER": "R$11 ou 0.6 Crédito",
    "NET IPTV": "R$11 ou 0.6 Crédito",
    "PLAYER MAX": "R$11 ou 0.6 Crédito",
    "RED PLAYER": "R$11 ou 0.6 Crédito",
    "SMART PLAYER": "R$11 ou 0.6 Crédito",
    "SSIPTV": "R$11 ou 0.6 Crédito",
    "SUPER PLAYER": "R$11 ou 0.6 Crédito",
}

# ===================== TEXTOS =====================
HOW_IT_WORKS = (
    "⚠️ Aviso: Este bot não libera canais!\n\n"
    "Como ativar a *licença anual* do app:\n"
    "1) Toque em **📲 Ativar um Aplicativo** e escolha o app.\n"
    "2) Envie a **Chave MAC** corretamente (ex: 00:1A:79:12:34:56).\n"
    "3) Pague via **PIX** (QR ou copia-e-cola) e envie **📷 o comprovante** aqui.\n"
    "4) Ativando seu aplicativo. Isso pode levar alguns instantes...\n"
    "Dica: revise a MAC antes de enviar para evitar atrasos."
)

TERMS = (
    "📜 Termos de Uso\n\n"
    "• O bot serve apenas para ativar licenças dos aplicativos listados.\n"
    "• Não fornecemos listas, canais ou conteúdos.\n"
    "• Pagamentos e ativações são manuais e podem exigir conferência.\n"
    "• MAC incorreta é de responsabilidade do usuário.\n"
    "• Após ativação, não há reembolso.\n"
    "• Ao usar, você concorda com estes termos."
)

SUPPORT_TEXT = (
    "👨‍💻 Suporte\n\n"
    "Fale diretamente com o responsável:\n"
    "➡️ @ativabott"
)

# ===================== DB =====================
def db():
    return sqlite3.connect(DB_PATH)

def _column_exists(cur, table: str, column: str) -> bool:
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    return column in cols

def init_db():
    con = db()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS activations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            app TEXT,
            mac TEXT,
            file_message_id INTEGER,
            created_at TEXT,
            expires_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admin_chats (
            chat_id INTEGER PRIMARY KEY
        )
    """)
    con.commit()
    con.close()

def add_admin_chat_id(chat_id: int):
    con = db()
    cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO admin_chats (chat_id) VALUES (?)", (int(chat_id),))
    con.commit()
    con.close()

def get_admin_chat_ids() -> list[int]:
    con = db()
    cur = con.cursor()
    ids = set()
    cur.execute("SELECT value FROM config WHERE key='admin_chat_id'")
    row = cur.fetchone()
    if row and row[0]:
        try:
            ids.add(int(row[0]))
        except:
            pass
    cur.execute("SELECT chat_id FROM admin_chats")
    ids.update(int(r[0]) for r in cur.fetchall())
    con.close()
    return list(ids)

def add_activation(user_id: int, username: str | None, app: str, mac: str, file_message_id: int | None):
    con = db()
    cur = con.cursor()
    created_at = datetime.now()
    expires_at = created_at + timedelta(days=365)
    cur.execute(
        "INSERT INTO activations (user_id, username, app, mac, file_message_id, created_at, expires_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            user_id, username, app, mac, file_message_id,
            created_at.strftime("%Y-%m-%d %H:%M:%S"),
            expires_at.strftime("%Y-%m-%d %H:%M:%S")
        )
    )
    con.commit()
    con.close()
    return created_at, expires_at

def listar_ativacoes():
    con = db()
    cur = con.cursor()
    cur.execute("SELECT username, app, mac, created_at, expires_at FROM activations ORDER BY expires_at ASC")
    rows = cur.fetchall()
    con.close()
    return rows

# ===================== FSM =====================
class Activate(StatesGroup):
    choosing_app = State()
    entering_mac = State()
    waiting_receipt = State()

# ===================== MENUS =====================
def main_menu() -> types.ReplyKeyboardMarkup:
    return types.ReplyKeyboardMarkup(
        keyboard=[
            [types.KeyboardButton(text="📲 Ativar um Aplicativo")],
            [types.KeyboardButton(text="💳 Pagamento (PIX)")],
            [types.KeyboardButton(text="💰 Tabela de Valores")],
            [types.KeyboardButton(text="❓ Como Funciona o Bot"), types.KeyboardButton(text="📜 Termos de Uso")],
            [types.KeyboardButton(text="🆘 Suporte"), types.KeyboardButton(text="👥 Clientes")],
        ],
        resize_keyboard=True
    )

def apps_keyboard() -> types.ReplyKeyboardMarkup:
    rows = []
    row = []
    for i, app in enumerate(PLANOS.keys(), start=1):
        row.append(types.KeyboardButton(text=app))
        if i % 2 == 0:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([types.KeyboardButton(text="⬅️ Voltar ao Menu")])
    return types.ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)

def prices_text() -> str:
    lines = ["💰 Tabela de Valores\n"]
    for app, preco in PLANOS.items():
        lines.append(f"🔹 {app}\n{preco}\n")
    return "\n".join(lines)

def is_mac_text(txt: str) -> bool:
    import re
    t = txt.strip()
    return bool(re.match(r"^([0-9A-Fa-f]{2}([-:])){5}[0-9A-Fa-f]{2}$", t)) or len(t.replace(":", "").replace("-", "")) >= 12

# ===================== HANDLERS =====================
@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 Bem-vindo ao *Bot de Ativações*!\nEscolha uma opção abaixo:",
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )

@router.message(F.text == "❓ Como Funciona o Bot")
async def how_it_works(message: types.Message):
    await message.answer(HOW_IT_WORKS, parse_mode="Markdown")

@router.message(F.text == "📜 Termos de Uso")
async def terms(message: types.Message):
    await message.answer(TERMS)

@router.message(F.text == "🆘 Suporte")
async def support(message: types.Message):
    await message.answer(SUPPORT_TEXT)

@router.message(F.text == "💰 Tabela de Valores")
async def tabela(message: types.Message):
    await message.answer(prices_text())

@router.message(F.text == "💳 Pagamento (PIX)")
async def pagamento(message: types.Message):
    try:
        await message.answer_photo(types.FSInputFile(PIX_QR_PATH), caption="💳 Pague via PIX usando QR Code ou copia e cola abaixo:")
    except:
        await message.answer("💳 Pague via PIX usando copia e cola abaixo:")
    await message.answer(f"```\n{PIX_COPIA_E_COLA}\n```", parse_mode="Markdown")

@router.message(F.text == "📲 Ativar um Aplicativo")
async def ativar(message: types.Message, state: FSMContext):
    await state.set_state(Activate.choosing_app)
    await message.answer("📲 Escolha o aplicativo para ativação:", reply_markup=apps_keyboard())

@router.message(Activate.choosing_app)
async def choose_app(message: types.Message, state: FSMContext):
    app = message.text.strip()
    if app not in PLANOS:
        await message.answer("⚠️ Escolha uma opção válida.")
        return
    await state.update_data(app=app)
    await state.set_state(Activate.entering_mac)
    await message.answer(f"✅ App selecionado: {app}\n\nAgora envie a *Chave MAC* do seu dispositivo:", parse_mode="Markdown")

@router.message(Activate.entering_mac)
async def enter_mac(message: types.Message, state: FSMContext):
    mac = message.text.strip()
    if not is_mac_text(mac):
        await message.answer("⚠️ Formato inválido. Envie novamente a MAC (exemplo: 00:1A:79:12:34:56)")
        return
    await state.update_data(mac=mac)
    await state.set_state(Activate.waiting_receipt)
    await message.answer("✅ MAC recebida!\n\nAgora envie **📷 o comprovante de pagamento** aqui.")

@router.message(Activate.waiting_receipt, F.photo)
async def receber_comprovante(message: types.Message, state: FSMContext):
    data = await state.get_data()
    app = data.get("app")
    mac = data.get("mac")
    file_id = message.photo[-1].file_id

    created_at, expires_at = add_activation(message.from_user.id, message.from_user.username, app, mac, message.message_id)
    await state.clear()

    await message.answer(
        f"🎉 Ativação registrada!\n\n"
        f"📲 App: {app}\n"
        f"🔑 MAC: {mac}\n"
        f"📅 Validade: até {expires_at.strftime('%d/%m/%Y')}\n\n"
        "⏳ Aguarde a confirmação do administrador."
    )

    # Notificar admins
    admin_ids = get_admin_chat_ids()
    for aid in admin_ids:
        try:
            await bot.send_message(aid, f"📢 Novo pedido de ativação!\n\nUsuário: @{message.from_user.username}\nApp: {app}\nMAC: {mac}")
            await bot.forward_message(aid, message.chat.id, message.message_id)
        except Exception as e:
            log.error(f"Erro ao enviar para admin {aid}: {e}")

@router.message(F.text == "👥 Clientes")
async def clientes(message: types.Message):
    if message.from_user.username not in ADMINS:
        await message.answer("⛔ Acesso negado.")
        return
    rows = listar_ativacoes()
    if not rows:
        await message.answer("📂 Nenhum cliente encontrado.")
        return
    text = "👥 Lista de Clientes:\n\n"
    for u, app, mac, criado, expira in rows:
        text += f"👤 @{u or 'sem_username'}\n📲 {app}\n🔑 {mac}\n⏳ Expira: {expira}\n\n"
    await message.answer(text)

# ===================== LEMBRETES =====================
async def verificar_expiracoes():
    while True:
        try:
            con = db()
            cur = con.cursor()
            cur.execute("SELECT user_id, username, expires_at FROM activations")
            rows = cur.fetchall()
            con.close()

            agora = datetime.now()
            admin_ids = get_admin_chat_ids()

            for user_id, username, expires_at in rows:
                if not expires_at:
                    continue
                try:
                    expira = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S")
                except:
                    continue
                dias = (expira - agora).days

                if dias in (7, 1):
                    aviso = "7 dias" if dias == 7 else "AMANHÃ"
                    try:
                        await bot.send_message(user_id, f"⚠️ Seu plano expira em {aviso} ({expira.strftime('%d/%m/%Y')}).")
                    except:
                        pass
                    for aid in admin_ids:
                        try:
                            await bot.send_message(aid, f"📢 Cliente @{username or 'sem_username'} expira em {aviso}.")
                        except:
                            pass

        except Exception as e:
            log.error(f"Erro no verificador de expirações: {e}")

        await asyncio.sleep(86400)

# ===================== RUN =====================
async def main():
    init_db()
    asyncio.create_task(verificar_expiracoes())
    log.info("🤖 Bot iniciado...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
