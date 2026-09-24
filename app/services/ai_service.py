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
           f"{model}:generateContent?key={api_key}")
    payload = {
        "contents": contents,
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7},
    }
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


def _call_huggingface(api_key: str, model: str, messages: list,
                      system: str = None, max_tokens: int = 1024) -> str:
    """HuggingFace Inference API."""
    prompt_parts = []
    if system:
        prompt_parts.append(f"<|system|>\n{system}\n")
    for m in messages:
        tag = "user" if m["role"] == "user" else "assistant"
        prompt_parts.append(f"<|{tag}|>\n{m['content']}\n")
    prompt_parts.append("<|assistant|>\n")
    prompt = "".join(prompt_parts)

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"inputs": prompt, "parameters": {"max_new_tokens": max_tokens,
                                                  "temperature": 0.7, "return_full_text": False}}
    url = f"https://api-inference.huggingface.co/models/{model}"
    resp = requests.post(url, headers=headers, json=payload, timeout=90)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list) and data:
        return data[0].get("generated_text", "")
    return str(data)


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
        status = e.response.status_code if e.response else "?"
        if status == 401:
            return "❌ Invalid API key. Please check your credentials in Settings."
        elif status == 429:
            return "⏳ Rate limit hit. Please wait a moment and try again."
        else:
            return f"❌ API error ({status}): {e.response.text[:200] if e.response else str(e)}"
    except Exception as e:
        return f"❌ Unexpected error: {str(e)[:300]}"


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
Generate comprehensive structured study notes for the topic based on what was covered in the session.

FORMAT:
# Topic Title

## 📖 Core Concepts
[Bullet list of key ideas]

## 🧮 Key Formulas & Derivations
[All math in LaTeX: $inline$ and $$block$$]

## 💡 Intuition Builder
[Analogies and mental models]

## 🔗 Real-World Applications
[Concrete examples]

## ⚠️ Common Mistakes
[What to watch out for]

## 🧠 Quick Revision Checklist
- [ ] item 1
- [ ] item 2
...

## 📚 Suggested Next Topics
[2-3 related topics to explore]

Be thorough but clear. Use LaTeX properly for all math.
Topic: {topic}
Session summary: {summary}
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
