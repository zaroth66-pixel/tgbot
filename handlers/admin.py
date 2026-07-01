import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from utils.db import load_data, save_data, get_user, save_user
from utils.helpers import is_admin, get_active_link, build_caption, ADMIN_IDS
from utils.languages import LANGUAGES

logger = logging.getLogger(__name__)


# ── Main admin menu ────────────────────────────────────────────────────────────
async def show_admin_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    link = get_active_link(data)
    h, m = data["schedule_hour"], str(data["schedule_minute"]).zfill(2)
    senbl = "✅ ON" if data["schedule_enabled"] else "❌ OFF"
    img   = "✅" if data.get("image_url") else "❌"
    vid   = "✅" if data.get("video_url") else "❌"

    kb = [
        [InlineKeyboardButton("📎 APK Links",            callback_data="a_links"),
         InlineKeyboardButton("🖼 Image",                callback_data="a_image")],
        [InlineKeyboardButton("📹 Video",                callback_data="a_video"),
         InlineKeyboardButton("💬 Caption & Words",      callback_data="a_caption")],
        [InlineKeyboardButton("🌍 Language Captions",    callback_data="a_langcaptions")],
        [InlineKeyboardButton("📦 Version & Changelog",  callback_data="a_version")],
        [InlineKeyboardButton("🔐 Channel Settings",     callback_data="a_channel")],
        [InlineKeyboardButton("👥 Groups",               callback_data="a_groups")],
        [InlineKeyboardButton("⏰ Schedule",             callback_data="a_schedule")],
        [InlineKeyboardButton("📤 Post Now",             callback_data="a_postnow"),
         InlineKeyboardButton("👁 Preview Post",         callback_data="a_preview")],
        [InlineKeyboardButton("📣 Broadcast",            callback_data="a_broadcast")],
        [InlineKeyboardButton("📊 Statistics",           callback_data="a_stats")],
        [InlineKeyboardButton("👤 User Management",      callback_data="a_users")],
        [InlineKeyboardButton("⚙️ Settings",             callback_data="a_settings")],
        [InlineKeyboardButton("💾 Backup / Restore",     callback_data="a_backup")],
        [InlineKeyboardButton("🏷 Watermark",            callback_data="a_watermark")],
    ]
    text = (
        f"🤖 *Admin Panel*\n\n"
        f"📎 APK: {'✅ ' + link['label'] if link else '❌ None'}\n"
        f"🖼 Image: {img}  📹 Video: {vid}\n"
        f"👥 Groups: {len(data['groups'])}\n"
        f"📦 Version: v{data.get('version','1.0.0')}\n"
        f"⏰ Schedule: {h}:{m} UTC — {senbl}\n"
        f"👤 Users: {len(data.get('users',{}))}\n"
        f"📊 Total Posts: {data.get('total_posts',0)}"
    )
    markup = InlineKeyboardMarkup(kb)
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=markup, parse_mode="Markdown")


# ── Callback router ────────────────────────────────────────────────────────────
async def admin_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    d = q.data

    if not is_admin(q.from_user.id):
        await q.answer("⛔ Not authorised.", show_alert=True)
        return

    # ── Back ──────────────────────────────────────────────────────────────────
    if d == "a_menu":
        await q.answer()
        await show_admin_menu(update, ctx)

    # ── APK Links ─────────────────────────────────────────────────────────────
    elif d == "a_links":
        await q.answer(); await show_links_menu(update, ctx)
    elif d == "a_addlink":
        await q.answer()
        ctx.user_data["a_awaiting"] = "link_label"
        await q.edit_message_text("📎 Send the *label* for this APK link:", parse_mode="Markdown")
    elif d.startswith("a_setactive_"):
        idx = int(d.split("_")[-1])
        data = load_data(); data["active_link_index"] = idx; save_data(data)
        await q.answer("✅ Active link set!", show_alert=True)
        await show_links_menu(update, ctx)
    elif d.startswith("a_dellink_"):
        await q.answer()
        idx = int(d.split("_")[-1])
        data = load_data()
        if 0 <= idx < len(data["apk_links"]):
            data["apk_links"].pop(idx)
            data["active_link_index"] = max(0, min(data["active_link_index"], len(data["apk_links"])-1))
            save_data(data)
        await show_links_menu(update, ctx)

    # ── Image ─────────────────────────────────────────────────────────────────
    elif d == "a_image":
        await q.answer(); await show_image_menu(update, ctx)
    elif d == "a_setimgurl":
        await q.answer()
        ctx.user_data["a_awaiting"] = "image_url"
        await q.edit_message_text("🖼 Send the direct image URL:")
    elif d == "a_uploadimg":
        await q.answer()
        ctx.user_data["a_awaiting"] = "image_upload"
        await q.edit_message_text("🖼 Send the image photo now:")
    elif d == "a_clearimg":
        data = load_data(); data["image_url"] = ""; save_data(data)
        await q.answer("🗑 Cleared.", show_alert=True); await show_image_menu(update, ctx)

    # ── Video ─────────────────────────────────────────────────────────────────
    elif d == "a_video":
        await q.answer(); await show_video_menu(update, ctx)
    elif d == "a_setvidurl":
        await q.answer()
        ctx.user_data["a_awaiting"] = "video_url"
        await q.edit_message_text("📹 Send the GitHub raw .mp4 URL:")
    elif d == "a_clearvid":
        data = load_data(); data["video_url"] = ""; save_data(data)
        await q.answer("🗑 Cleared.", show_alert=True); await show_video_menu(update, ctx)

    # ── Caption ───────────────────────────────────────────────────────────────
    elif d == "a_caption":
        await q.answer(); await show_caption_menu(update, ctx)
    elif d == "a_editcaption":
        await q.answer()
        ctx.user_data["a_awaiting"] = "caption"
        await q.edit_message_text("💬 Send the new main caption:")
    elif d == "a_addword":
        await q.answer()
        ctx.user_data["a_awaiting"] = "extra_word"
        await q.edit_message_text("➕ Send the extra line to add:")
    elif d.startswith("a_delword_"):
        await q.answer()
        idx = int(d.split("_")[-1])
        data = load_data()
        if 0 <= idx < len(data["extra_words"]):
            data["extra_words"].pop(idx); save_data(data)
        await show_caption_menu(update, ctx)

    # ── Language captions ─────────────────────────────────────────────────────
    elif d == "a_langcaptions":
        await q.answer(); await show_langcaptions_menu(update, ctx)
    elif d.startswith("a_editlangcap_"):
        await q.answer()
        lang = d[len("a_editlangcap_"):]
        ctx.user_data["a_awaiting"]  = "lang_caption"
        ctx.user_data["a_lang_edit"] = lang
        await q.edit_message_text(f"💬 Send the caption for *{LANGUAGES.get(lang, lang)}*:", parse_mode="Markdown")

    # ── Version ───────────────────────────────────────────────────────────────
    elif d == "a_version":
        await q.answer(); await show_version_menu(update, ctx)
    elif d == "a_editversion":
        await q.answer()
        ctx.user_data["a_awaiting"] = "version"
        await q.edit_message_text("📦 Send new version number (e.g. `1.2.3`):", parse_mode="Markdown")
    elif d == "a_editchangelog":
        await q.answer()
        ctx.user_data["a_awaiting"] = "changelog"
        await q.edit_message_text("📝 Send the changelog for this version:")

    # ── Channel settings ──────────────────────────────────────────────────────
    elif d == "a_channel":
        await q.answer(); await show_channel_menu(update, ctx)
    elif d == "a_setchannel":
        await q.answer()
        ctx.user_data["a_awaiting"] = "channel_username"
        await q.edit_message_text("🔐 Send the channel username (e.g. `@mychannel`):", parse_mode="Markdown")
    elif d == "a_setchannelid":
        await q.answer()
        ctx.user_data["a_awaiting"] = "channel_id"
        await q.edit_message_text("🔢 Send the channel numeric ID (e.g. `-1001234567890`):")

    # ── Groups ────────────────────────────────────────────────────────────────
    elif d == "a_groups":
        await q.answer(); await show_groups_menu(update, ctx)
    elif d.startswith("a_delgroup_"):
        await q.answer()
        idx = int(d.split("_")[-1])
        data = load_data()
        if 0 <= idx < len(data["groups"]):
            removed = data["groups"].pop(idx); save_data(data)
            await q.answer(f"🗑 Removed: {removed['title']}", show_alert=True)
        await show_groups_menu(update, ctx)

    # ── Schedule ──────────────────────────────────────────────────────────────
    elif d == "a_schedule":
        await q.answer(); await show_schedule_menu(update, ctx)
    elif d == "a_togglesched":
        await q.answer()
        data = load_data(); data["schedule_enabled"] = not data["schedule_enabled"]; save_data(data)
        from handlers.posting import reschedule
        reschedule(ctx.application)
        await show_schedule_menu(update, ctx)
    elif d == "a_editsched":
        await q.answer()
        ctx.user_data["a_awaiting"] = "schedule_time"
        await q.edit_message_text("⏰ Send time in `HH:MM` UTC format (e.g. `08:30`):", parse_mode="Markdown")

    # ── Post now ──────────────────────────────────────────────────────────────
    elif d == "a_postnow":
        await q.answer()
        await q.edit_message_text("📤 Posting to all groups, please wait…")
        from handlers.posting import post_to_all
        await post_to_all(ctx.application)
        await q.edit_message_text(
            "✅ Done! Posted to all groups.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="a_menu")]]),
        )

    # ── Preview ───────────────────────────────────────────────────────────────
    elif d == "a_preview":
        await q.answer()
        await q.edit_message_text("👁 Sending preview to you now…")
        from handlers.posting import post_to_chat
        await post_to_chat(ctx.application, q.from_user.id, "Preview")
        await ctx.bot.send_message(
            q.from_user.id,
            "👁 That's how the post looks!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="a_menu")]]),
        )

    # ── Broadcast ─────────────────────────────────────────────────────────────
    elif d == "a_broadcast":
        await q.answer()
        ctx.user_data["a_awaiting"] = "broadcast"
        await q.edit_message_text("📣 *Broadcast Message*\n\nSend the message to broadcast to ALL groups:", parse_mode="Markdown")

    # ── Stats ─────────────────────────────────────────────────────────────────
    elif d == "a_stats":
        await q.answer()
        data  = load_data()
        total = data.get("total_posts", 0)
        users = data.get("users", {})
        total_users     = len(users)
        total_balance   = sum(u.get("balance", 0) for u in users.values())
        total_referrals = sum(u.get("referrals", 0) for u in users.values())
        pending_w = sum(1 for u in users.values() if u.get("pending_withdraw"))
        pending_s = sum(1 for u in users.values() if u.get("screenshot_pending"))
        ppg = data.get("posts_per_group", {})
        lines = [
            f"📊 *Statistics*\n",
            f"📤 Total posts: {total}",
            f"👤 Total users: {total_users}",
            f"👥 Total referrals paid: {total_referrals}",
            f"💵 Total ETB owed: {total_balance}",
            f"⏳ Pending payouts: {pending_w}",
            f"📸 Pending screenshots: {pending_s}",
            "",
        ]
        for gname, cnt in list(ppg.items())[:10]:
            lines.append(f"• {gname}: {cnt} posts")
        await q.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="a_menu")]]),
            parse_mode="Markdown",
        )

    # ── Backup ────────────────────────────────────────────────────────────────
    elif d == "a_backup":
        await q.answer()
        import json
        data = load_data()
        backup_bytes = json.dumps(data, indent=2, ensure_ascii=False).encode()
        await ctx.bot.send_document(
            q.from_user.id,
            document=backup_bytes,
            filename="backup_data.json",
            caption="💾 Backup of bot data. Send this file back to restore.",
        )
        # FIX #7: set awaiting=restore AFTER the edit so pressing Back doesn't arm the restore state
        await q.edit_message_text(
            "💾 Backup sent!\n\nTo restore, send the backup JSON file in this chat.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="a_menu")]]),
        )
        ctx.user_data["a_awaiting"] = "restore"

    # ── Watermark ─────────────────────────────────────────────────────────────
    elif d == "a_watermark":
        await q.answer()
        data = load_data()
        wm   = data.get("watermark", "") or "_Not set_"
        ctx.user_data["a_awaiting"] = "watermark"
        await q.edit_message_text(
            f"🏷 *Watermark*\n\nCurrent: {wm}\n\nSend new watermark text (or `clear` to remove):",
            parse_mode="Markdown",
        )

    # ── NEW: User Management ───────────────────────────────────────────────────
    elif d == "a_users":
        await q.answer(); await show_users_menu(update, ctx)
    elif d == "a_exportusers":
        await q.answer()
        import json
        data  = load_data()
        users = data.get("users", {})
        lines = ["user_id,name,balance,referrals,pending_withdraw,lang"]
        for uid, u in users.items():
            lines.append(f"{uid},{u.get('name','')},{u.get('balance',0)},"
                         f"{u.get('referrals',0)},{u.get('pending_withdraw',False)},{u.get('lang','en')}")
        csv_bytes = "\n".join(lines).encode()
        await ctx.bot.send_document(q.from_user.id, document=csv_bytes, filename="users.csv",
                                    caption="👤 All users export")
        await q.answer("✅ Exported!", show_alert=True)
    elif d == "a_banuser":
        await q.answer()
        ctx.user_data["a_awaiting"] = "ban_user_id"
        await q.edit_message_text("🚫 Send the *User ID* to ban:", parse_mode="Markdown")
    elif d == "a_unbanuser":
        await q.answer()
        ctx.user_data["a_awaiting"] = "unban_user_id"
        await q.edit_message_text("✅ Send the *User ID* to unban:", parse_mode="Markdown")

    # ── NEW: Settings ─────────────────────────────────────────────────────────
    elif d == "a_settings":
        await q.answer(); await show_settings_menu(update, ctx)
    elif d == "a_set_reward":
        await q.answer()
        ctx.user_data["a_awaiting"] = "referral_reward"
        await q.edit_message_text("🎁 Send the new referral reward amount in ETB (e.g. `50`):", parse_mode="Markdown")
    elif d == "a_toggle_broadcast":
        await q.answer()
        data = load_data()
        data["broadcast_on_post"] = not data.get("broadcast_on_post", False)
        save_data(data)
        await show_settings_menu(update, ctx)

    # ── AI Moderation ─────────────────────────────────────────────────────────
    elif d == "a_ai_moderation":
        await q.answer(); await show_ai_moderation_menu(update, ctx)
    elif d == "a_toggle_ai":
        await q.answer()
        data = load_data()
        data["ai_moderation_enabled"] = not data.get("ai_moderation_enabled", True)
        save_data(data)
        await show_ai_moderation_menu(update, ctx)
    elif d == "a_upload_reference":
        await q.answer()
        ctx.user_data["a_awaiting"] = "reference_screenshot"
        await q.edit_message_text(
            "📸 *Upload Reference Screenshot*\n\n"
            "Send the *real* installation screenshot of your app.\n"
            "This is what Groq AI will compare against every user submission.\n\n"
            "Send it as a photo now:",
            parse_mode="Markdown",
        )
    elif d == "a_view_reference":
        await q.answer()
        import os
        if os.path.exists("reference_screenshot.jpg"):
            await ctx.bot.send_photo(
                q.from_user.id,
                photo=open("reference_screenshot.jpg", "rb"),
                caption="📸 Current reference screenshot used for AI validation.",
            )
            await show_ai_moderation_menu(update, ctx)
        else:
            await q.answer("❌ No reference screenshot set yet.", show_alert=True)
    elif d == "a_clear_reference":
        await q.answer()
        import os
        if os.path.exists("reference_screenshot.jpg"):
            os.remove("reference_screenshot.jpg")
            await q.answer("🗑 Reference screenshot cleared.", show_alert=True)
        await show_ai_moderation_menu(update, ctx)
    elif d == "a_reset_strikes":
        await q.answer()
        ctx.user_data["a_awaiting"] = "reset_strikes_uid"
        await q.edit_message_text(
            "🔄 Send the *User ID* to reset their strike count to 0:",
            parse_mode="Markdown",
        )

    # ── Referral approve/reject ───────────────────────────────────────────────
    elif d.startswith("approve_ref_"):
        # FIX #6 (from previous): credit goes to the REFERRER, not the submitter
        submitter_id = int(d.split("_")[-1])
        await q.answer()
        data     = load_data()
        submitter = get_user(data, submitter_id)
        referrer_id = submitter.get("referred_by")
        reward = data.get("referral_amount", 40)

        # Clear screenshot_pending flag on submitter
        submitter["screenshot_pending"] = False
        save_user(data, submitter_id, submitter)

        if referrer_id:
            referrer = get_user(data, referrer_id)
            referrer["balance"]   = referrer.get("balance", 0) + reward
            referrer["referrals"] = referrer.get("referrals", 0) + 1
            save_user(data, referrer_id, referrer)
            await q.edit_message_reply_markup(reply_markup=None)
            await q.message.reply_text(
                f"✅ Approved! Referrer {referrer_id} credited +{reward} ETB. "
                f"Balance: {referrer['balance']} ETB"
            )
            try:
                await ctx.bot.send_message(
                    referrer_id,
                    f"✅ Your referral was approved! +{reward} ETB added.\n"
                    f"💵 New balance: {referrer['balance']} ETB"
                )
            except Exception:
                pass
        else:
            await q.edit_message_reply_markup(reply_markup=None)
            await q.message.reply_text(
                f"✅ Approved for user {submitter_id} but they have no referrer — no credit awarded."
            )

        try:
            await ctx.bot.send_message(submitter_id, "✅ Your referral screenshot was approved!")
        except Exception:
            pass

    elif d.startswith("reject_ref_"):
        uid = int(d.split("_")[-1])
        await q.answer()
        data = load_data()
        user = get_user(data, uid)
        user["screenshot_pending"] = False
        save_user(data, uid, user)
        await q.edit_message_reply_markup(reply_markup=None)
        await q.message.reply_text(f"❌ Rejected referral screenshot from user {uid}.")
        try:
            await ctx.bot.send_message(uid, "❌ Your screenshot was rejected. Please make sure you installed the app and try again.")
        except Exception:
            pass

    # ── Payout approve/reject ─────────────────────────────────────────────────
    elif d.startswith("pay_approve_"):
        uid  = int(d.split("_")[-1])
        await q.answer()
        data = load_data()
        user = get_user(data, uid)
        paid = user.get("balance", 0)
        user["balance"]         = 0
        user["pending_withdraw"] = False
        save_user(data, uid, user)
        await q.edit_message_reply_markup(reply_markup=None)
        await q.message.reply_text(f"✅ Paid {paid} ETB to user {uid}. Balance reset to 0.")
        try:
            await ctx.bot.send_message(uid, f"✅ Your payout of {paid} ETB has been approved and sent!")
        except Exception:
            pass

    elif d.startswith("pay_reject_"):
        uid  = int(d.split("_")[-1])
        await q.answer()
        data = load_data()
        user = get_user(data, uid)
        user["pending_withdraw"] = False
        save_user(data, uid, user)
        await q.edit_message_reply_markup(reply_markup=None)
        await q.message.reply_text(f"❌ Rejected payout for user {uid}.")
        try:
            await ctx.bot.send_message(uid, "❌ Your payout request was rejected. Contact admin for details.")
        except Exception:
            pass

    else:
        await q.answer()


# ── Sub-menus ─────────────────────────────────────────────────────────────────
async def show_links_menu(update, ctx):
    data  = load_data(); links = data["apk_links"]; ai = data["active_link_index"]
    kb = []
    for i, lnk in enumerate(links):
        star = "⭐ " if i == ai else ""
        kb.append([
            InlineKeyboardButton(f"{star}{lnk['label']}", callback_data=f"a_setactive_{i}"),
            InlineKeyboardButton("🗑", callback_data=f"a_dellink_{i}"),
        ])
    kb += [[InlineKeyboardButton("➕ Add Link", callback_data="a_addlink")],
           [InlineKeyboardButton("⬅️ Back",    callback_data="a_menu")]]
    await update.callback_query.edit_message_text(
        "📎 *APK Links* — tap to set active (⭐)",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def show_image_menu(update, ctx):
    data = load_data(); img = data.get("image_url","") or "_Not set_"
    kb = [
        [InlineKeyboardButton("🔗 Set URL",    callback_data="a_setimgurl"),
         InlineKeyboardButton("📤 Upload",     callback_data="a_uploadimg")],
        [InlineKeyboardButton("🗑 Clear",      callback_data="a_clearimg")],
        [InlineKeyboardButton("⬅️ Back",       callback_data="a_menu")],
    ]
    await update.callback_query.edit_message_text(
        f"🖼 *Image*\n\nCurrent: `{img[:80]}`",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def show_video_menu(update, ctx):
    data = load_data(); vid = data.get("video_url","") or "_Not set_"
    kb = [
        [InlineKeyboardButton("🔗 Set URL",    callback_data="a_setvidurl")],
        [InlineKeyboardButton("🗑 Clear",      callback_data="a_clearvid")],
        [InlineKeyboardButton("⬅️ Back",       callback_data="a_menu")],
    ]
    await update.callback_query.edit_message_text(
        f"📹 *Video*\n\nCurrent: `{vid[:80]}`",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def show_caption_menu(update, ctx):
    data = load_data()
    kb   = [[InlineKeyboardButton("✏️ Edit Caption", callback_data="a_editcaption")]]
    for i, w in enumerate(data.get("extra_words",[])):
        kb.append([InlineKeyboardButton(w[:35], callback_data="noop"),
                   InlineKeyboardButton("🗑", callback_data=f"a_delword_{i}")])
    kb += [[InlineKeyboardButton("➕ Add Line", callback_data="a_addword")],
           [InlineKeyboardButton("⬅️ Back",    callback_data="a_menu")]]
    await update.callback_query.edit_message_text(
        f"💬 *Caption*\n\n{data.get('caption','')}\n\nExtra lines: {len(data.get('extra_words',[]))}",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def show_langcaptions_menu(update, ctx):
    data = load_data(); lang_captions = data.get("lang_captions", {})
    kb = []
    for code, name in LANGUAGES.items():
        has = "✅" if code in lang_captions else "➕"
        kb.append([InlineKeyboardButton(f"{has} {name}", callback_data=f"a_editlangcap_{code}")])
    kb.append([InlineKeyboardButton("⬅️ Back", callback_data="a_menu")])
    await update.callback_query.edit_message_text(
        "🌍 *Language Captions*\n\nSet a custom caption per language.",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def show_version_menu(update, ctx):
    data = load_data()
    kb = [
        [InlineKeyboardButton("📦 Edit Version",    callback_data="a_editversion")],
        [InlineKeyboardButton("📝 Edit Changelog",  callback_data="a_editchangelog")],
        [InlineKeyboardButton("⬅️ Back",            callback_data="a_menu")],
    ]
    await update.callback_query.edit_message_text(
        f"📦 *Version & Changelog*\n\nVersion: `v{data.get('version','1.0.0')}`\n\nChangelog:\n{data.get('changelog','—')}",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def show_channel_menu(update, ctx):
    data = load_data()
    ch   = data.get("required_channel_username","@mychannel")
    cid  = data.get("required_channel_id", 0)
    kb = [
        [InlineKeyboardButton("📝 Set Username",  callback_data="a_setchannel")],
        [InlineKeyboardButton("🔢 Set Channel ID",callback_data="a_setchannelid")],
        [InlineKeyboardButton("⬅️ Back",          callback_data="a_menu")],
    ]
    await update.callback_query.edit_message_text(
        f"🔐 *Channel Settings*\n\nUsername: `{ch}`\nID: `{cid}`\n\n_Both are needed for accurate membership check._",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def show_groups_menu(update, ctx):
    data   = load_data(); groups = data["groups"]
    kb = []
    for i, g in enumerate(groups[:20]):
        kb.append([InlineKeyboardButton(g["title"][:30], callback_data="noop"),
                   InlineKeyboardButton("🗑", callback_data=f"a_delgroup_{i}")])
    kb.append([InlineKeyboardButton("⬅️ Back", callback_data="a_menu")])
    await update.callback_query.edit_message_text(
        f"👥 *Groups & Channels*\n\nTotal: {len(groups)}\n\nBot auto-registers when added to any group/channel.",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def show_schedule_menu(update, ctx):
    data = load_data(); h, m = data["schedule_hour"], str(data["schedule_minute"]).zfill(2)
    enbl = data["schedule_enabled"]
    kb = [
        [InlineKeyboardButton(f"{'✅ Enabled' if enbl else '❌ Disabled'} — Toggle", callback_data="a_togglesched")],
        [InlineKeyboardButton("⏰ Change Time", callback_data="a_editsched")],
        [InlineKeyboardButton("⬅️ Back",        callback_data="a_menu")],
    ]
    await update.callback_query.edit_message_text(
        f"⏰ *Schedule*\n\nTime: `{h}:{m} UTC`\nStatus: {'✅ ON' if enbl else '❌ OFF'}",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def show_users_menu(update, ctx):
    """NEW: user management submenu."""
    data  = load_data()
    users = data.get("users", {})
    banned = len(data.get("banned_users", {}))
    pending_w = sum(1 for u in users.values() if u.get("pending_withdraw"))
    pending_s = sum(1 for u in users.values() if u.get("screenshot_pending"))
    kb = [
        [InlineKeyboardButton("📤 Export CSV",   callback_data="a_exportusers")],
        [InlineKeyboardButton("🚫 Ban User",     callback_data="a_banuser"),
         InlineKeyboardButton("✅ Unban User",   callback_data="a_unbanuser")],
        [InlineKeyboardButton("⬅️ Back",         callback_data="a_menu")],
    ]
    await update.callback_query.edit_message_text(
        f"👤 *User Management*\n\n"
        f"Total users: {len(users)}\n"
        f"Banned: {banned}\n"
        f"⏳ Pending payouts: {pending_w}\n"
        f"📸 Pending screenshots: {pending_s}",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def show_settings_menu(update, ctx):
    """Bot settings submenu."""
    import os
    data   = load_data()
    reward = data.get("referral_amount", 40)
    bcast  = "✅ ON" if data.get("broadcast_on_post") else "❌ OFF"
    ai_on  = "✅ ON" if data.get("ai_moderation_enabled", True) else "❌ OFF"
    ref_set = "✅ Set" if os.path.exists("reference_screenshot.jpg") else "❌ Not set"
    kb = [
        [InlineKeyboardButton(f"🎁 Referral Reward: {reward} ETB",  callback_data="a_set_reward")],
        [InlineKeyboardButton(f"📢 Notify users on post: {bcast}",  callback_data="a_toggle_broadcast")],
        [InlineKeyboardButton(f"🤖 AI Moderation: {ai_on}  |  Ref: {ref_set}", callback_data="a_ai_moderation")],
        [InlineKeyboardButton("⬅️ Back", callback_data="a_menu")],
    ]
    await update.callback_query.edit_message_text(
        "⚙️ *Bot Settings*\n\nConfigure bot behaviour.",
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def show_ai_moderation_menu(update, ctx):
    """AI screenshot moderation submenu."""
    import os
    data    = load_data()
    enabled = data.get("ai_moderation_enabled", True)
    ref_ok  = os.path.exists("reference_screenshot.jpg")

    status_lines = [
        f"🤖 *AI Screenshot Moderation*\n",
        f"Status: {'✅ Enabled' if enabled else '❌ Disabled'}",
        f"Reference image: {'✅ Uploaded' if ref_ok else '❌ Not set'}",
        f"Strikes to ban: 3",
        "",
        "_When enabled, every user screenshot is compared to your reference_"
        "_image by Groq AI before reaching you. Fakes are rejected automatically._",
        "",
        "_If Groq is down, screenshots pass through to you as normal._",
    ]

    kb = [
        [InlineKeyboardButton(
            f"{'❌ Disable' if enabled else '✅ Enable'} AI Moderation",
            callback_data="a_toggle_ai"
        )],
        [InlineKeyboardButton("📸 Upload Reference Screenshot", callback_data="a_upload_reference")],
    ]
    if ref_ok:
        kb.append([
            InlineKeyboardButton("👁 View Reference",  callback_data="a_view_reference"),
            InlineKeyboardButton("🗑 Clear Reference", callback_data="a_clear_reference"),
        ])
    kb.append([InlineKeyboardButton("🔄 Reset User Strikes", callback_data="a_reset_strikes")])
    kb.append([InlineKeyboardButton("⬅️ Back", callback_data="a_settings")])

    await update.callback_query.edit_message_text(
        "\n".join(status_lines),
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown",
    )


# ── Admin text/file message handler ───────────────────────────────────────────
async def admin_message_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id) or update.effective_chat.type != "private":
        return

    awaiting = ctx.user_data.get("a_awaiting")
    if not awaiting:
        return

    if update.message.photo and awaiting == "image_upload":
        ctx.user_data.pop("a_awaiting", None)
        photo = update.message.photo[-1]
        file  = await photo.get_file()
        data  = load_data(); data["image_url"] = file.file_path; save_data(data)
        await update.message.reply_text("✅ Image uploaded!", reply_markup=_back_kb())
        return

    # ── Reference screenshot for AI moderation ────────────────────────────────
    if update.message.photo and awaiting == "reference_screenshot":
        ctx.user_data.pop("a_awaiting", None)
        photo = update.message.photo[-1]
        file  = await photo.get_file()
        # Download and save locally as reference_screenshot.jpg
        await file.download_to_drive("reference_screenshot.jpg")
        await update.message.reply_text(
            "✅ *Reference screenshot saved!*\n\n"
            "Groq AI will now compare every user submission against this image.\n"
            "You can view or replace it anytime from the AI Moderation menu.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🤖 AI Moderation Settings", callback_data="a_ai_moderation")
            ]])
        )
        return

    if update.message.document and awaiting == "restore":
        ctx.user_data.pop("a_awaiting", None)
        import json
        file    = await update.message.document.get_file()
        content = await file.download_as_bytearray()
        try:
            restored = json.loads(content.decode())
            save_data(restored)
            await update.message.reply_text("✅ Data restored successfully!", reply_markup=_back_kb())
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to restore: {e}")
        return

    text = update.message.text.strip() if update.message.text else ""
    if not text:
        return

    data = load_data()
    ctx.user_data.pop("a_awaiting", None)

    if awaiting == "link_label":
        ctx.user_data["a_pending_label"] = text
        ctx.user_data["a_awaiting"]      = "link_url"
        await update.message.reply_text(f"✅ Label: *{text}*\n\nNow send the APK download URL:", parse_mode="Markdown")
        return
    elif awaiting == "link_url":
        label = ctx.user_data.pop("a_pending_label", "Unnamed")
        data["apk_links"].append({"label": label, "url": text})
    elif awaiting == "image_url":
        data["image_url"] = text
    elif awaiting == "video_url":
        data["video_url"] = text
    elif awaiting == "caption":
        data["caption"] = text
    elif awaiting == "extra_word":
        data.setdefault("extra_words", []).append(text)
    elif awaiting == "lang_caption":
        lang = ctx.user_data.pop("a_lang_edit", "en")
        data.setdefault("lang_captions", {})[lang] = text
    elif awaiting == "version":
        data["version"] = text.lstrip("v")
    elif awaiting == "changelog":
        data["changelog"] = text
    elif awaiting == "channel_username":
        data["required_channel_username"] = text if text.startswith("@") else f"@{text}"
    elif awaiting == "channel_id":
        try:
            data["required_channel_id"] = int(text)
        except ValueError:
            await update.message.reply_text("❌ Invalid ID. Must be a number like `-1001234567890`")
            return
    elif awaiting == "schedule_time":
        try:
            hh, mm = text.split(":")
            hh, mm = int(hh), int(mm)
            assert 0 <= hh <= 23 and 0 <= mm <= 59
            data["schedule_hour"]   = hh
            data["schedule_minute"] = mm
            save_data(data)
            from handlers.posting import reschedule
            reschedule(ctx.application)
            await update.message.reply_text(f"✅ Schedule set to `{hh}:{str(mm).zfill(2)} UTC`",
                                            parse_mode="Markdown", reply_markup=_back_kb())
            return
        except Exception:
            await update.message.reply_text("❌ Invalid format. Use HH:MM (e.g. 09:30)")
            return
    elif awaiting == "watermark":
        data["watermark"] = "" if text.lower() == "clear" else text
    elif awaiting == "broadcast":
        groups = data.get("groups", [])
        ok, fail = 0, 0
        for g in groups:
            try:
                await ctx.bot.send_message(g["id"], text); ok += 1
            except Exception:
                fail += 1
        await update.message.reply_text(f"📣 Broadcast done!\n✅ Sent: {ok}\n❌ Failed: {fail}",
                                        reply_markup=_back_kb())
        return
    elif awaiting == "referral_reward":
        try:
            amount = int(text)
            assert amount > 0
            data["referral_amount"] = amount
        except Exception:
            await update.message.reply_text("❌ Invalid amount. Send a positive integer.")
            return
    elif awaiting == "ban_user_id":
        try:
            uid = int(text)
            data.setdefault("banned_users", {})[str(uid)] = True
            await update.message.reply_text(f"🚫 User {uid} has been banned.", reply_markup=_back_kb())
            try:
                await ctx.bot.send_message(uid, "🚫 You have been banned from this bot.")
            except Exception:
                pass
        except ValueError:
            await update.message.reply_text("❌ Invalid User ID.")
        return
    elif awaiting == "unban_user_id":
        try:
            uid = int(text)
            data.setdefault("banned_users", {}).pop(str(uid), None)
            await update.message.reply_text(f"✅ User {uid} has been unbanned.", reply_markup=_back_kb())
        except ValueError:
            await update.message.reply_text("❌ Invalid User ID.")
        return

    elif awaiting == "reset_strikes_uid":
        try:
            uid  = int(text)
            user = get_user(data, uid)
            old  = user.get("screenshot_strikes", 0)
            user["screenshot_strikes"] = 0
            save_user(data, uid, user)
            await update.message.reply_text(
                f"✅ Reset strikes for user `{uid}` from {old} → 0.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🤖 AI Moderation", callback_data="a_ai_moderation")
                ]])
            )
        except ValueError:
            await update.message.reply_text("❌ Invalid User ID.")
        return

    elif awaiting == "referral_reward":
        try:
            amount = int(text)
            assert amount > 0
            data["referral_amount"] = amount
        except Exception:
            await update.message.reply_text("❌ Invalid amount. Send a positive integer.")
            return

    save_data(data)
    await update.message.reply_text("✅ Saved!", reply_markup=_back_kb())


def _back_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="a_menu")]])
