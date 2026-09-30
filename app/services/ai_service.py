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
                             system: str = None, temperature: Optional[float] = 0.7,
                             max_tokens: int = None) -> str:
    """Works for OpenAI, xAI Grok (same REST shape)."""
    payload_messages = []
    if system:
        payload_messages.append({"role": "system", "content": system})
    payload_messages.extend(messages)

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": payload_messages}
    if temperature is not None: payload["temperature"] = temperature
    if max_tokens is not None:
        if model.lower().startswith(("o1", "o3", "o4", "gpt-5", "gpt-6")):
            payload["max_completion_tokens"] = max_tokens
        else:
            payload["max_tokens"] = max_tokens

    resp = requests.post(f"{base_url}/chat/completions", headers=headers,
                         json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_anthropic(api_key: str, model: str, messages: list,
                    system: str = None, max_tokens: int = 8192, temperature: Optional[float] = 0.7) -> str:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if temperature is not None: payload["temperature"] = temperature
    if system:
        payload["system"] = system

    resp = requests.post("https://api.anthropic.com/v1/messages",
                         headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def _call_gemini(api_key: str, model: str, messages: list,
                 system: str = None, max_tokens: int = None, temperature: Optional[float] = 0.7) -> str:
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
        "generationConfig": {},
    }
    if temperature is not None: payload["generationConfig"]["temperature"] = temperature
    if max_tokens is not None: payload["generationConfig"]["maxOutputTokens"] = max_tokens
    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


def _call_huggingface(api_key: str, model: str, messages: list,
                      system: str = None, max_tokens: int = None, temperature: Optional[float] = 0.7) -> str:
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
    }
    if temperature is not None: payload["temperature"] = temperature
    if max_tokens is not None: payload["max_tokens"] = max_tokens
    resp = requests.post("https://router.huggingface.co/v1/chat/completions",
                         headers=headers, json=payload, timeout=90)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


# ---------------------------------------------------------------------------
# Unified caller
# ---------------------------------------------------------------------------

def call_ai(provider: str, model: str, api_key: str, messages: list,
            system: str = None, max_tokens: int = None, temperature: float = 0.7) -> str:
    """Route to correct provider and return assistant reply string."""
    provider = provider.lower()
    try:
        if provider == "openai":
            return _call_openai_compatible(
                "https://api.openai.com/v1", api_key, model, messages, system,
                temperature=temperature if supports_temperature(provider, model) else None,
                max_tokens=max_tokens)
        elif provider == "xai":
            return _call_openai_compatible(
                "https://api.x.ai/v1", api_key, model, messages, system, temperature=temperature, max_tokens=max_tokens)
        elif provider == "anthropic":
            return _call_anthropic(api_key, model, messages, system, max_tokens or 8192, temperature=temperature)
        elif provider == "google":
            return _call_gemini(api_key, model, messages, system, max_tokens, temperature=temperature)
        elif provider == "huggingface":
            return _call_huggingface(api_key, model, messages, system, max_tokens, temperature=temperature)
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


def supports_temperature(provider: str, model: str) -> bool:
    """Whether the selected API/model accepts a temperature parameter."""
    provider = (provider or "").lower()
    model = (model or "").lower()
    if provider == "openai" and model.startswith(("o1", "o3", "o4", "gpt-5", "gpt-6")):
        return False
    return provider in {"openai", "xai", "anthropic", "google"}


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

QUIZ_SYSTEM = """You are LearnOrbit Quiz Engine. Generate exactly {count} high-quality assessment questions for the topic.

OUTPUT FORMAT — strict JSON only, no markdown, no preamble:
{{
  "questions": [
    {{
      "id": 1,
      "type": "mcq|msq|short_answer|long_answer",
      "question": "question text with LaTeX where needed ($formula$)",
      "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
      "correct": "A or an array such as [\\"A\\", \\"C\\"] for objective items; null for written items",
      "reference_answer": "concise expected answer for written items; null for objective items",
      "rubric": ["criterion 1", "criterion 2", "criterion 3"],
      "explanation": "Why this is correct and why others are wrong",
      "bloom_level": "remember|understand|apply|analyze|evaluate|create",
      "difficulty": "easy|medium|hard",
      "misconception_check": "common wrong belief this tests",
      "examiner_intent": "definition-check|misconception-trap|algebraic-hygiene|transfer|time-pressure"
    }}
  ]
}}

Use a balanced mix of objective (MCQ/MSQ) and written questions (short answer/long answer); use only MCQ/MSQ when a topic cannot reasonably support written assessment.
For MSQ, the correct value must be an array of at least two option keys. For written questions, set options to {{}}, correct to null, provide a concise reference_answer and exactly three assessable rubric criteria.
Mix difficulties and make distractors realistic.
Tag each item with the hidden examiner intent in examiner_intent. Never reveal the tag in the question text.
Assign each question exactly one Bloom level from remember, understand, apply,
analyze, evaluate, or create. Explain why the correct answer is right and why
each distractor is wrong.
Topic: {topic}
Key areas covered in session: {key_areas}
"""

MISCONCEPTION_SYSTEM = """You are LearnOrbit Misconception Detector.
Given the learner's message and the tutor's accurate explanation, identify a clear misconception only if the learner asserted a false belief. A question, uncertainty, incomplete answer, or request for clarification alone is not a misconception. Do not infer beliefs the learner did not state. If uncertain, return has_misconception=false and confidence 0.

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


def generate_quiz(provider, model, api_key, topic, key_areas="", mode="quiz"):
    question_count = 20 if mode == "exam" else 10
    questions = []
    for batch_start in range(0, question_count, 5):
        batch_count = min(5, question_count - batch_start)
        system = QUIZ_SYSTEM.format(
            count=batch_count,
            topic=topic,
            key_areas=key_areas or topic,
        )
        messages = [{
            "role": "user",
            "content": (
                f"Generate exactly {batch_count} distinct questions for {topic}. "
                f"Use IDs {batch_start + 1} through {batch_start + batch_count}."
            ),
        }]
        raw = call_ai(provider, model, api_key, messages, system=system, max_tokens=6000)
        if _is_provider_error(raw):
            return {"error": raw[:700]}
        parsed = _parse_json_payload(raw)
        batch = parsed.get("questions") if isinstance(parsed, dict) else None
        if not _valid_quiz_batch(batch, batch_count):
            repair_source = json.dumps(parsed, ensure_ascii=False) if isinstance(parsed, dict) else raw
            repair_messages = [{
                "role": "user",
                "content": (
                    "Repair this assessment into valid strict JSON. Preserve the useful "
                    "question ideas, fix missing/invalid answer formats, and return the "
                    "requested number of complete questions in a JSON object with a "
                    "questions array only.\n\n" + repair_source[:12000]
                ),
            }]
            repaired = call_ai(
                provider, model, api_key, repair_messages,
                system="Repair malformed assessment JSON. Output valid JSON only.",
                max_tokens=6000,
            )
            if _is_provider_error(repaired):
                return {"error": repaired[:700]}
            parsed = _parse_json_payload(repaired)
            batch = parsed.get("questions") if isinstance(parsed, dict) else None
        if not _valid_quiz_batch(batch, batch_count):
            return {
                "error": (
                    f"The AI provider returned no usable questions for assessment "
                    f"batch {batch_start // 5 + 1}. Check the selected model/API key "
                    "and try again."
                )
            }
        for offset, question in enumerate(batch[:batch_count]):
            if isinstance(question, dict):
                question["id"] = batch_start + offset + 1
                questions.append(question)
        if len(batch) < batch_count:
            return {"error": f"The AI provider returned only {len(batch)} of {batch_count} questions in a batch. Please retry."}
    return {"questions": questions}


def _valid_quiz_batch(batch, expected_count):
    if not isinstance(batch, list) or len(batch) < expected_count:
        return False
    for question in batch[:expected_count]:
        if not isinstance(question, dict) or not isinstance(question.get("question"), str) or not question["question"].strip():
            return False
        options = question.get("options")
        answer_type = str(question.get("type", "")).strip().lower()
        correct = question.get("correct")
        if not answer_type:
            answer_type = "msq" if isinstance(correct, list) else (
                "mcq" if isinstance(options, dict) and options else "short_answer"
            )
        if answer_type not in {"mcq", "msq", "short_answer", "long_answer"}:
            return False
        if answer_type in {"mcq", "msq"}:
            if not isinstance(options, dict) or len(options) < 2:
                return False
            if answer_type == "mcq":
                if not isinstance(correct, str) or correct not in options:
                    return False
            elif answer_type == "msq":
                if (not isinstance(correct, list) or len(correct) < 2
                        or any(not isinstance(answer, str) for answer in correct)
                        or not set(correct).issubset(options)):
                    return False
        else:
            if (not isinstance(question.get("reference_answer"), str)
                    or not question["reference_answer"].strip()
                    or not isinstance(question.get("rubric"), list)
                    or len(question["rubric"]) != 3
                    or any(not isinstance(item, str) or not item.strip() for item in question["rubric"])):
                return False
    return True


def _is_provider_error(raw):
    text = str(raw or "").strip()
    return not text or text.startswith((
        "Invalid API key.",
        "API key was rejected",
        "Rate limit hit.",
        "API error (",
        "Unexpected error:",
        "[LearnOrbit] Unknown AI provider:",
    ))


def evaluate_written_answers(provider, model, api_key, topic, questions, answers):
    """Score written responses against question-specific criteria on a 0–2 rubric."""
    grading_questions = []
    for question in questions:
        qid = str(question["id"])
        answer = str(answers.get(qid, "")).strip()
        if question.get("type") not in {"short_answer", "long_answer"} or not answer:
            continue
        grading_questions.append({
            "id": qid,
            "question": question["question"],
            "reference_answer": question.get("reference_answer", ""),
            "rubric": question.get("rubric", []),
            "student_answer": answer[:5000],
        })
    if not grading_questions:
        return {}
    messages = [{
        "role": "user",
        "content": json.dumps({"topic": topic, "questions": grading_questions}),
    }]
    raw = call_ai(
        provider, model, api_key, messages,
        system=(
            "Grade written student answers fairly and conservatively. Accept equivalent "
            "wording and correct reasoning. For each rubric criterion assign 0 (missing/"
            "incorrect), 1 (partly correct), or 2 (fully correct). Do not reward verbosity. "
            "Provide concise evidence-based feedback, never infer facts absent from the answer. "
            'Return strict JSON only: {"evaluations":[{"id":"...","criteria":[0,1,2],'
            '"feedback":"..."}]}.'
        ),
        max_tokens=3000,
        temperature=0,
    )
    if _is_provider_error(raw):
        raise RuntimeError(raw[:700])
    payload = _parse_json_payload(raw)
    evaluations = payload.get("evaluations") if isinstance(payload, dict) else None
    if not isinstance(evaluations, list):
        raise RuntimeError("The AI provider returned an invalid written-answer evaluation. Please retry submission.")
    by_id = {}
    expected_ids = {question["id"] for question in grading_questions}
    for item in evaluations:
        if not isinstance(item, dict) or str(item.get("id")) not in expected_ids:
            continue
        criteria = item.get("criteria")
        if not isinstance(criteria, list) or len(criteria) != 3:
            continue
        scores = []
        for value in criteria:
            if isinstance(value, bool) or value not in (0, 1, 2):
                break
            scores.append(value)
        if len(scores) == 3:
            by_id[str(item["id"])] = {
                "criteria": scores,
                "feedback": str(item.get("feedback", ""))[:800],
            }
    if expected_ids - by_id.keys():
        raise RuntimeError("The AI provider did not grade every written answer. Please retry submission.")
    return by_id


def _parse_json_payload(raw):
    """Decode JSON from common model wrappers without assuming one exact fence."""
    cleaned = re.sub(r"```(?:json)?|```", "", str(raw or ""), flags=re.IGNORECASE).strip()
    try:
        payload = json.loads(cleaned)
        return payload if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    for position, char in enumerate(cleaned):
        if char != "{":
            continue
        try:
            payload, _ = decoder.raw_decode(cleaned[position:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def detect_misconception(provider, model, api_key, topic, user_text, correct_concept):
    system = MISCONCEPTION_SYSTEM
    msg = (
        f"Topic: {topic}\nLearner message: {user_text[:4000]}\n"
        f"Tutor explanation: {correct_concept[:5000]}"
    )
    messages = [{"role": "user", "content": msg}]
    raw = call_ai(provider, model, api_key, messages, system=system, max_tokens=512)
    if _is_provider_error(raw):
        raise RuntimeError(f"Misconception analysis failed: {raw[:500]}")
    result = _parse_json_payload(raw)
    if (not isinstance(result, dict)
            or not isinstance(result.get("has_misconception"), bool)
            or not isinstance(result.get("confidence"), (int, float))):
        raise ValueError("Misconception analysis returned invalid JSON.")
    result["confidence"] = max(0, min(1, float(result["confidence"])))
    return result


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
