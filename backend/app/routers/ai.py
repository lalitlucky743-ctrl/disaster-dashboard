import os

from fastapi import APIRouter, Depends, HTTPException
from groq import Groq

from ..dependencies import get_current_user
from ..schemas import AIRequest, AIResponse


router = APIRouter()


SYSTEM_PROMPT = """
You are DisasterIQ, an AI disaster intelligence assistant.

You help users understand:

- floods
- landslides
- earthquakes
- forest fires
- heavy rainfall
- disaster preparedness
- disaster risk
- geographic risk patterns

Give concise, practical and structured answers.

Important rules:

1. Do not claim information is live unless live
   data has actually been supplied by the system.

2. If current live information is unavailable,
   clearly say that the answer is based on general
   risk information.

3. Do not invent real-time alerts, weather data,
   evacuation orders, government announcements,
   sensor readings, or emergency conditions.

4. Keep answers practical and easy to understand.

5. For disaster preparedness questions, provide
   clear safety-oriented steps.

6. Avoid unnecessary technical jargon.
"""


@router.post(
    "/ask",
    response_model=AIResponse,
)
def ask_ai(
    data: AIRequest,
    current_user=Depends(get_current_user),
):

    # =====================================================
    # GET GROQ API KEY
    # =====================================================

    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="GROQ_API_KEY is not configured.",
        )

    # =====================================================
    # CREATE GROQ CLIENT
    # =====================================================

    try:

        client = Groq(
            api_key=api_key
        )

        # =================================================
        # BUILD USER MESSAGE
        # =================================================

        user_message = data.question.strip()

        if data.location:

            user_message = (
                f"Selected location: "
                f"{data.location.strip()}\n\n"
                f"Question: "
                f"{data.question.strip()}"
            )

        # =================================================
        # GROQ REQUEST
        # =================================================

        response = client.chat.completions.create(

           model=os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-120b",
),
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": user_message,
                },
            ],

            temperature=0.2,

            max_tokens=700,
        )

        # =================================================
        # GET AI RESPONSE
        # =================================================

        ai_message = (
            response
            .choices[0]
            .message
            .content
        )

        if not ai_message:

            raise HTTPException(
                status_code=500,
                detail="AI returned an empty response.",
            )

        # =================================================
        # RETURN RESPONSE
        # =================================================

        return {
            "answer": ai_message,
            "status": "ready",
        }

    # =====================================================
    # GROQ ERROR
    # =====================================================

    except HTTPException:
        raise

    except Exception as e:

        print(
            "Groq error:",
            repr(e),
        )

        raise HTTPException(
            status_code=500,
            detail="AI service temporarily unavailable.",
        )