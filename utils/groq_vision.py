"""
Groq vision-based screenshot validator.

Flow:
  1. Admin uploads a reference screenshot of the real app via the admin panel.
     It's saved as "reference_screenshot.jpg" in the bot's working directory.
  2. When a user submits a screenshot, both images are base64-encoded and sent
     to the Groq vision model (llama-4-scout-17b-16e-instruct).
  3. Groq decides: VALID or INVALID, with a short reason.
  4. On failure / timeout → fallback (treat as valid, pass to admin).
  5. 3 invalid submissions → user is auto-banned.
"""

import os
import base64
import logging
import httpx

logger = logging.getLogger(__name__)

GROQ_API_KEY       = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL         = "meta-llama/llama-4-scout-17b-16e-instruct"
REFERENCE_IMG_PATH = "reference_screenshot.jpg"
TIMEOUT_SECONDS    = 20


def _encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _encode_bytes(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")


async def validate_screenshot(user_img_bytes: bytes) -> tuple[bool, str]:
    """
    Compare user screenshot against the reference image using Groq vision.

    Returns:
        (is_valid: bool, reason: str)
        is_valid=True  → looks like a real install screenshot
        is_valid=False → looks fake / wrong app / manipulated
        is_valid=True  → also returned on API error (safe fallback)
    """

    # ── Fallback: no API key or no reference image ────────────────────────────
    if not GROQ_API_KEY:
        logger.warning("GROQ_API_KEY not set — skipping AI validation (fallback: pass)")
        return True, "AI validation skipped (no API key)"

    if not os.path.exists(REFERENCE_IMG_PATH):
        logger.warning("Reference screenshot not set — skipping AI validation (fallback: pass)")
        return True, "AI validation skipped (no reference image)"

    try:
        ref_b64  = _encode_image(REFERENCE_IMG_PATH)
        user_b64 = _encode_bytes(user_img_bytes)

        prompt = (
            "You are a fraud detection assistant for a mobile app referral system.\n\n"
            "You are given TWO images:\n"
            "  Image 1 (REFERENCE): The genuine, expected installation screenshot of our app.\n"
            "  Image 2 (SUBMISSION): A screenshot submitted by a user claiming to have installed the app.\n\n"
            "Your job is to decide whether Image 2 is a VALID proof of installation.\n\n"
            "A submission is VALID if:\n"
            "- It shows the same app as the reference (same UI, same app name/icon, same screens)\n"
            "- It appears to be a real screenshot (not a photo of a screen, not edited/cropped heavily)\n"
            "- It is not a duplicate or copy of the reference image itself\n\n"
            "A submission is INVALID if:\n"
            "- It shows a different app entirely\n"
            "- It is clearly edited, fake, or a screenshot of a screenshot\n"
            "- It is the reference image itself (copy-paste fraud)\n"
            "- It shows an unrelated screen (e.g. home screen, blank screen, another app)\n\n"
            "Reply ONLY in this exact format (no extra text):\n"
            "RESULT: VALID\n"
            "REASON: <one short sentence>\n\n"
            "or\n\n"
            "RESULT: INVALID\n"
            "REASON: <one short sentence>"
        )

        payload = {
            "model": GROQ_MODEL,
            "max_tokens": 100,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{ref_b64}"
                            }
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{user_b64}"
                            }
                        },
                    ]
                }
            ]
        }

        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type":  "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            result_text = resp.json()["choices"][0]["message"]["content"].strip()

        logger.info(f"Groq vision response: {result_text}")

        # Parse response
        is_valid = "RESULT: VALID" in result_text
        reason   = ""
        for line in result_text.splitlines():
            if line.startswith("REASON:"):
                reason = line[len("REASON:"):].strip()
                break

        return is_valid, reason

    except httpx.TimeoutException:
        logger.warning("Groq API timeout — fallback: pass screenshot to admin")
        return True, "AI validation timed out (passed to admin)"

    except Exception as e:
        logger.error(f"Groq vision error: {e}")
        return True, f"AI validation error (passed to admin): {e}"
