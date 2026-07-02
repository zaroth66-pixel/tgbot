import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import TelegramError

from utils.db import load_data, save_data, get_user, save_user
from utils.helpers import (
    is_admin, check_channel_membership, download_file,
    ADMIN_IDS, MIN_WITHDRAW, MIN_REFERRALS, human_size
)
from utils.languages import t, LANGUAGES

logger = logging.getLogger(__name__)

BOT_USERNAME = os.environ.get("BOT_USERNAME", "mybot")


def _get_referral_amount(data: dict) -> int:
    """Configurable referral reward (admin can change in settings)."""
    return data.get("referral_amount", 40)


# ── Helpers ────────────────────────────────────────────────────────────────────
async def _reply(update: Update, text: str, **kwargs):
    """Send a message whether the update came from a command or callback."""
    if update.callback_query:
        await update.callback_query.message.reply_text(text, **kwargs)
    else:
        await update.message.reply_text(text, **kwargs)


async def _send_join_prompt(update: Update, ctx, lang: str, data: dict):
    """Send the channel-join prompt, works in both message and callback contexts."""
    channel = data.get("required_channel_username", "@mychannel")
    kb = [
        [InlineKeyboardButton(t(lang, "join_btn"), url=f"https://t.me/{channel.lstrip('@')}")],
        [InlineKeyboardButton(t(lang, "check_join_btn"), callback_data="check_joined")],
    ]
    markup = InlineKeyboardMarkup(kb)
    # FIX #1: always use _reply so we never call update.message on a callback update
    await _reply(update, t(lang, "join_prompt"), reply_markup=markup)


# ── Language selection ─────────────────────────────────────────────────────────
async def show_lang_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb, row = [], []
    for code, name in LANGUAGES.items():
        row.append(InlineKeyboardButton(name, callback_data=f"setlang_{code}"))
        if len(row) == 2:
            kb.append(row); row = []
    if row:
        kb.append(row)
    text = "🌍 Please select your language / እባክዎ ቋንቋዎን ይምረጡ / Afaan filadhaa / ቋንቋኻ ምረጽ"
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def handle_setlang(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    # FIX: use prefix strip so "setlang_pt" and future "setlang_pt_br" both work
    lang = q.data[len("setlang_"):]
    await q.answer()
    data = load_data()
    user = get_user(data, q.from_user.id)
    user["lang"] = lang
    save_user(data, q.from_user.id, user)
    await show_user_menu(update, ctx, lang)


# ── Send APK immediately ───────────────────────────────────────────────────────
async def send_apk_to_user(bot, user_id: int, lang: str):
    data  = load_data()
    links = data.get("apk_links", [])
    idx   = data.get("active_link_index", 0)
    if not links:
        await bot.send_message(user_id, "⚠️ No APK available yet. Check back soon!")
        return

    link = links[idx]
    await bot.send_message(user_id, t(lang, "welcome"))

    if data.get("image_url"):
        try:
            await bot.send_photo(user_id, photo=data["image_url"],
                                 caption=f"📦 {link['label']} v{data.get('version','1.0')}")
        except Exception as e:
            logger.warning(f"Image send failed: {e}")

    if data.get("video_url"):
        path, _ = download_file(data["video_url"], ".mp4")
        if path:
            try:
                with open(path, "rb") as vf:
                    await bot.send_video(user_id, video=vf, caption="📹 Installation Guide")
            except Exception as e:
                logger.warning(f"Video send failed: {e}")
            finally:
                os.unlink(path)

    # FIX #5: removed redundant separate apk_caption message; caption is on the document
    path, size = download_file(link["url"], ".apk")
    if path:
        try:
            with open(path, "rb") as apk:
                await bot.send_document(
                    user_id,
                    document=apk,
                    filename=f"{link['label']}.apk",
                    caption=f"📦 {link['label']} v{data.get('version','1.0')} — {human_size(size)}",
                )
        except Exception as e:
            logger.error(f"APK send failed: {e}")
        finally:
            os.unlink(path)


# ── /start handler ─────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args    = ctx.args or []

    if is_admin(user_id):
        from handlers.admin import show_admin_menu
        await show_admin_menu(update, ctx)
        return

    # NEW: /cancel shortcut
    if args and args[0] == "cancel":
        await cmd_cancel(update, ctx)
        return

    data = load_data()

    # NEW: check if user is banned
    if str(user_id) in data.get("banned_users", {}):
        await update.message.reply_text("🚫 You have been banned from using this bot.")
        return

    user = get_user(data, user_id)

    # FIX #4: parse referral cleanly with prefix strip, compare int to int
    referred_by = None
    if args and args[0].startswith("ref_"):
        try:
            referred_by = int(args[0][len("ref_"):])
            if referred_by == user_id:
                referred_by = None
        except Exception:
            referred_by = None

    if referred_by and not user.get("referred_by"):
        user["referred_by"] = referred_by

    save_user(data, user_id, user)

    lang = user.get("lang", "")

    if not lang or (args and args[0] == "setlang"):
        await show_lang_select(update, ctx)
        return

    await send_apk_to_user(ctx.bot, user_id, lang)

    channel = data.get("required_channel_username", "@mychannel")
    channel_id = data.get("required_channel_id") or channel
    joined = await check_channel_membership(ctx.bot, user_id, channel_id)

    if not joined:
        # FIX #1: _send_join_prompt works regardless of message/callback context
        await _send_join_prompt(update, ctx, lang, data)
    else:
        await show_user_menu(update, ctx, lang)


# ── /cancel command ────────────────────────────────────────────────────────────
async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """NEW: lets users escape a stuck awaiting state."""
    user_id = update.effective_user.id
    data    = load_data()
    user    = get_user(data, user_id)
    lang    = user.get("lang", "en")
    if user.get("awaiting"):
        user["awaiting"] = None
        save_user(data, user_id, user)
        await _reply(update, "❌ Cancelled. Returning to menu.")
    await show_user_menu(update, ctx, lang)


# ── User main menu ─────────────────────────────────────────────────────────────
async def show_user_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE, lang: str = None):
    user_id = update.effective_user.id
    data    = load_data()
    user    = get_user(data, user_id)
    lang    = lang or user.get("lang", "en")

    kb = [
        [InlineKeyboardButton(t(lang, "referral_menu"), callback_data="referral_menu")],
        [InlineKeyboardButton("📊 " + t(lang, "my_stats"),  callback_data="my_stats")],
        [InlineKeyboardButton("🌍 " + t(lang, "lang_select"), callback_data="change_lang")],
    ]
    text = (
        f"{t(lang, 'main_menu')}\n\n"
        f"{t(lang, 'balance', balance=user.get('balance', 0))}\n"
        f"{t(lang, 'referrals_count', count=user.get('referrals', 0))}"
    )
    markup = InlineKeyboardMarkup(kb)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup)
    else:
        await update.message.reply_text(text, reply_markup=markup)


# ── Referral menu ──────────────────────────────────────────────────────────────
async def show_referral_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q       = update.callback_query
    user_id = q.from_user.id
    data    = load_data()
    user    = get_user(data, user_id)
    lang    = user.get("lang", "en")

    channel    = data.get("required_channel_username", "@mychannel")
    channel_id = data.get("required_channel_id") or channel
    joined     = await check_channel_membership(ctx.bot, user_id, channel_id)

    if not joined:
        # FIX #3: answer the query before the early return so it doesn't spin
        await q.answer()
        kb = [
            [InlineKeyboardButton(t(lang, "join_btn"), url=f"https://t.me/{channel.lstrip('@')}")],
            [InlineKeyboardButton(t(lang, "check_join_btn"), callback_data="check_joined")],
        ]
        await q.edit_message_text(t(lang, "join_prompt"), reply_markup=InlineKeyboardMarkup(kb))
        return

    await q.answer()

    bot_username = (await ctx.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    balance  = user.get("balance", 0)
    refs     = user.get("referrals", 0)
    reward   = _get_referral_amount(data)

    kb = [
        [InlineKeyboardButton(t(lang, "submit_screenshot"), callback_data="submit_screenshot")],
        [InlineKeyboardButton("🏆 " + t(lang, "leaderboard"),  callback_data="leaderboard")],
    ]
    if balance >= MIN_WITHDRAW and refs >= MIN_REFERRALS:
        kb.append([InlineKeyboardButton(t(lang, "withdraw_btn"), callback_data="request_withdraw")])
    kb.append([InlineKeyboardButton("⬅️ " + t(lang, "main_menu"), callback_data="user_menu")])

    text = (
        f"💰 <b>{t(lang, 'referral_menu')}</b>\n\n"
        f"{t(lang, 'balance', balance=balance)}\n"
        f"{t(lang, 'referrals_count', count=refs)}\n"
        f"🎁 Earn {reward} ETB per referral\n\n"
        f"🔗 Your referral link:\n<code>{ref_link}</code>\n\n"
        f"{t(lang, 'share_text')}"
    )
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
# ── My Stats ──────────────────────────────────────────────────────────────────
async def show_my_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """NEW: user's personal stats screen."""
    q       = update.callback_query
    user_id = q.from_user.id
    await q.answer()
    data    = load_data()
    user    = get_user(data, user_id)
    lang    = user.get("lang", "en")

    refs    = user.get("referrals", 0)
    balance = user.get("balance", 0)
    pending = "⏳ Yes" if user.get("pending_withdraw") else "No"
    reward  = _get_referral_amount(data)
    needed  = max(0, MIN_REFERRALS - refs)
    needed_bal = max(0, MIN_WITHDRAW - balance)

    text = (
        f"📊 *Your Stats*\n\n"
        f"💵 Balance: *{balance} ETB*\n"
        f"👥 Approved Referrals: *{refs}*\n"
        f"🎁 Reward per referral: *{reward} ETB*\n"
        f"💸 Pending payout: *{pending}*\n\n"
        f"📈 Progress to payout:\n"
        f"  • Referrals needed: {needed} more\n"
        f"  • ETB needed: {needed_bal} more\n"
    )
    kb = [[InlineKeyboardButton("⬅️ Back", callback_data="user_menu")]]
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


# ── Leaderboard ────────────────────────────────────────────────────────────────
async def show_leaderboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """NEW: top 10 referrers."""
    q    = update.callback_query
    await q.answer()
    data = load_data()
    lang = data.get("users", {}).get(str(q.from_user.id), {}).get("lang", "en")

    users = data.get("users", {})
    ranked = sorted(
        [(uid, u.get("referrals", 0)) for uid, u in users.items()],
        key=lambda x: x[1], reverse=True
    )[:10]

    lines = ["🏆 *Top Referrers*\n"]
    medals = ["🥇", "🥈", "🥉"] + ["🔹"] * 7
    for i, (uid, refs) in enumerate(ranked):
        u    = users[uid]
        name = u.get("name", f"User {uid[:6]}")
        lines.append(f"{medals[i]} {name} — {refs} referrals")

    kb = [[InlineKeyboardButton("⬅️ Back", callback_data="referral_menu")]]
    await q.edit_message_text(
        "\n".join(lines) or "No data yet.",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )


# ── Check joined callback ──────────────────────────────────────────────────────
async def check_joined_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q       = update.callback_query
    user_id = q.from_user.id
    await q.answer()
    data    = load_data()
    user    = get_user(data, user_id)
    lang    = user.get("lang", "en")

    channel_id = data.get("required_channel_id") or data.get("required_channel_username", "@mychannel")
    joined = await check_channel_membership(ctx.bot, user_id, channel_id)

    if joined:
        # FIX #2: edit the current message with join confirm, then send the menu as a fresh message
        await q.edit_message_text(t(lang, "joined_confirm"))
        # Build and send the full user menu as a new message
        kb = [
            [InlineKeyboardButton(t(lang, "referral_menu"), callback_data="referral_menu")],
            [InlineKeyboardButton("📊 " + t(lang, "my_stats"), callback_data="my_stats")],
            [InlineKeyboardButton("🌍 " + t(lang, "lang_select"), callback_data="change_lang")],
        ]
        await ctx.bot.send_message(
            user_id,
            f"{t(lang, 'main_menu')}\n\n"
            f"{t(lang, 'balance', balance=user.get('balance', 0))}\n"
            f"{t(lang, 'referrals_count', count=user.get('referrals', 0))}",
            reply_markup=InlineKeyboardMarkup(kb),
        )
    else:
        await q.answer(t(lang, "not_joined"), show_alert=True)


# ── Screenshot submission ──────────────────────────────────────────────────────
async def submit_screenshot_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q       = update.callback_query
    user_id = q.from_user.id
    data    = load_data()
    user    = get_user(data, user_id)
    lang    = user.get("lang", "en")

    # FIX #5: answer first (only once) — no second q.answer() below
    channel_id = data.get("required_channel_id") or data.get("required_channel_username", "@mychannel")
    joined = await check_channel_membership(ctx.bot, user_id, channel_id)
    if not joined:
        await q.answer(t(lang, "not_joined"), show_alert=True)
        return

    # NEW: anti-duplicate — prevent submitting again while one is pending review
    if user.get("screenshot_pending"):
        await q.answer("⏳ You already have a screenshot under review. Please wait.", show_alert=True)
        return

    await q.answer()
    user["awaiting"] = "screenshot"
    save_user(data, user_id, user)
    await q.edit_message_text(
        t(lang, "screenshot_prompt"),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="referral_menu")]]),
    )


async def handle_screenshot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """User sends a photo as screenshot proof."""
    user_id = update.effective_user.id
    if update.effective_chat.type != "private" or is_admin(user_id):
        return

    data = load_data()
    user = get_user(data, user_id)
    lang = user.get("lang", "en")

    if user.get("awaiting") != "screenshot":
        return

    if not update.message.photo:
        await update.message.reply_text("❌ Please send a photo/screenshot.")
        return

    # ── AI moderation ─────────────────────────────────────────────────────────
    if data.get("ai_moderation_enabled", True):
        thinking_msg = await update.message.reply_text("🔍 Verifying your screenshot, please wait…")
        try:
            # Download the highest-res version of the submitted photo
            photo_file = await update.message.photo[-1].get_file()
            img_bytes  = await photo_file.download_as_bytearray()

            from utils.groq_vision import validate_screenshot
            is_valid, reason = await validate_screenshot(bytes(img_bytes))
        except Exception as e:
            logger.error(f"AI moderation exception: {e}")
            is_valid, reason = True, f"AI check failed ({e}), passed to admin"
        finally:
            try:
                await thinking_msg.delete()
            except Exception:
                pass

        if not is_valid:
            strikes = user.get("screenshot_strikes", 0) + 1
            user["screenshot_strikes"] = strikes
            user["awaiting"] = None

            if strikes >= 3:
                # Auto-ban after 3 failed attempts
                user["awaiting"] = None
                save_user(data, user_id, user)
                data.setdefault("banned_users", {})[str(user_id)] = True
                save_data(data)
                await update.message.reply_text(
                    "🚫 Your account has been banned after 3 invalid screenshot submissions.\n"
                    "Contact support if you believe this is a mistake."
                )
                # Notify admins
                for admin_id in ADMIN_IDS:
                    try:
                        await ctx.bot.send_message(
                            admin_id,
                            f"🚫 User *{update.effective_user.full_name}* (ID: `{user_id}`) "
                            f"auto-banned after 3 invalid screenshots.\n"
                            f"Last rejection reason: _{reason}_",
                            parse_mode="Markdown",
                        )
                    except Exception:
                        pass
                return
            else:
                save_user(data, user_id, user)
                remaining = 3 - strikes
                await update.message.reply_text(
                    f"❌ *Screenshot rejected by AI verification*\n\n"
                    f"Reason: {reason}\n\n"
                    f"Please make sure you send a screenshot of the installed app "
                    f"that matches the reference. You have *{remaining} attempt(s)* remaining "
                    f"before your account is banned.\n\n"
                    f"Tap 📸 Submit Screenshot to try again.",
                    parse_mode="Markdown",
                )
                return

    # ── Passed AI check (or AI disabled / fallback) ───────────────────────────
    user["awaiting"]           = None
    user["screenshot_pending"] = True
    user["name"]               = update.effective_user.full_name
    # Reset strikes on a valid submission
    user["screenshot_strikes"] = 0
    save_user(data, user_id, user)

    referred_by = user.get("referred_by")
    reward      = _get_referral_amount(data)
    ai_status   = "✅ AI approved" if data.get("ai_moderation_enabled", True) else "⚠️ AI disabled"
    caption = (
        f"📸 Screenshot from *{update.effective_user.full_name}* "
        f"(ID: `{user_id}`)\n"
        f"Referred by: {referred_by or 'None'}\n"
        f"Balance: {user.get('balance', 0)} ETB | Referrals: {user.get('referrals', 0)}\n"
        f"Reward if approved: +{reward} ETB → referrer ID {referred_by}\n"
        f"🤖 {ai_status}"
    )

    for admin_id in ADMIN_IDS:
        try:
            await ctx.bot.forward_message(
                chat_id=admin_id,
                from_chat_id=update.effective_chat.id,
                message_id=update.message.message_id,
            )
            kb = [[
                InlineKeyboardButton(f"✅ Approve (+{reward} ETB)", callback_data=f"approve_ref_{user_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_ref_{user_id}"),
            ]]
            await ctx.bot.send_message(
                admin_id, caption,
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Failed to forward screenshot to admin {admin_id}: {e}")

    try:
        await update.message.delete()
    except Exception:
        pass

    await ctx.bot.send_message(user_id, t(lang, "screenshot_sent"))


# ── Withdraw request ───────────────────────────────────────────────────────────
async def request_withdraw_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q       = update.callback_query
    user_id = q.from_user.id
    data    = load_data()
    user    = get_user(data, user_id)
    lang    = user.get("lang", "en")

    # FIX #6: answer only once; use show_alert on the single answer call for error cases
    if user.get("balance", 0) < MIN_WITHDRAW or user.get("referrals", 0) < MIN_REFERRALS:
        await q.answer(t(lang, "withdraw_min"), show_alert=True)
        return

    if user.get("pending_withdraw"):
        await q.answer("⏳ You already have a pending withdrawal request.", show_alert=True)
        return

    await q.answer()
    user["awaiting"] = "withdraw_number"
    save_user(data, user_id, user)
    await q.edit_message_text(
        t(lang, "withdraw_prompt"),
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="referral_menu")]]),
    )


async def handle_withdraw_number(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.effective_chat.type != "private" or is_admin(user_id):
        return
    data = load_data()
    user = get_user(data, user_id)
    lang = user.get("lang", "en")

    if user.get("awaiting") != "withdraw_number":
        return

    number = update.message.text.strip()
    user["awaiting"]         = None
    user["pending_withdraw"] = True
    user["withdraw_number"]  = number
    save_user(data, user_id, user)

    name = update.effective_user.full_name
    for admin_id in ADMIN_IDS:
        try:
            kb = [[
                InlineKeyboardButton("✅ Pay & Approve", callback_data=f"pay_approve_{user_id}"),
                InlineKeyboardButton("❌ Reject",        callback_data=f"pay_reject_{user_id}"),
            ]]
            await ctx.bot.send_message(
                admin_id,
                f"💸 *Withdrawal Request*\n\n"
                f"👤 {name} (ID: `{user_id}`)\n"
                f"💵 Amount: *{user.get('balance', 0)} ETB*\n"
                f"📱 Payment number: `{number}`",
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")

    await update.message.reply_text(t(lang, "withdraw_sent"))


# ── New member joined group ────────────────────────────────────────────────────
async def handle_new_member(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        if member.is_bot:
            continue
        try:
            bot_username = (await ctx.bot.get_me()).username
            kb = [[InlineKeyboardButton(
                t("en", "get_app_btn"),
                url=f"https://t.me/{bot_username}?start=welcome"
            )]]
            await update.message.reply_text(
                t("en", "group_welcome", name=member.mention_html()),
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"Welcome message failed: {e}")
