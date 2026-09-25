"""
LearnOrbit AI Service
Unified multi-provider AI abstraction (OpenAI, Gemini, Claude, Grok, HuggingFace)
"""

import json
import re
import requests
from typing import Optional


# ---------------------------------------------------------------------------
# Provider-specific callers
# ---------------------------------------------------------------------------

def _call_openai_compatible(base_url: str, api_key: str, model: str, messages: list,
                             system: str = None, temperature: float = 0.7,
                             max_tokens: int = 2048) -> str:
    """Works for OpenAI, xAI Grok (same REST shape)."""
    payload_messages = []
    if system:
        payload_messages.append({"role": "system", "content": system})
    payload_messages.extend(messages)

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": payload_messages,
                "temperature": temperature, "max_tokens": max_tokens}

    resp = requests.post(f"{base_url}/chat/completions", headers=headers,
                         json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_anthropic(api_key: str, model: str, messages: list,
                    system: str = None, max_tokens: int = 2048) -> str:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if system:
        payload["system"] = system

    resp = requests.post("https://api.anthropic.com/v1/messages",
                         headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def _call_gemini(api_key: str, model: str, messages: list,
                 system: str = None, max_tokens: int = 2048) -> str:
    """Google Gemini via REST."""
    parts = []
    if system:
        parts.append({"text": f"[System instruction]: {system}\n\n"})

    contents = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})

    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent")
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    payload = {
        "contents": contents,
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7},
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


def _call_huggingface(api_key: str, model: str, messages: list,
                      system: str = None, max_tokens: int = 1024) -> str:
    """Call Hugging Face's current OpenAI-compatible Inference Providers API."""
    payload_messages = []
    if system:
        payload_messages.append({"role": "system", "content": system})
    for m in messages:
        payload_messages.append({"role": m["role"], "content": m["content"]})

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": payload_messages,
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }
    resp = requests.post("https://router.huggingface.co/v1/chat/completions",
                         headers=headers, json=payload, timeout=90)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Unified caller
# ---------------------------------------------------------------------------

def call_ai(provider: str, model: str, api_key: str, messages: list,
            system: str = None, max_tokens: int = 2048) -> str:
    """Route to correct provider and return assistant reply string."""
    provider = provider.lower()
    try:
        if provider == "openai":
            return _call_openai_compatible(
                "https://api.openai.com/v1", api_key, model, messages, system, max_tokens=max_tokens)
        elif provider == "xai":
            return _call_openai_compatible(
                "https://api.x.ai/v1", api_key, model, messages, system, max_tokens=max_tokens)
        elif provider == "anthropic":
            return _call_anthropic(api_key, model, messages, system, max_tokens)
        elif provider == "google":
            return _call_gemini(api_key, model, messages, system, max_tokens)
        elif provider == "huggingface":
            return _call_huggingface(api_key, model, messages, system, max_tokens)
        else:
            return f"[LearnOrbit] Unknown AI provider: {provider}"
    except requests.exceptions.HTTPError as e:
        response = e.response
        # Preserve the actual provider status/body; those details explain 400s
        # such as unsupported models and malformed requests.
        match = re.search(r"\b([45]\d{2}) Client Error:", str(e))
        status = response.status_code if response is not None else (int(match.group(1)) if match else "?")
        detail = response.text[:1000] if response is not None else str(e)
        lowered_detail = detail.lower()
        invalid_key_markers = (
            "api_key_invalid",
            "api key not valid",
            "invalid api key",
            "incorrect api key",
            "incorrect api key provided",
            "invalid x-api-key",
            "authentication_error",
        )
        if status == 401 or any(marker in lowered_detail for marker in invalid_key_markers):
            return "Invalid API key. Check that this is a key for the selected provider."
        if status == 403:
            return f"API key was rejected or lacks permission: {detail[:400]}"
        elif status == 429:
            return "Rate limit hit. Please wait a moment and try again."
        else:
            return f"API error ({status}): {detail[:500]}"
    except Exception as e:
        return f"Unexpected error: {str(e)[:300]}"


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

TUTOR_SYSTEM = """You are LearnOrbit — an expert AI tutor and learning coach. Your personality is warm, encouraging, a little playful, and deeply knowledgeable.

TEACHING RULES:
1. Explain concepts with DEPTH: theory → intuition → examples → applications.
2. Use numbered steps for processes. Use bullet points for lists.
3. Format ALL mathematical expressions in LaTeX: inline as $...$ and block as $$...$$
4. After every explanation, end with a quick comprehension check or a thought-provoking question.
5. Detect misconceptions gently. Never embarrass the learner.
6. Adapt difficulty based on user responses (note their level in [ADAPT: level] tags).
7. Keep responses structured and scannable.
8. Add a relevant fun fact or real-world application when appropriate.
9. Be encouraging! Celebrate progress with emojis sparingly but warmly.

TOPIC CONTEXT: {topic}
DIFFICULTY LEVEL: {difficulty}
LEARNING STYLE: {style}
"""

QUIZ_SYSTEM = """You are LearnOrbit Quiz Engine. Generate exactly 10 multiple-choice questions for the topic.

OUTPUT FORMAT — strict JSON only, no markdown, no preamble:
{{
  "questions": [
    {{
      "id": 1,
      "question": "question text with LaTeX where needed ($formula$)",
      "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
      "correct": "A",
      "explanation": "Why this is correct and why others are wrong",
      "difficulty": "easy|medium|hard",
      "misconception_check": "common wrong belief this tests"
    }}
  ]
}}

Mix difficulties: 3 easy, 4 medium, 3 hard. Make distractors realistic.
Topic: {topic}
Key areas covered in session: {key_areas}
"""

MISCONCEPTION_SYSTEM = """You are LearnOrbit Misconception Detector.
Given a user's answer/explanation and the correct concept, identify if there's a misconception.

OUTPUT FORMAT — strict JSON only:
{{
  "has_misconception": true/false,
  "misconception": "what the user wrongly believes (null if none)",
  "root_cause": "why this misconception arises (null if none)",
  "correction": "gentle, clear correction (null if none)",
  "confidence": 0.0-1.0
}}
"""

NOTES_SYSTEM = """You are LearnOrbit Notes Generator.
Create clear, accurate notes that a student can learn from without rereading the chat.

TEACHING AND ACCURACY RULES:
- Start with a plain-language overview and 3–5 concrete learning goals.
- Build ideas in order: prerequisites or context, core idea, how it works,
  then use.
- For each important concept, give a precise definition, an intuitive
  explanation, and a short example. Explain technical terms the first time.
- Include one worked example when the topic supports it; show the reasoning in
  steps and explain why each step is valid.
- For formulas, define every symbol and unit, state when the formula applies,
  and use LaTeX for mathematical notation ($inline$ or $$block$$).
- Distinguish what the conversation covered from useful background. Fill small
  gaps with standard facts, but do not invent claims, sources, or learner results.
- Prefer specific explanations over repeated summaries or motivational filler.
  Keep paragraphs short; use lists when they improve scanning.
- Omit sections that do not apply instead of adding generic filler.

OUTPUT FORMAT — Markdown only:
# {topic}

## At a glance
[A concise overview, then 3–5 learning goals]

## Build the idea
[Prerequisites and core concepts in a sensible teaching order]

## See it in action
[Worked example, demonstration, or concrete case]

## Apply it
[Practical uses and when this knowledge is useful]

## Common confusions
[Likely mistakes, why they happen, and how to correct them]

## Quick review
[A short checklist of the essential takeaways]

## Check your understanding
[3–5 questions, followed by a clearly labeled answer key]

## Where to go next
[Two or three closely related topics, with a brief reason for each]

Topic: {topic}
Session coverage and context:
{summary}
"""

LEARNING_STYLE_SYSTEM = """Analyze the user's conversation and infer their learning style.
OUTPUT FORMAT — strict JSON only:
{{
  "style": "visual|analytical|narrative|balanced",
  "difficulty_suggestion": "beginner|intermediate|advanced",
  "engagement_score": 0.0-1.0,
  "observations": ["observation 1", "observation 2"]
}}
"""


def build_tutor_system(topic: str, difficulty: str = "beginner", style: str = "balanced") -> str:
    return TUTOR_SYSTEM.format(topic=topic, difficulty=difficulty, style=style)


def generate_quiz(provider, model, api_key, topic, key_areas=""):
    system = QUIZ_SYSTEM.format(topic=topic, key_areas=key_areas or topic)
    messages = [{"role": "user", "content": f"Generate 10 MCQ questions for: {topic}"}]
    raw = call_ai(provider, model, api_key, messages, system=system, max_tokens=3000)
    # Strip markdown fences if present
    raw = re.sub(r"```(?:json)?|```", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Attempt to extract JSON object
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {"questions": [], "error": "Failed to parse quiz JSON"}


def detect_misconception(provider, model, api_key, topic, user_text, correct_concept):
    system = MISCONCEPTION_SYSTEM
    msg = f"Topic: {topic}\nUser said: {user_text}\nCorrect concept: {correct_concept}"
    messages = [{"role": "user", "content": msg}]
    raw = call_ai(provider, model, api_key, messages, system=system, max_tokens=512)
    raw = re.sub(r"```(?:json)?|```", "", raw).strip()
    try:
        return json.loads(raw)
    except Exception:
        return {"has_misconception": False}


def generate_notes(provider, model, api_key, topic, session_summary):
    system = NOTES_SYSTEM.format(topic=topic, summary=session_summary)
    messages = [{"role": "user", "content": f"Generate comprehensive study notes for: {topic}"}]
    return call_ai(provider, model, api_key, messages, system=system, max_tokens=3000)


def infer_learning_style(provider, model, api_key, conversation_text):
    messages = [{"role": "user", "content": f"Conversation:\n{conversation_text}"}]
    raw = call_ai(provider, model, api_key, messages, system=LEARNING_STYLE_SYSTEM, max_tokens=512)
    raw = re.sub(r"```(?:json)?|```", "", raw).strip()
    try:
        return json.loads(raw)
    except Exception:
        return {"style": "balanced", "difficulty_suggestion": "intermediate", "engagement_score": 0.5}
