# bot_iptv_complete.py
# Bot IPTV completo — Aiogram 3.x
# Contém: menu inline, ativação/renovação, PIX (QR gerado se não houver arquivo),
# referrals, ranking, recompensas automáticas, idiomas, suporte humano, /admin, /broadcast, /set_group, export report.

import asyncio
import logging
import os
import sqlite3
import html
from io import BytesIO
from datetime import datetime, timedelta
from typing import Optional, List

import qrcode
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.types import FSInputFile, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest

# ===================== CONFIG - edite antes de rodar =====================
BOT_TOKEN = ""  # (já estava no seu código)
DB_PATH = "bot_iptv.db"

# Admins: por username (sem @) e/ou por id (numérico)
ADMINS: List[str] = ["Hidalgo73", "ativabott"]
ADMIN_IDS: List[int] = []  # ex: [12345678]

PIX_COPIA_E_COLA = (
    "00020101021126580014br.gov.bcb.pix01363c22457a-3a09-44fb-adc5-34f11cd07da35204000053039865802BR5919"
    "INGRID G F DA COSTA6011SALESOPOLIS62070503***630411DF"
)
PIX_QR_PATH = "QR CODE.jpg"  # se existir, será enviado; se não, o bot gera QR

# Recompensa: número de indicações para ganhar recompensa
REWARD_THRESHOLD = 5

# =======================================================================

# Logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bot_iptv")

# Bot
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

# ===================== PLANOS (sua tabela atualizada) =====================
PLANOS = {
    "ABE PLAYER": "R$10 ATIVAÇÃO | R$9 Crédito",
    "ALL PLAYER": "R$10 ATIVAÇÃO | R$9 Crédito",
    "BOB PLAYER": "R$10 ATIVAÇÃO | R$9 Crédito",
    "SMART ONE PRO": "R$10 ATIVAÇÃO | R$9 Crédito",
    "BOB PRO": "R$10 ATIVAÇÃO | R$9 Crédito",
    "BOB PREMIUM": "R$10 ATIVAÇÃO | R$9 Crédito",
    "DUPLEX TV DO IBO": "R$10 ATIVAÇÃO | R$9 Crédito",
    "FAMILY PLAYER": "R$10 ATIVAÇÃO | R$9 Crédito",
    "FLIXNET": "R$10 ATIVAÇÃO | R$9 Crédito",
    "HUSH PLAY": "R$10 ATIVAÇÃO | R$9 Crédito",
    "IBO PLAYER": "R$10 ATIVAÇÃO | R$9 Crédito",
    "IBO STB": "R$10 ATIVAÇÃO | R$9 Crédito",
    "IBOSOL PLAYER": "R$10 ATIVAÇÃO | R$9 Crédito",
    "IBOSS PLAYER": "R$10 ATIVAÇÃO | R$9 Crédito",
    "IBOXX PLAYER": "R$10 ATIVAÇÃO | R$9 Crédito",
    "IBO PRO": "R$12 ATIVAÇÃO | R$10 Crédito",
    "KING4K PLAYER": "R$10 ATIVAÇÃO | R$9 Crédito",
    "KTN PLAYER": "R$10 ATIVAÇÃO | R$9 Crédito",
    "LAZER PLAY": "R$15 ATIVAÇÃO | R$12 Crédito",
    "MAC PLAYER": "R$10 ATIVAÇÃO | R$9 Crédito",
    "SMARTONE": "R$19 ATIVAÇÃO",
    "VIRGINIA": "R$10 ATIVAÇÃO | R$9 Crédito",
    "VU PLAYER PRO": "R$12 ATIVAÇÃO | R$10 Crédito",
    "DUPLEX PLAY": "R$15 ATIVAÇÃO | R$13 Crédito",
    "CLOUDDY": "20$ (Chamar suporte)"
}

# ===================== TEXTOS (simples suporte a idiomas) =====================
# Map básico de textos por linguagem - você pode expandir depois
TEXTS = {
    "pt": {
        "welcome": "👋 Bem-vindo ao *Bot de Ativações*! Escolha uma opção abaixo:",
        "payment_prompt": "💳 Pague via PIX (QR ou copia-e-cola) e envie o comprovante aqui.",
        "comprovante_received": "📩 Comprovante recebido! O suporte vai conferir e ativar sua licença.",
        "activated": "🎉 Seu aplicativo foi ativado com sucesso! ✅",
        "renewed": "♻️ Sua licença foi renovada com sucesso! ✅",
        "reward_msg": "🏆 Parabéns! Você atingiu {n} indicações e ganhou uma recompensa. Entre em contato com o suporte (@{sup}) para resgatar.",
    },
    "en": {
        "welcome": "👋 Welcome to the Activation Bot! Choose an option below:",
        "payment_prompt": "💳 Pay via PIX (QR or copy-and-paste) and send the receipt here.",
        "comprovante_received": "📩 Receipt received! Support will check and activate your license.",
        "activated": "🎉 Your app was activated successfully! ✅",
        "renewed": "♻️ Your license was renewed successfully! ✅",
        "reward_msg": "🏆 Congrats! You reached {n} referrals and earned a reward. Contact support (@{sup}).",
    },
    "es": {
        "welcome": "👋 Bienvenido al Bot de Activaciones! Elige una opción:",
        "payment_prompt": "💳 Paga vía PIX (QR o copia y pega) y envía el comprobante aquí.",
        "comprovante_received": "📩 Comprobante recibido! El soporte verificará y activará tu licencia.",
        "activated": "🎉 Tu aplicación fue activada con éxito! ✅",
        "renewed": "♻️ Tu licencia fue renovada con éxito! ✅",
        "reward_msg": "🏆 Felicidades! Alcanzaste {n} referidos y ganaste una recompensa. Contacta soporte (@{sup}).",
    }
}

# Support username (first admin)
SUPPORT_USERNAME = ADMINS[0] if ADMINS else "ativabott"

# ===================== DB HELPERS =====================
def db():
    # Cada função abre sua conexão (check_same_thread para uso em tasks)
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def ensure_users_schema(con: sqlite3.Connection):
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    exists = cur.fetchone() is not None
    if not exists:
        cur.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                username TEXT,
                invited_by INTEGER,
                lang TEXT DEFAULT 'pt',
                created_at TEXT
            )
        """)
        con.commit()
        return
    # garante colunas mínimas
    cur.execute("PRAGMA table_info(users)")
    cols = [r[1] for r in cur.fetchall()]
    if "lang" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN lang TEXT DEFAULT 'pt'")
        con.commit()
    if "invited_by" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN invited_by INTEGER")
        con.commit()


def init_db():
    con = db()
    cur = con.cursor()
    ensure_users_schema(con)
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
        CREATE TABLE IF NOT EXISTS pending_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            req_type TEXT,
            user_id INTEGER,
            username TEXT,
            app TEXT,
            mac TEXT,
            proof_chat_id INTEGER,
            proof_message_id INTEGER,
            created_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS admin_chats (
            chat_id INTEGER PRIMARY KEY
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin TEXT,
            action TEXT,
            target TEXT,
            created_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT,
            inviter_id INTEGER,
            invited_id INTEGER,
            created_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            inviter_id INTEGER,
            threshold INTEGER,
            granted_at TEXT
        )
    """)
    con.commit()
    con.close()


def add_user(user_id: int, username: Optional[str], invited_by: Optional[int] = None):
    con = db()
    cur = con.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("INSERT OR IGNORE INTO users (user_id, username, invited_by, created_at) VALUES (?, ?, ?, ?)",
                (user_id, username, invited_by, now))
    cur.execute("UPDATE users SET username=? WHERE user_id=?", (username, user_id))
    # if invited_by provided, also update invited_by if not set
    if invited_by:
        cur.execute("UPDATE users SET invited_by=? WHERE user_id=? AND (invited_by IS NULL OR invited_by=0)", (invited_by, user_id))
    con.commit()
    con.close()


def get_user_lang(user_id: int) -> str:
    con = db()
    cur = con.cursor()
    cur.execute("SELECT lang FROM users WHERE user_id=?", (user_id,))
    r = cur.fetchone()
    con.close()
    return r[0] if r and r[0] else "pt"


def set_user_lang(user_id: int, lang: str):
    con = db()
    cur = con.cursor()
    cur.execute("UPDATE users SET lang=? WHERE user_id=?", (lang, user_id))
    con.commit()
    con.close()


def get_all_user_ids() -> List[int]:
    con = db()
    cur = con.cursor()
    cur.execute("SELECT user_id FROM users")
    rows = cur.fetchall()
    con.close()
    return [int(r[0]) for r in rows]


def add_admin_chat_id(chat_id: int):
    con = db()
    cur = con.cursor()
    cur.execute("INSERT OR IGNORE INTO admin_chats (chat_id) VALUES (?)", (int(chat_id),))
    con.commit()
    con.close()


def get_admin_chat_ids() -> List[int]:
    con = db()
    cur = con.cursor()
    cur.execute("SELECT chat_id FROM admin_chats")
    ids = [int(r[0]) for r in cur.fetchall()]
    con.close()
    return ids


def add_activation(user_id: int, username: Optional[str], app: str, mac: str, file_message_id: Optional[int]):
    con = db()
    cur = con.cursor()
    created_at = datetime.now()
    expires_at = created_at + timedelta(days=365)
    cur.execute("INSERT INTO activations (user_id, username, app, mac, file_message_id, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, username, app, mac, file_message_id, created_at.strftime("%Y-%m-%d %H:%M:%S"), expires_at.strftime("%Y-%m-%d %H:%M:%S")))
    con.commit()
    con.close()
    return created_at, expires_at


def renew_activation_by_mac(mac: str) -> Optional[datetime]:
    con = db()
    cur = con.cursor()
    cur.execute("SELECT id FROM activations WHERE mac=? ORDER BY id DESC LIMIT 1", (mac,))
    row = cur.fetchone()
    if not row:
        con.close()
        return None
    new_exp = datetime.now() + timedelta(days=365)
    cur.execute("UPDATE activations SET expires_at=? WHERE id=?", (new_exp.strftime("%Y-%m-%d %H:%M:%S"), row[0]))
    con.commit()
    con.close()
    return new_exp


def listar_ativacoes():
    con = db()
    cur = con.cursor()
    cur.execute("SELECT username, app, mac, created_at, expires_at FROM activations ORDER BY expires_at ASC")
    rows = cur.fetchall()
    con.close()
    return rows


def log_action(admin: str, action: str, target: str):
    con = db()
    cur = con.cursor()
    cur.execute("INSERT INTO logs (admin, action, target, created_at) VALUES (?, ?, ?, ?)",
                (admin, action, target, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    con.commit()
    con.close()


def save_referral(code: str, inviter_id: int, invited_id: int):
    con = db()
    cur = con.cursor()
    cur.execute("INSERT INTO referrals (code, inviter_id, invited_id, created_at) VALUES (?, ?, ?, ?)",
                (code, inviter_id, invited_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    con.commit()
    # checa recompensa automática
    cur.execute("SELECT COUNT(*) FROM referrals WHERE inviter_id=?", (inviter_id,))
    count = cur.fetchone()[0]
    # verifica se já ganhou recompensa
    cur.execute("SELECT id FROM rewards WHERE inviter_id=? AND threshold=?", (inviter_id, REWARD_THRESHOLD))
    already = cur.fetchone()
    if count >= REWARD_THRESHOLD and not already:
        cur.execute("INSERT INTO rewards (inviter_id, threshold, granted_at) VALUES (?, ?, ?)",
                    (inviter_id, REWARD_THRESHOLD, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        con.commit()
        # notifica inviter
        try:
            msg = TEXTS.get(get_user_lang(inviter_id), TEXTS["pt"])["reward_msg"].format(n=REWARD_THRESHOLD, sup=SUPPORT_USERNAME)
            bot.send_message(inviter_id, html.escape(msg))
        except Exception:
            log.warning("Não foi possível notificar o usuário sobre recompensa.")
    con.close()


# ===================== FSM (Estados) =====================
class Activate(StatesGroup):
    choosing_app = State()
    entering_mac = State()
    waiting_receipt = State()


class Renew(StatesGroup):
    choosing_app = State()
    entering_mac = State()
    waiting_receipt = State()


class BroadcastStates(StatesGroup):
    waiting_message = State()


# ===================== UTILIDADES =====================
def admin_only(username: Optional[str] = None, user_id: Optional[int] = None) -> bool:
    if user_id and user_id in ADMIN_IDS:
        return True
    if username and username in ADMINS:
        return True
    return False


def escape(s: Optional[str]) -> str:
    return html.escape(s or "")


async def send_safe_message(chat_id: int, text: str, reply_markup: Optional[types.InlineKeyboardMarkup] = None):
    """Tenta enviar com parse_mode HTML; se falhar (bad entities), envia versão escapada."""
    try:
        return await bot.send_message(chat_id, text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        try:
            return await bot.send_message(chat_id, escape(text))
        except Exception:
            log.exception("Falha ao enviar mensagem segura.")
            return None


# ===================== TECLADOS / MENUS (INLINE) =====================
def main_menu_inline() -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📲 Ativar", callback_data="menu_activate"),
         InlineKeyboardButton(text="🔁 Renovar", callback_data="menu_renew")],
        [InlineKeyboardButton(text="💳 PIX", callback_data="menu_pix"),
         InlineKeyboardButton(text="💰 Valores", callback_data="menu_prices")],
        [InlineKeyboardButton(text="📢 Meu Link", callback_data="menu_ref"),
         InlineKeyboardButton(text="🆘 Suporte", callback_data="menu_support")],
        [InlineKeyboardButton(text="🏆 Ranking", callback_data="menu_ranking"),
         InlineKeyboardButton(text="🌐 Idioma", callback_data="menu_lang")]
    ])
    return kb


def apps_reply_keyboard() -> types.ReplyKeyboardMarkup:
    rows, row = [], []
    for i, app in enumerate(PLANOS.keys(), 1):
        row.append(types.KeyboardButton(text=app))
        if i % 2 == 0:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([types.KeyboardButton(text="⬅️ Voltar ao Menu")])
    return types.ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


# ===================== PIX / QR =====================
async def send_pix_info(chat_id: int):
    """Envia QR (arquivo se existir) e copia-e-cola de forma resiliente."""
    # tenta enviar arquivo QR se existir
    try:
        if PIX_QR_PATH and os.path.exists(PIX_QR_PATH):
            await bot.send_photo(chat_id, FSInputFile(PIX_QR_PATH), caption="💳 Pague via PIX usando o QR abaixo ou a chave copia-e-cola.")
        else:
            qr_img = qrcode.make(PIX_COPIA_E_COLA)
            bio = BytesIO()
            qr_img.save(bio, format="PNG")
            bio.seek(0)
            await bot.send_photo(chat_id, FSInputFile(bio, filename="pix.png"), caption="💳 QR gerado automaticamente.")
    except Exception:
        log.exception("Falha ao enviar/gerar QR.")

    # envia copia-e-cola (em code block -> usando HTML <pre>)
    try:
        await bot.send_message(chat_id, f"<pre>{html.escape(PIX_COPIA_E_COLA)}</pre>")
    except Exception:
        await bot.send_message(chat_id, f"PIX (copia-e-cola): {PIX_COPIA_E_COLA}")


# ===================== NOTIFY ADM GROUP =====================
async def notify_admin_group(text: str, forward_from_chat_id: Optional[int] = None, forward_message_id: Optional[int] = None, inline_kb: Optional[InlineKeyboardMarkup] = None):
    admin_ids = get_admin_chat_ids()
    if not admin_ids:
        log.warning("Nenhum grupo de ADM cadastrado. Use /set_group dentro do grupo de admins.")
        return
    for gid in admin_ids:
        try:
            await bot.send_message(gid, text, reply_markup=inline_kb)
            if forward_from_chat_id and forward_message_id:
                try:
                    await bot.forward_message(gid, forward_from_chat_id, forward_message_id)
                except Exception:
                    log.warning("Falha ao encaminhar comprovante para grupo ADM.")
        except Exception:
            log.exception(f"Erro ao notificar grupo ADM {gid}.")


# ===================== START / CALLBACKS / HANDLERS =====================
@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    # limpa estado
    try:
        await state.clear()
    except Exception:
        pass

    args = ""
    if message.text:
        parts = message.text.split(maxsplit=1)
        if len(parts) > 1:
            args = parts[1].strip()

    inviter_id = None
    # referral
    if args.startswith("ref_"):
        code = args.replace("ref_", "", 1)
        try:
            inviter_id = int(code)
        except Exception:
            inviter_id = None
        if inviter_id:
            save_referral(code=args, inviter_id=inviter_id, invited_id=message.from_user.id)

    # caso link venha com plano (ex: ?start=PLANO_NAME)
    if args and not args.startswith("ref_"):
        # trata plano (underscores -> espaços)
        plano = args.replace("_", " ")
        add_user(message.from_user.id, message.from_user.username, invited_by=inviter_id)
        await message.answer(f"👋 Você escolheu o plano: <b>{html.escape(plano)}</b>\n\nEnvie agora a chave MAC para iniciar.",
                             reply_markup=apps_reply_keyboard())
        await state.set_state(Activate.entering_mac)
        await state.update_data(app=plano)
        return

    # registra usuário
    add_user(message.from_user.id, message.from_user.username, invited_by=inviter_id)

    # resposta inicial com menu inline
    lang = get_user_lang(message.from_user.id)
    txt = TEXTS.get(lang, TEXTS["pt"])["welcome"]
    await send_safe_message(message.chat.id, txt, reply_markup=main_menu_inline())


# ---- Callback do menu inline ----
@router.callback_query(F.data == "menu_activate")
async def menu_activate_cb(q: types.CallbackQuery, state: FSMContext):
    await q.answer()
    await state.set_state(Activate.choosing_app)
    await bot.send_message(q.from_user.id, "📲 Escolha o aplicativo para ativação:", reply_markup=apps_reply_keyboard())


@router.callback_query(F.data == "menu_renew")
async def menu_renew_cb(q: types.CallbackQuery, state: FSMContext):
    await q.answer()
    await state.set_state(Renew.choosing_app)
    await bot.send_message(q.from_user.id, "🔁 Escolha o aplicativo para renovação:", reply_markup=apps_reply_keyboard())


@router.callback_query(F.data == "menu_pix")
async def menu_pix_cb(q: types.CallbackQuery):
    await q.answer()
    await send_pix_info(q.from_user.id)


@router.callback_query(F.data == "menu_prices")
async def menu_prices_cb(q: types.CallbackQuery):
    await q.answer()
    await bot.send_message(q.from_user.id, prices_text())


@router.callback_query(F.data == "menu_ref")
async def menu_ref_cb(q: types.CallbackQuery):
    await q.answer()
    me = await bot.get_me()
    link = f"https://t.me/{me.username}?start=ref_{q.from_user.id}"
    # conta indicados
    con = db(); cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM referrals WHERE inviter_id=?", (q.from_user.id,))
    total = cur.fetchone()[0] if cur else 0
    con.close()
    await bot.send_message(q.from_user.id, f"📢 Seu link de indicação:\n{link}\n\nVocê já indicou: {total} pessoa(s).")


@router.callback_query(F.data == "menu_support")
async def menu_support_cb(q: types.CallbackQuery):
    await q.answer()
    # botão para abrir chat com suporte (abre o perfil do primeiro admin)
    support = SUPPORT_USERNAME
    if support:
        await bot.send_message(q.from_user.id, f"🆘 Fale com o suporte: @{support}")
    else:
        await bot.send_message(q.from_user.id, "🆘 Suporte indisponível no momento.")


@router.callback_query(F.data == "menu_ranking")
async def menu_ranking_cb(q: types.CallbackQuery):
    await q.answer()
    # gera ranking geral por número de indicações
    con = db(); cur = con.cursor()
    cur.execute("SELECT inviter_id, COUNT(*) as cnt FROM referrals GROUP BY inviter_id ORDER BY cnt DESC LIMIT 10")
    rows = cur.fetchall()
    con.close()
    if not rows:
        await bot.send_message(q.from_user.id, "🏆 Ranking vazio — ninguém indicou ainda.")
        return
    text = "🏆 Ranking (top 10 indicados):\n\n"
    rank = 1
    for inviter_id, cnt in rows:
        # pega username do inviter
        con = db(); cur = con.cursor()
        cur.execute("SELECT username FROM users WHERE user_id=?", (inviter_id,))
        r = cur.fetchone(); con.close()
        uname = r[0] if r and r[0] else f"ID:{inviter_id}"
        text += f"{rank}. @{html.escape(uname)} — {cnt} indicação(ões)\n"
        rank += 1
    await bot.send_message(q.from_user.id, text)


@router.callback_query(F.data == "menu_lang")
async def menu_lang_cb(q: types.CallbackQuery):
    await q.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Português 🇧🇷", callback_data="setlang_pt"),
         InlineKeyboardButton(text="English 🇺🇸", callback_data="setlang_en")],
        [InlineKeyboardButton(text="Español 🇪🇸", callback_data="setlang_es")]
    ])
    await bot.send_message(q.from_user.id, "🌐 Escolha o idioma / Choose language / Elige idioma:", reply_markup=kb)


@router.callback_query(F.data.startswith("setlang_"))
async def setlang_cb(q: types.CallbackQuery):
    await q.answer()
    lang = q.data.split("_", 1)[1]
    if lang not in ("pt", "en", "es"):
        lang = "pt"
    set_user_lang(q.from_user.id, lang)
    await bot.send_message(q.from_user.id, f"Idioma definido para: {lang}")


# ===================== mensagens de menu em texto =====================
def prices_text() -> str:
    lines = ["💰 Tabela de Valores\n"]
    for app, preco in PLANOS.items():
        lines.append(f"🔹 {app}\n{preco}\n")
    return "\n".join(lines)


def is_mac_text(txt: str) -> bool:
    import re
    t = (txt or "").strip()
    return bool(re.match(r"^([0-9A-Fa-f]{2}([-:])){5}[0-9A-Fa-f]{2}$", t)) or len(t.replace(":", "").replace("-", "")) >= 12


# ===================== ATIVAÇÃO / RENOVAÇÃO (fluxos) =====================
@router.message(Activate.choosing_app)
async def choose_app(message: types.Message, state: FSMContext):
    app = (message.text or "").strip()
    if app not in PLANOS:
        await message.reply("⚠️ Escolha uma opção válida da lista.")
        return
    await state.update_data(app=app)
    await state.set_state(Activate.entering_mac)
    await message.reply(f"✅ App selecionado: <code>{escape(app)}</code>\n\nAgora envie a <code>Chave MAC</code> do seu dispositivo (ex: <code>00:1A:79:12:34:56</code>).")


@router.message(Activate.entering_mac)
async def enter_mac(message: types.Message, state: FSMContext):
    mac = (message.text or "").strip()
    if not is_mac_text(mac):
        await message.reply("⚠️ Formato inválido. Envie novamente a MAC (exemplo: 00:1A:79:12:34:56).")
        return
    await state.update_data(mac=mac)
    await state.set_state(Activate.waiting_receipt)
    lang = get_user_lang(message.from_user.id)
    await bot.send_message(message.chat.id, TEXTS.get(lang, TEXTS["pt"])["payment_prompt"])
    await send_pix_info(message.chat.id)


@router.message(Activate.waiting_receipt, F.photo)
async def receber_comprovante_ativacao(message: types.Message, state: FSMContext):
    data = await state.get_data()
    app = data.get("app")
    mac = data.get("mac")
    con = db(); cur = con.cursor()
    cur.execute("INSERT INTO pending_requests (req_type, user_id, username, app, mac, proof_chat_id, proof_message_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("new", message.from_user.id, message.from_user.username, app, mac, message.chat.id, message.message_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    pending_id = cur.lastrowid
    con.commit(); con.close()
    lang = get_user_lang(message.from_user.id)
    await bot.send_message(message.chat.id, TEXTS.get(lang, TEXTS["pt"])["comprovante_received"])
    await state.clear()
    await bot.send_message(message.chat.id, "⬅️ Voltar ao menu principal", reply_markup=main_menu_inline())

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Ativar", callback_data=f"approve:{pending_id}"),
         InlineKeyboardButton(text="❌ Reprovar", callback_data=f"reject:{pending_id}")]
    ])
    await notify_admin_group(
        text=(f"📢 <b>Novo pedido de ATIVAÇÃO</b>\n\nUsuário: @{escape(message.from_user.username or 'sem_username')}\nApp: {escape(app)}\nMAC: <code>{escape(mac)}</code>\nID pendente: {pending_id}"),
        forward_from_chat_id=message.chat.id,
        forward_message_id=message.message_id,
        inline_kb=kb
    )


@router.message(Renew.choosing_app)
async def renew_choose_app(message: types.Message, state: FSMContext):
    app = (message.text or "").strip()
    if app not in PLANOS:
        await message.reply("⚠️ Escolha uma opção válida da lista.")
        return
    await state.update_data(app=app)
    await state.set_state(Renew.entering_mac)
    await message.reply("Agora envie a Chave MAC que deseja renovar:")


@router.message(Renew.entering_mac)
async def renew_enter_mac(message: types.Message, state: FSMContext):
    mac = (message.text or "").strip()
    if not is_mac_text(mac):
        await message.reply("⚠️ MAC inválida. Exemplo: 00:1A:79:12:34:56.")
        return
    await state.update_data(mac=mac)
    await state.set_state(Renew.waiting_receipt)
    lang = get_user_lang(message.from_user.id)
    await bot.send_message(message.chat.id, TEXTS.get(lang, TEXTS["pt"])["payment_prompt"])
    await send_pix_info(message.chat.id)


@router.message(Renew.waiting_receipt, F.photo)
async def receber_comprovante_renovacao(message: types.Message, state: FSMContext):
    data = await state.get_data()
    app = data.get("app")
    mac = data.get("mac")
    con = db(); cur = con.cursor()
    cur.execute("INSERT INTO pending_requests (req_type, user_id, username, app, mac, proof_chat_id, proof_message_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("renew", message.from_user.id, message.from_user.username, app, mac, message.chat.id, message.message_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    pending_id = cur.lastrowid
    con.commit(); con.close()
    lang = get_user_lang(message.from_user.id)
    await bot.send_message(message.chat.id, TEXTS.get(lang, TEXTS["pt"])["comprovante_received"])
    await state.clear()
    await bot.send_message(message.chat.id, "⬅️ Voltar ao menu principal", reply_markup=main_menu_inline())

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="♻️ Renovar", callback_data=f"renew:{pending_id}"),
         InlineKeyboardButton(text="❌ Reprovar", callback_data=f"reject:{pending_id}")]
    ])
    await notify_admin_group(
        text=(f"📢 <b>Pedido de RENOVAÇÃO</b>\n\nUsuário: @{escape(message.from_user.username or 'sem_username')}\nApp: {escape(app)}\nMAC: <code>{escape(mac)}</code>\nID pendente: {pending_id}"),
        forward_from_chat_id=message.chat.id,
        forward_message_id=message.message_id,
        inline_kb=kb
    )


# ===================== CALLBACKS PARA APROVAÇÃO / REJEIÇÃO =====================
@router.callback_query(F.data.startswith(("approve:", "renew:", "reject:")))
async def admin_actions(callback: types.CallbackQuery):
    await callback.answer()
    username = callback.from_user.username
    user_id = callback.from_user.id
    if not admin_only(username, user_id):
        await callback.answer("Apenas ADMs podem usar.", show_alert=True)
        return

    action, pid_str = callback.data.split(":", 1)
    try:
        pending_id = int(pid_str)
    except:
        await callback.answer("ID inválido.", show_alert=True)
        return

    con = db()
    cur = con.cursor()
    cur.execute("SELECT req_type, user_id, username, app, mac, proof_chat_id, proof_message_id FROM pending_requests WHERE id=?", (pending_id,))
    row = cur.fetchone()
    if not row:
        con.close()
        await callback.answer("Pedido não encontrado ou já processado.", show_alert=True)
        return

    req_type, tgt_user_id, username_u, app, mac, proof_chat_id, proof_message_id = row

    if action == "reject":
        cur.execute("DELETE FROM pending_requests WHERE id=?", (pending_id,))
        con.commit()
        con.close()
        try:
            await callback.message.edit_text(f"❌ Pedido #{pending_id} REPROVADO por @{escape(callback.from_user.username)}.")
        except Exception:
            pass
        log_action(callback.from_user.username, "reject", f"{username_u}|{app}|{mac}")
        try:
            await bot.send_message(tgt_user_id, "❌ Seu pedido foi reprovado. Entre em contato com o suporte.")
        except:
            pass
        return

    if action == "approve" or req_type == "new":
        created_at, expires_at = add_activation(tgt_user_id, username_u, app, mac, proof_message_id)
        cur.execute("DELETE FROM pending_requests WHERE id=?", (pending_id,))
        con.commit()
        con.close()
        try:
            await callback.message.edit_text(
                f"✅ Pedido #{pending_id} ATIVADO por @{escape(callback.from_user.username)}.\n"
                f"Usuário: @{escape(username_u or 'sem_username')}\nApp: {escape(app)}\nMAC: <code>{escape(mac)}</code>\nVálido até: {expires_at.strftime('%d/%m/%Y')}"
            )
        except Exception:
            pass
        log_action(callback.from_user.username, "approve", f"{username_u}|{app}|{mac}")
        try:
            await bot.send_message(tgt_user_id, TEXTS.get(get_user_lang(tgt_user_id), TEXTS["pt"])["activated"])
        except:
            pass
        return

    if action == "renew":
        new_exp = renew_activation_by_mac(mac)
        if new_exp is None:
            _, new_exp = add_activation(tgt_user_id, username_u, app, mac, proof_message_id)
        cur.execute("DELETE FROM pending_requests WHERE id=?", (pending_id,))
        con.commit()
        con.close()
        try:
            await callback.message.edit_text(
                f"♻️ Pedido #{pending_id} RENOVADO por @{escape(callback.from_user.username)}.\n"
                f"Usuário: @{escape(username_u or 'sem_username')}\nApp: {escape(app)}\nMAC: <code>{escape(mac)}</code>\nNovo vencimento: {new_exp.strftime('%d/%m/%Y')}"
            )
        except Exception:
            pass
        log_action(callback.from_user.username, "renew", f"{username_u}|{app}|{mac}")
        try:
            await bot.send_message(tgt_user_id, TEXTS.get(get_user_lang(tgt_user_id), TEXTS["pt"])["renewed"])
        except:
            pass
        return


# ===================== /set_group (registrar grupo ADM) =====================
@router.message(Command("set_group"))
async def set_group(message: types.Message):
    if message.chat.type not in ("group", "supergroup"):
        await message.reply("Este comando deve ser enviado dentro do grupo de administradores.")
        return
    if not admin_only(message.from_user.username, message.from_user.id):
        await message.reply("Apenas administradores podem registrar o grupo.")
        return
    add_admin_chat_id(message.chat.id)
    await message.reply("✅ Grupo registrado! O bot enviará pedidos de ativação/renovação aqui.")


# ===================== LISTAR CLIENTES (ADM) =====================
@router.message(F.text == "👥 Clientes")
async def clientes(message: types.Message):
    if not admin_only(message.from_user.username, message.from_user.id):
        await message.reply("⛔ Acesso negado.")
        return
    rows = listar_ativacoes()
    if not rows:
        await message.reply("📂 Nenhum cliente encontrado.")
        return
    text = "👥 Lista de Clientes:\n\n"
    for u, app, mac, criado, expira in rows:
        text += f"👤 @{escape(u or 'sem_username')}\n📲 {escape(app)}\n🔑 {escape(mac)}\n⏳ Expira: {expira}\n\n"
    await message.reply(text)


# ===================== EXPORTAR RELATÓRIO (ADM) =====================
@router.message(Command("relatorio"))
async def export_report(message: types.Message):
    if not admin_only(message.from_user.username, message.from_user.id):
        await message.reply("⛔ Acesso negado.")
        return
    con = db(); cur = con.cursor()
    cur.execute("SELECT id, user_id, username, app, mac, created_at, expires_at FROM activations")
    rows = cur.fetchall(); con.close()
    if not rows:
        await message.reply("Nenhuma ativação para exportar.")
        return
    import csv, time
    fname = f"relatorio_ativacoes_{int(time.time())}.csv"
    with open(fname, "w", newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(["id", "user_id", "username", "app", "mac", "created_at", "expires_at"])
        writer.writerows(rows)
    await message.reply_document(FSInputFile(fname))
    try:
        os.remove(fname)
    except:
        pass


# ===================== /admin e /broadcast =====================
@router.message(Command("admin"))
async def admin_panel(message: types.Message):
    if not admin_only(message.from_user.username, message.from_user.id):
        await message.reply("⛔ Você não é administrador.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📈 Ranking", callback_data="menu_ranking"),
         InlineKeyboardButton(text="📋 Relatório", callback_data="admin_relatorio")],
        [InlineKeyboardButton(text="⚙️ Registrar grupo", callback_data="admin_set_group")]
    ])
    await message.reply("⚙️ Painel ADM — escolha uma opção:", reply_markup=kb)


@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_cb(q: types.CallbackQuery, state: FSMContext):
    await q.answer()
    if not admin_only(q.from_user.username, q.from_user.id):
        await q.message.answer("⛔ Apenas ADMs.")
        return
    await q.message.answer("📢 Envie a mensagem que deseja enviar para todos (texto/mídia).")
    await state.set_state(BroadcastStates.waiting_message)


@router.message(Command("broadcast"))
async def start_broadcast_cmd(message: types.Message, state: FSMContext):
    if not admin_only(message.from_user.username, message.from_user.id):
        await message.reply("⛔ Apenas ADMs podem usar este comando.")
        return
    await message.reply("📢 Envie a mensagem (texto/mídia) que deseja enviar para todos os clientes.")
    await state.set_state(BroadcastStates.waiting_message)


@router.message(BroadcastStates.waiting_message)
async def do_broadcast(message: types.Message, state: FSMContext):
    if not admin_only(message.from_user.username, message.from_user.id):
        await message.reply("⛔ Apenas ADMs podem enviar broadcast.")
        await state.clear()
        return

    users = get_all_user_ids()
    enviados, falhou = 0, 0
    for uid in users:
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
            enviados += 1
            await asyncio.sleep(0.03)
        except Exception:
            try:
                if message.text:
                    await bot.send_message(uid, message.text)
                    enviados += 1
                else:
                    falhou += 1
            except Exception:
                falhou += 1

    await message.reply(f"✅ Broadcast finalizado. Enviados: {enviados} | Falharam: {falhou}")
    log_action(message.from_user.username or str(message.from_user.id), "broadcast", f"enviados:{enviados},falharam:{falhou}")
    await state.clear()


# ===================== VOLTAR AO MENU =====================
@router.message(F.text.in_({"⬅️ Voltar ao Menu", "⬅️ Voltar", "Voltar", "Menu", "🔙 Voltar ao menu"}))
async def voltar_menu(message: types.Message, state: FSMContext):
    try:
        await state.clear()
    except:
        pass
    await message.answer("🔙 Você voltou ao menu principal.", reply_markup=main_menu_inline())


# ===================== LEMBRETES DIÁRIOS (task) =====================
async def verificar_expiracoes():
    while True:
        try:
            con = db(); cur = con.cursor()
            cur.execute("SELECT user_id, username, expires_at FROM activations")
            rows = cur.fetchall(); con.close()
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
                        await bot.send_message(user_id, f"⚠️ Sua licença expira em {aviso} ({expira.strftime('%d/%m/%Y')}).")
                    except:
                        pass
                    for gid in admin_ids:
                        try:
                            await bot.send_message(gid, f"📢 Cliente @{username or 'sem_username'} expira em {aviso}.")
                        except:
                            pass
        except Exception:
            log.exception("Erro no verificador de expirações.")
        await asyncio.sleep(86400)


# ===================== START BOT =====================
async def main():
    init_db()
    asyncio.create_task(verificar_expiracoes())
    log.info("🤖 Bot iniciado...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

