import logging
import sqlite3
import re
from datetime import datetime, timedelta  # ရက်စွဲတွက်ချက်ရန် library များ
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler
)

# --- CONFIGURATION ---
BOT_TOKEN = "8836816469:AAF4QdxvkK1Z8UtqtA42ThJtvuLeF5OB0uk"
ADMIN_ID = 5568078975
OWNER_USER = "@NeedMyHelpp"

KPAY_NUMBER = "09970276547"
KPAY_NAME = "Wai Yan Naing"

# 🌟 Cloud Volume Disk ၏ လမ်းကြောင်းအသစ်အား ဤနေရာတွင် တရားသေ သတ်မှတ်လိုက်သည် 🌟
DB_PATH = "/app/data/vpn_store.db"

# --- CONVERSATION STATES ---
CHOOSING_SERVER = 0
ENTERING_TXN = 1
ENTERING_NAME = 2
ADMIN_GET_ID = 3
ADMIN_GET_CONFIG = 4
ADMIN_SELECT_PRICE_PROD = 5
ADMIN_GET_NEW_PRICE = 6
ADMIN_EDIT_ID = 7
ADMIN_EDIT_CONFIG = 8
ADMIN_ADD_KEY_TYPE = 9
ADMIN_ADD_KEY_INPUT = 10
ADMIN_MANUAL_ID = 11
ADMIN_MANUAL_KEY = 12
ADMIN_VIEW_KEY_TYPE = 13
ADMIN_DEL_KEY_INPUT = 14

# ရိုးရိုး Request log များကို ဖျောက်ထားပြီး အရေးကြီး Warning/Error သာ ပြမည့်ပုံစံသို့ ပြောင်းထားသည်
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.WARNING)
logger = logging.getLogger(__name__)

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect(DB_PATH)  # ပြောင်းလဲထားသော လမ်းကြောင်းအား သုံးစွဲခြင်း
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id TEXT PRIMARY KEY, name TEXT, price INTEGER, stock_status TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT,
            product_id TEXT, txn_last_5 TEXT, sender_name TEXT, status TEXT DEFAULT 'PENDING'
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vpn_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id TEXT,
            vpn_key TEXT,
            is_used INTEGER DEFAULT 0
        )
    ''')
    cursor.execute("INSERT OR IGNORE INTO products VALUES ('sg_100gb', '🇸🇬 Singapore Premium (100GB)', 3000, 'IN_STOCK')")
    cursor.execute("INSERT OR IGNORE INTO products VALUES ('us_100gb', '🇺🇸 United States High-Speed (100GB)', 3000, 'IN_STOCK')")
    conn.commit()
    conn.close()

def get_products():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price, stock_status FROM products")
    data = cursor.fetchall()
    conn.close()
    return data

def get_available_key_count(product_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM vpn_keys WHERE LOWER(product_id) = ? AND is_used = 0", (product_id.lower(),))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def insert_bulk_keys(product_id, keys_list):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    for key in keys_list:
        if key.strip():
            cursor.execute("INSERT INTO vpn_keys (product_id, vpn_key) VALUES (?, ?)", (product_id.lower(), key.strip()))
    conn.commit()
    conn.close()

def pull_single_unused_key(product_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, vpn_key FROM vpn_keys WHERE LOWER(product_id) = ? AND is_used = 0 LIMIT 1", (product_id.lower(),))
    row = cursor.fetchone()
    if row:
        key_id, vpn_key = row
        cursor.execute("UPDATE vpn_keys SET is_used = 1 WHERE id = ?", (key_id,))
        conn.commit()
        conn.close()
        return vpn_key
    conn.close()
    return None

def get_all_unused_keys_db(product_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, vpn_key FROM vpn_keys WHERE LOWER(product_id) = ? AND is_used = 0", (product_id.lower(),))
    rows = cursor.fetchall()
    conn.close()
    return rows

def delete_key_by_id(key_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM vpn_keys WHERE id = ?", (key_id,))
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    return success

def update_stock_db(product_id, status):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE products SET stock_status = ? WHERE LOWER(id) = ?", (status, product_id.lower()))
    conn.commit()
    conn.close()

def update_price_db(product_id, price):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE products SET price = ? WHERE LOWER(id) = ?", (price, product_id.lower()))
    conn.commit()
    conn.close()

def log_transaction(user_id, username, product_id, txn, name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO transactions (user_id, username, product_id, txn_last_5, sender_name) VALUES (?, ?, ?, ?, ?)",
        (user_id, username, product_id, txn, name)
    )
    tx_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return tx_id

# --- USER SIDE HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    welcome_text = (
        "👑 <b>WELCOME TO PREMIUM VPN METRO</b> 👑\n"
        "⚡ <i>Fastest • Most Reliable • No Log Policy</i> ⚡\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "လိုင်းကျပ်ခြင်း၊ Ping တက်ခြင်းများအတွက် လုံးဝစိတ်ပူစရာမလိုဘဲ Gaming, Streaming နှင့် Browsing များကို "
        "အရှိန်အဟုန်မြှင့်တင်ပေးမည့် <b>High-Class Premium VPN Server</b> များကို အောက်တွင် စတင်ဝယ်ယူနိုင်ပါပြီခင်ဗျာ။\n\n"
        "👇 ဝယ်ယူရန် အောက်ပါ <b>START SHOPPING</b> ခလုတ်ကို နှိပ်ပါ။"
    )
    keyboard = [
        [InlineKeyboardButton("🛒 ✨ START SHOPPING (ဝယ်ယူရန်) ✨ 🛒", callback_data="buy_vpn")],
        [InlineKeyboardButton("💬 Feedback & Review", url=f"https://t.me/{OWNER_USER.replace('@','')}")],
        [InlineKeyboardButton("📞 Contact Owner", url=f"https://t.me/{OWNER_USER.replace('@','')}")]
    ]
    if update.effective_user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("⚙️ Admin Dashboard Mode", callback_data="admin_panel")])
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await update.callback_query.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode="HTML")
    return ConversationHandler.END

async def buy_vpn_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    products = get_products()
    keyboard = []
    text = "💎 <b>PREMIUM VPN SERVER LIST</b> 💎\n━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    for pid, name, price, stock in products:
        badge = "🔥 [🔥 POPULAR]" if "singapore" in name.lower() else "💎 [💎 BEST VALUE]"
        if stock == "IN_STOCK":
            status_tag = "🟢 <code>[ ██████████ ] IN STOCK</code>"
            btn_text = f"💳 ဝယ်ယူမည် | {price} Ks"
        else:
            status_tag = "🔴 <code>[ ░░░░░░░░░░ ] OUT OF STOCK</code>"
            btn_text = "❌ ကုန်သွားပါပြီ (Out of Stock)"
            
        text += f"{badge} <b>{name}</b>\n💰 <b>Price:</b> <b>{price} Ks</b>\n📊 <b>Stock Status:</b> {status_tag}\n\n─────────────────────\n"
        keyboard.append([InlineKeyboardButton(f"{name} - {btn_text}", callback_data=f"select_{pid}")])
        
    keyboard.append([InlineKeyboardButton("⬅️ Back to Main Menu", callback_data="main_menu")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return CHOOSING_SERVER

async def handle_server_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_id = query.data.replace("select_", "")
    products = {p[0].lower(): {"name": p[1], "price": p[2], "stock": p[3]} for p in get_products()}
    selected = products.get(product_id.lower())
    
    if not selected or selected["stock"] == "OUT_OF_STOCK":
        await query.answer("⚠️ ဤ Package သည် ကုန်သွားပါပြီ။", show_alert=True)
        return CHOOSING_SERVER

    context.user_data["selected_product_id"] = product_id
    context.user_data["selected_product_name"] = selected["name"]
    context.user_data["selected_product_price"] = selected["price"]
    
    payment_text = (
        "💳 <b>PREMIUM DIGITAL CHECKOUT</b> 💳\n━━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Selected Product:</b> {selected['name']}\n"
        f"💵 <b>Net Amount:</b> <code>{selected['price']} Ks</code>\n━━━━━━━━━━━━━━━━━━━━━\n\n"
        "👇 <b>အောက်ပါ Kpay အကောင့်သို့ ငွေလွဲပေးပါရန်:</b>\n"
        f"📱 Kpay Number: <code>{KPAY_NUMBER}</code> (နှိပ်ပြီး Copy ကူးပါ)\n"
        f"👤 Kpay Name: <b>{KPAY_NAME}</b>\n\n"
        "📌 <b>ငွေလွဲပြီးပါက ကျေးဇူးပြု၍:</b>\n"
        "ငွေလွဲပြေစာပေါ်ရှိ <b>Transaction ID နောက်ဆုံး ဂဏန်း ၅ လုံး</b> ကို အောက်တွင် ရိုက်ထည့်ပေးပါ။"
    )
    keyboard = [[InlineKeyboardButton("❌ Cancel Order", callback_data="buy_vpn")]]
    await query.edit_message_text(payment_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return ENTERING_TXN

async def process_txn_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not re.match(r"^\d{5}$", text):
        await update.message.reply_text(f"❌ <b>အချက်အလက် မှားယွင်းနေပါသည်။</b>\nဂဏန်း ၅ လုံး တိကျစွာ ရိုက်ထည့်ပေးပါ။\n📞 Contact Owner: {OWNER_USER}", parse_mode="HTML")
        return ENTERING_TXN
    context.user_data["txn_last_5"] = text
    await update.message.reply_text("👤 ကျေးဇူးပြု၍ Ngwe Lwe Name (Sender Name) ကို ရိုက်ထည့်ပေးပါ။")
    return ENTERING_NAME

async def process_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender_name = update.message.text.strip()
    user = update.effective_user
    pid = context.user_data["selected_product_id"]
    p_name = context.user_data["selected_product_name"]
    txn = context.user_data["txn_last_5"]
    
    username_clean = f"@{user.username}" if user.username else "No_Username"
    tx_id = log_transaction(user.id, username_clean, pid, txn, sender_name)
    
    customer_confirmation = (
        "🎉 <b>ORDER RECORDED SUCCESSFULLY!</b> 🎉\n━━━━━━━━━━━━━━━━━━━━━\n"
        "သင့်အချက်အလက်များကို သိမ်းဆည်းပြီးပါပြီ။ Admin မှ ငွေလွဲကို စစ်ဆေးပြီးလျှင် အတည်ပြုချက်စာနှင့်အတူ VPN Key ပို့ပေးပါလိမ့်မည်။\n\n"
        f"🧾 <b>Receipt ID:</b> <code>#{tx_id}</code>\n📦 <b>Server Purchased:</b> {p_name}\n"
        f"🔢 <b>Txn Code:</b> <code>{txn}</code>\n👤 <b>Kpay Sender:</b> {sender_name}\n━━━━━━━━━━━━━━━━━━━━━\n"
        f"🚨 တစ်စုံတစ်ရာ အဆင်မပြေပါက ဆက်သွယ်ရန်: {OWNER_USER}"
    )
    await update.message.reply_text(customer_confirmation, parse_mode="HTML")
    
    keys_left = get_available_key_count(pid)
    admin_alert = (
        "🔔 <b>🚨 NEW ORDER ALERT!</b> 🔔\n━━━━━━━━━━━━━━━━━━━━━\n"
        f"🧾 <b>Order ID:</b> #{tx_id}\n"
        f"👤 <b>Customer:</b> {username_clean} (ID: <code>{user.id}</code>)\n"
        f"📦 <b>Package:</b> {p_name}\n"
        f"🔢 <b>Txn Last 5:</b> <code>{txn}</code>\n"
        f"👤 <b>Kpay Sender:</b> {sender_name}\n"
        f"🔑 <b>Keys Stock Remaining:</b> {keys_left} Keys\n━━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 <b>လုပ်ဆောင်ချက်ကို ရွေးချယ်ပါ:</b>"
    )
    keyboard = [
        [InlineKeyboardButton("✅ APPROVE (Auto Send Key)", callback_data=f"autogo_{user.id}_{pid}")],
        [InlineKeyboardButton("✍️ Manual Send Key (ကိုယ်တိုင်ရိုက်ပို့မည်)", callback_data="admin_manual_send")],
        [InlineKeyboardButton("❌ Reject / Cancel Order", callback_data="admin_panel")]
    ]
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_alert, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return ConversationHandler.END

# --- ADMIN DASHBOARD PANEL ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        query = update.callback_query
        await query.answer()
    else:
        query = None

    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    
    sg_keys = get_available_key_count("sg_100gb")
    us_keys = get_available_key_count("us_100gb")
    
    text = (
        "🛠 <b>Welcome to Admin Dashboard Console</b>\n\n"
        f"📊 <b>လက်ရှိ Key လက်ကျန်စာရင်း:</b>\n"
        f"• Singapore Server: <code>{sg_keys} Keys</code>\n"
        f"• US Server: <code>{us_keys} Keys</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "လုပ်ဆောင်လိုသော စနစ်ကို ရွေးချယ်ပါ။"
    )
    keyboard = [
        [InlineKeyboardButton("📥 Add Bulk VPN Keys", callback_data="admin_add_key_menu")],
        [InlineKeyboardButton("🔑 Manage/Delete Key Stock", callback_data="admin_manage_keys_menu")],
        [InlineKeyboardButton("📦 Manage Stock Status", callback_data="admin_toggle_stock")],
        [InlineKeyboardButton("💰 Update Product Price", callback_data="admin_edit_price")],
        [InlineKeyboardButton("🚀 Send VPN Key (Manual)", callback_data="admin_manual_send")],
        [InlineKeyboardButton("📝 Edit Sent VPN Key", callback_data="admin_edit_key")],
        [InlineKeyboardButton("⬅️ Exit Dashboard", callback_data="main_menu")]
    ]
    
    if query:
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return ConversationHandler.END

# AUTO DISPATCH ENGINE
async def handle_auto_dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_")
    target_user_id = int(parts[1])
    product_id = f"{parts[2]}_{parts[3]}"
    
    assigned_key = pull_single_unused_key(product_id)
    if assigned_key:
        expiry_date = (datetime.now() + timedelta(days=30)).strftime("%d-%B-%Y")
        
        delivery_message = (
            "🚀 <b>လူကြီးမင်း ဝယ်ယူထားသော VPN Premium Key ရောက်ရှိလာပါပြီ!</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"<code>{assigned_key}</code>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 <b>Expiry Date (သက်တမ်းကုန်ရက်):</b> <code>{expiry_date}</code> (ရက်ပေါင်း ၃၀)\n"
            "💡 <i>Key စာသားကို နှိပ်လိုက်ရုံဖြင့် အလိုအလျောက် Copy ကူးပြီးသား ဖြစ်သွားပါမည်။</i>\n"
            "✨ အားပေးမှုကို အထူးကျေးဇူးတင်ရှိပါသည်။"
        )
        try:
            await context.bot.send_message(chat_id=target_user_id, text=delivery_message, parse_mode="HTML")
            await query.edit_message_text(f"✅ <b>Order Approved!</b>\nUser ID: <code>{target_user_id}</code> ထံသို့ Key (သက်တမ်းကုန်ရက်: {expiry_date}) ကို Auto ပို့ဆောင်ပြီးပါပြီ။", parse_mode="HTML")
        except Exception as e:
            await query.message.reply_text(f"❌ User ထံ စာပို့မရပါ။ Error: {e}")
    else:
        await query.message.reply_text(f"⚠️ <b>Error: Key Stock ပြတ်လပ်နေပါသည်!</b>\n{product_id} အတွက် ကီးများ ကုန်သွားပါပြီ။")

# --- 🔑 KEY INVENTORY MANAGER ---
async def admin_manage_keys_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "🔑 <b>ဘယ် Server ရဲ့ လက်ကျန် Key စာရင်းကို စီမံခန့်ခွဲမလဲ?</b>"
    keyboard = [
        [InlineKeyboardButton("🇸🇬 Singapore Unused Keys ကြည့်မည်", callback_data="viewkey_sg_100gb")],
        [InlineKeyboardButton("🇺🇸 US Unused Keys ကြည့်မည်", callback_data="viewkey_us_100gb")],
        [InlineKeyboardButton("⬅️ Back to Dashboard", callback_data="admin_panel")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return ADMIN_VIEW_KEY_TYPE

async def admin_view_and_manage_keys(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_id = query.data.replace("viewkey_", "")
    all_keys = get_all_unused_keys_db(product_id)
    
    if not all_keys:
        keyboard = [[InlineKeyboardButton("⬅️ Back to Admin Dashboard", callback_data="admin_panel")]]
        await query.edit_message_text(f"📊 <b>{product_id}</b> အတွက် လက်ရှိသိုလှောင်ထားသော မသုံးရသေးသည့် Key စာရင်း လုံးဝ (လုံးဝ) မရှိတော့ပါ။", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return ConversationHandler.END
        
    text = f"🗂 <b>{product_id} Unused Key List (လက်ကျန်စာရင်း)</b>\n"
    text += "━━━━━━━━━━━━━━━━━━━━━\n\n"
    for key_id, vpn_key in all_keys:
        short_key = vpn_key[:40] + "..." if len(vpn_key) > 40 else vpn_key
        text += f"🆔 <b>Key ID:</b> <code>{key_id}</code>\n🔑 <code>{short_key}</code>\n──────────────────\n"
        
    text += "\n❌ <b>ကီးတစ်ခုခုကို ဖြုတ်ပယ်/ဖျက်ထုတ်လိုပါက:</b>\n၎င်း၏ <b>Key ID</b> ကို အောက်တွင် ရိုက်ထည့်ပေးပါ။\n(ထွက်ရန် /cancel ဟုရိုက်ပါ)"
    await query.message.reply_text(text, parse_mode="HTML")
    return ADMIN_DEL_KEY_INPUT

async def admin_execute_key_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    input_text = update.message.text.strip()
    if not input_text.isdigit():
        await update.message.reply_text("❌ Key ID သည် ဂဏန်းသီးသန့်သာ ဖြစ်ရပါမည်။ တိကျစွာ ထပ်မံရိုက်ထည့်ပါ။")
        return ADMIN_DEL_KEY_INPUT
        
    key_id_to_del = int(input_text)
    is_deleted = delete_key_by_id(key_id_to_del)
    if is_deleted:
        await update.message.reply_text(f"✅ <b>Success!</b> Key ID: <code>{key_id_to_del}</code> ကို ဖျက်ထုတ်လိုက်ပါပြီ။\n\n🔍 လက်ကျန်ကီးစာရင်းအား ပြန်လည်ကြည့်ရှုရန် /start ကို နှိပ်၍ Admin Panel ထဲသို့ ပြန်ဝင်ပေးပါရန်။", parse_mode="HTML")
    else:
        await update.message.reply_text("❌ ထို Key ID ကို ရှာမတွေ့ပါ။ ID နံပါတ် မှန်ကန်စွာ ပြန်လည်ရိုက်ထည့်ပါ။")
        return ADMIN_DEL_KEY_INPUT
    return ConversationHandler.END

# Bulk Key Add
async def admin_add_key_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "📥 <b>ဘယ် Server အတွက် Key များ ထည့်သွင်းမလဲ?</b>"
    keyboard = [
        [InlineKeyboardButton("🇸🇬 Singapore Keys ထည့်မည်", callback_data="addkey_sg_100gb")],
        [InlineKeyboardButton("🇺🇸 US Keys ထည့်မည်", callback_data="addkey_us_100gb")],
        [InlineKeyboardButton("⬅️ Back", callback_data="admin_panel")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return ADMIN_ADD_KEY_TYPE

async def admin_add_key_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_id = query.data.replace("addkey_", "")
    context.user_data["admin_add_target_pid"] = product_id
    await query.message.reply_text(f"🔑 <b>{product_id} အတွက် Key များထည့်ခြင်း:</b>\n\nKey များကို တစ်ကြောင်းလျှင် တစ်ခု (Line by Line) ဖြင့် ရိုက်ထည့် သို့မဟုတ် Paste လုပ်ပြီး ပို့ပေးပါ။", parse_mode="HTML")
    return ADMIN_ADD_KEY_INPUT

async def admin_add_key_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_keys_text = update.message.text
    product_id = context.user_data["admin_add_target_pid"]
    keys_list = raw_keys_text.split("\n")
    insert_bulk_keys(product_id, keys_list)
    await update.message.reply_text(f"✅ အောင်မြင်ပါပြီ။ Key စုစုပေါင်း <b>{len(keys_list)}</b> ခုကို ထည့်သွင်းပြီးပါပြီ။", parse_mode="HTML")
    return ConversationHandler.END

# Manual Key Send
async def admin_start_manual_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("👤 ဝယ်ယူသူ၏ <b>Customer ID</b> ကို ရိုက်ထည့်ပေးပါ။\nပယ်ဖျက်ရန် /cancel ဟု ရိုက်ပါ။", parse_mode="HTML")
    return ADMIN_MANUAL_ID

async def admin_process_manual_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_id = update.message.text.strip()
    if not target_id.isdigit():
        await update.message.reply_text("❌ ID နံပါတ် မှားယွင်းနေပါသည်။ ဂဏန်း သီးသန့်သာ ရိုက်ထည့်ပါ။")
        return ADMIN_MANUAL_ID
    context.user_data["admin_manual_target_id"] = int(target_id)
    await update.message.reply_text("🔑 ထို User ထံသို့ ပို့ပေးမည့် <b>VPN Key / Config</b> ကို ရိုက်ထည့် သို့မဟုတ် Paste လုပ်ပြီး ပို့လိုက်ပါ။")
    return ADMIN_MANUAL_KEY

async def admin_process_manual_deliver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config_text = update.message.text
    target_user_id = context.user_data["admin_manual_target_id"]
    
    expiry_date = (datetime.now() + timedelta(days=30)).strftime("%d-%B-%Y")
    delivery_message = (
        f"🚀 <b>လူကြီးမင်း ဝယ်ယူထားသော VPN Premium Key ရောက်ရှိလာပါပြီ!</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<code>{config_text}</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 <b>Expiry Date (သက်တမ်းကုန်ရက်):</b> <code>{expiry_date}</code> (ရက်ပေါင်း ၃၀)\n"
        f"✨ အားပေးမှုကို အထူးကျေးဇူးတင်ရှိပါသည်။"
    )
    try:
        await context.bot.send_message(chat_id=target_user_id, text=delivery_message, parse_mode="HTML")
        await update.message.reply_text("✅ ဝယ်သူထံသို့ VPN Config ကို Manual စနစ်ဖြင့် အောင်မြင်စွာ ပို့ဆောင်ပေးပြီးပါပြီ။")
    except Exception as e:
        await update.message.reply_text(f"❌ စာပို့၍မရပါ။ Error: {e}")
    return ConversationHandler.END

# Price & Stock Handlers
async def admin_toggle_stock_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    products = get_products()
    keyboard = []
    text = "🔄 <b>Stock Management Mode</b>\n\n"
    for pid, name, _, stock in products:
        status_text = "🟢 IN_STOCK" if stock == "IN_STOCK" else "🔴 OUT_OF_STOCK"
        text += f"▪️ {name} -> <b>{status_text}</b>\n"
        keyboard.append([InlineKeyboardButton(f"Toggle {name}", callback_data=f"tgt_{pid}")])
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="admin_panel")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

async def handle_stock_toggle_execution(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_id = query.data.replace("tgt_", "")
    products = {p[0].lower(): p[3] for p in get_products()}
    current_status = products.get(product_id.lower(), "IN_STOCK")
    new_status = "OUT_OF_STOCK" if current_status == "IN_STOCK" else "IN_STOCK"
    update_stock_db(product_id, new_status)
    return await admin_toggle_stock_menu(update, context)

async def admin_edit_price_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    products = get_products()
    keyboard = []
    text = "💰 <b>Price Management Mode</b>\n\n"
    for pid, name, price, _ in products:
        text += f"▪️ {name} -> <b>{price} Ks</b>\n"
        keyboard.append([InlineKeyboardButton(f"Edit Price: {name}", callback_data=f"prc_{pid}")])
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="admin_panel")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return ADMIN_SELECT_PRICE_PROD

async def handle_price_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_id = query.data.replace("prc_", "")
    context.user_data["admin_edit_price_pid"] = product_id
    await query.message.reply_text(f"🔢 <b>{product_id}</b> အတွက် Сျေးနှုန်းအသစ်ကို ဂဏန်းသီးသန့် ရိုက်ထည့်ပေးပါ။", parse_mode="HTML")
    return ADMIN_GET_NEW_PRICE

async def process_new_price_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price_text = update.message.text.strip()
    if not price_text.isdigit():
        await update.message.reply_text("❌ ဈေးနှုန်းသည် ဂဏန်းသီးသန့်သာ ဖြစ်ရပါမည်။")
        return ADMIN_GET_NEW_PRICE
    product_id = context.user_data["admin_edit_price_pid"]
    new_price = int(price_text)
    update_price_db(product_id, new_price)
    await update.message.reply_text(f"✅ ဈေးနှုန်းကို {new_price} Ks သို့ ပြောင်းလဲလိုက်ပါပြီ။")
    return ConversationHandler.END

async def admin_start_edit_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("📝 <b>Key ပြန်ပြင်ပေးမည့် ဝယ်သူ၏ Customer ID</b> ကို ရိုက်ထည့်ပေးပါ။", parse_mode="HTML")
    return ADMIN_EDIT_ID

async def admin_process_edit_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_id = update.message.text.strip()
    if not target_id.isdigit():
        await update.message.reply_text("❌ ID နံပါတ် မှားယွင်းနေပါသည်။")
        return ADMIN_EDIT_ID
    context.user_data["admin_edit_user_id"] = int(target_id)
    await update.message.reply_text("🔄 ထို User ထံသို့ အစားထိုး ပြန်လည်ပေးပို့မည့် <b>VPN Key အသစ်</b> ကို ပို့လိုက်ပါ။", parse_mode="HTML")
    return ADMIN_EDIT_CONFIG

async def admin_process_and_deliver_edited_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_config_text = update.message.text
    target_user_id = context.user_data["admin_edit_user_id"]
    
    expiry_date = (datetime.now() + timedelta(days=30)).strftime("%d-%B-%Y")
    edit_delivery_message = (
        f"⚡️ <b>NOTICE: လူကြီးမင်း၏ VPN Premium Key ကို ပြင်ဆင်ပေးထားပါသည်။</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"ယခင် Key အဟောင်းကို ဖျက်ပြီး အောက်ပါ <b>Key အသစ်</b> ကို အစားထိုး အသုံးပြုပေးပါရန်။\n\n"
        f"<code>{new_config_text}</code>\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 <b>Expiry Date (သက်တမ်းကုန်ရက်):</b> <code>{expiry_date}</code> (ရက်ပေါင်း ၃၀ အသစ်)\n"
        f"✨ Owner: {OWNER_USER}"
    )
    try:
        await context.bot.send_message(chat_id=target_user_id, text=edit_delivery_message, parse_mode="HTML")
        await update.message.reply_text("✅ ဝယ်သူထံသို့ ပြင်ဆင်ထားသော VPN Key အသစ်ကို ပို့ဆောင်ပေးပြီးပါပြီ။")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
    return ConversationHandler.END

async def cancel_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    await start(update, context)
    return ConversationHandler.END

# --- MAIN ENGINE ---
def main():
    init_db()  # Cloud Disk လမ်းကြောင်းသစ်ဖြင့် Database စတင်တည်ဆောက်ခြင်း
    app = Application.builder().token(BOT_TOKEN).build()
    
    purchase_flow = ConversationHandler(
        entry_points=[CallbackQueryHandler(buy_vpn_menu, pattern="^buy_vpn$")],
        states={
            CHOOSING_SERVER: [CallbackQueryHandler(handle_server_selection, pattern="^select_")],
            ENTERING_TXN: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_txn_input)],
            ENTERING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_name_input)]
        },
        fallbacks=[
            CallbackQueryHandler(cancel_action, pattern="^buy_vpn$"),
            CallbackQueryHandler(cancel_action, pattern="^main_menu$"),
            CommandHandler("cancel", cancel_action)
        ],
        per_chat=True
    )
    
    admin_add_key_flow = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_key_menu, pattern="^admin_add_key_menu$")],
        states={
            ADMIN_ADD_KEY_TYPE: [CallbackQueryHandler(admin_add_key_select, pattern="^addkey_")],
            ADMIN_ADD_KEY_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_key_save)]
        },
        fallbacks=[CommandHandler("cancel", cancel_action), CallbackQueryHandler(cancel_action, pattern="^admin_panel$")],
        per_chat=True
    )
    
    admin_manual_flow = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_start_manual_send, pattern="^admin_manual_send$")],
        states={
            ADMIN_MANUAL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_process_manual_id)],
            ADMIN_MANUAL_KEY: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_process_manual_deliver)]
        },
        fallbacks=[CommandHandler("cancel", cancel_action)],
        per_chat=True
    )
    
    admin_price_flow = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_edit_price_menu, pattern="^admin_edit_price$")],
        states={
            ADMIN_SELECT_PRICE_PROD: [CallbackQueryHandler(handle_price_selection, pattern="^prc_")],
            ADMIN_GET_NEW_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_new_price_input)]
        },
        fallbacks=[CommandHandler("cancel", cancel_action), CallbackQueryHandler(cancel_action, pattern="^admin_panel$")],
        per_chat=True
    )
    
    admin_key_edit_flow = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_start_edit_config, pattern="^admin_edit_key$")],
        states={
            ADMIN_EDIT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_process_edit_id)],
            ADMIN_EDIT_CONFIG: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_process_and_deliver_edited_config)]
        },
        fallbacks=[CommandHandler("cancel", cancel_action)],
        per_chat=True
    )
    
    admin_inventory_flow = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_manage_keys_menu, pattern="^admin_manage_keys_menu$")],
        states={
            ADMIN_VIEW_KEY_TYPE: [CallbackQueryHandler(admin_view_and_manage_keys, pattern="^viewkey_")],
            ADMIN_DEL_KEY_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_execute_key_delete)]
        },
        fallbacks=[CommandHandler("cancel", cancel_action), CallbackQueryHandler(cancel_action, pattern="^admin_panel$")],
        per_chat=True
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(purchase_flow)
    app.add_handler(admin_add_key_flow)
    app.add_handler(admin_manual_flow)
    app.add_handler(admin_price_flow)
    app.add_handler(admin_key_edit_flow)
    app.add_handler(admin_inventory_flow)
    
    app.add_handler(CallbackQueryHandler(start, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_toggle_stock_menu, pattern="^admin_toggle_stock$"))
    app.add_handler(CallbackQueryHandler(handle_stock_toggle_execution, pattern="^tgt_"))
    app.add_handler(CallbackQueryHandler(handle_auto_dispatch, pattern="^autogo_"))
    
    print("🚀 Ultimate VPN Smart Bot Engine V7 (Cloud Volume SQLite Ready) is Live.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()