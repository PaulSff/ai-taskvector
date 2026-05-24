# pip install -U spacy
# python -m spacy download en_core_web_sm
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import spacy
from spacy.matcher import Matcher, PhraseMatcher

from units.registry import UnitSpec, register_unit

# Unit I/O ports
SPACY_INPUT_PORTS = [("input_0", "str"), ("input_1", "str")]  # text, lang (iso639_1)
SPACY_OUTPUT_PORTS = [
    ("output_0", "list[str]"),  # noun_phrases
    ("output_1", "list[str]"),  # verbs (lemmatized by default)
    ("output_2", "list[dict]"),  # entities / phrases / concepts (structured)
]

# Default model mapping (small models)
DEFAULT_MODEL_MAP = {
    "en": "en_core_web_sm",
    "de": "de_core_news_sm",
    "fr": "fr_core_news_sm",
    "es": "es_core_news_sm",
    "it": "it_core_news_sm",
    "pt": "pt_core_news_sm",
    "nl": "nl_core_news_sm",
}


def _load_json(path: Optional[str]) -> Optional[Any]:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _spacy_step(
    params: Dict[str, Any],
    inputs: Dict[str, Any],
    state: Dict[str, Any],
    dt: float,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Process text with spaCy and return noun phrases, verbs, and entities/phrase/concept matches.
    See params/docs in previous messages.
    """
    text = inputs.get("input_0") or ""
    lang = inputs.get("input_1") or "en"
    if not isinstance(text, str):
        text = str(text or "")
    if not isinstance(lang, str) or not lang:
        lang = "en"

    params = params or {}

    # Resolve model name
    model_map = (
        params.get("model_map") or params.get("model_map_override") or DEFAULT_MODEL_MAP
    )
    explicit_model = params.get("model")
    model_name = explicit_model or model_map.get(
        lang, model_map.get("en", DEFAULT_MODEL_MAP["en"])
    )

    # Device/GPU handling (best-effort, version-tolerant)
    device = params.get("device")
    if device is None:
        device = "gpu" if params.get("use_gpu") else "cpu"
    device = str(device).lower()

    # Try to enable GPU using functions available in the current spaCy install.
    # We avoid importing names that may not exist; use getattr to call whichever is present.
    gpu_enabled = False
    if device == "gpu":
        prefer = getattr(spacy, "prefer_gpu", None)
        if callable(prefer):
            try:
                gpu_enabled = bool(prefer())
            except Exception:
                gpu_enabled = False
        else:
            # prefer_gpu not present; try require_gpu if available as attribute
            req = getattr(spacy, "require_gpu", None)
            if callable(req):
                try:
                    # Some spaCy variants accept no args; others may raise if unavailable
                    req()
                    gpu_enabled = True
                except Exception:
                    gpu_enabled = False
    effective_device = "gpu" if gpu_enabled else "cpu"

    disable_components = params.get("disable_components") or []
    if not isinstance(disable_components, list):
        disable_components = list(disable_components)

    # Load optional pattern file and merge
    file_patterns = _load_json(params.get("pattern_file"))
    supplied_patterns = params.get("patterns_to_find") or []
    patterns: List[Dict[str, Any]] = []
    if isinstance(file_patterns, list):
        patterns.extend(file_patterns)
    if isinstance(supplied_patterns, list):
        patterns.extend(supplied_patterns)

    # Load spaCy model
    try:
        nlp = spacy.load(model_name, disable=disable_components)
    except Exception:
        try:
            nlp = spacy.load(DEFAULT_MODEL_MAP["en"], disable=disable_components)
        except Exception:
            nlp = spacy.blank("en")

    # Max length
    max_length = params.get("max_length")
    if isinstance(max_length, int) and max_length > 0:
        try:
            nlp.max_length = max_length
        except Exception:
            pass

    # Ensure parser if noun_chunks required
    ensure_parser = params.get("ensure_parser_for_noun_chunks", True)
    if (
        ensure_parser
        and "parser" not in nlp.pipe_names
        and "parser" not in disable_components
    ):
        try:
            nlp.add_pipe("parser")
        except Exception:
            pass

    # Build matchers
    lower_attr = "LOWER" if params.get("lower_case_phrase_matching", True) else None
    phrase_matcher = PhraseMatcher(nlp.vocab, attr=lower_attr) if patterns else None
    token_matcher = Matcher(nlp.vocab) if patterns else None

    for pat in patterns:
        if not isinstance(pat, dict):
            continue
        label = pat.get("label") or pat.get("id") or "PATTERN"
        p_type = pat.get("pattern_type", "phrase")
        pattern_body = pat.get("pattern")
        if p_type == "phrase":
            if isinstance(pattern_body, str):
                docs = [nlp.make_doc(pattern_body)]
            elif isinstance(pattern_body, list):
                docs = [nlp.make_doc(p) for p in pattern_body if isinstance(p, str)]
            else:
                docs = []
            if docs and phrase_matcher is not None:
                try:
                    phrase_matcher.add(label, docs)
                except Exception:
                    pass
        else:
            if isinstance(pattern_body, list) and token_matcher is not None:
                try:
                    token_matcher.add(label, [pattern_body])
                except Exception:
                    pass

    # Process text
    doc = nlp(text)

    # Noun phrases (noun_chunks)
    noun_phrases: List[str] = []
    try:
        noun_phrases = [chunk.text for chunk in doc.noun_chunks]
    except Exception:
        noun_phrases = []

    # Verbs (optionally lemmatized)
    use_lemma = params.get("use_lemma_for_verbs", True)
    verbs: List[str] = []
    for token in doc:
        if token.pos_ == "VERB":
            verbs.append(token.lemma_ if use_lemma else token.text)

    # Entities from spaCy NER
    include_spacy_ents = params.get("include_spacy_ents", True)
    entities: List[Dict[str, Any]] = []
    if include_spacy_ents:
        for ent in getattr(doc, "ents", []):
            entities.append(
                {
                    "text": ent.text,
                    "label": ent.label_,
                    "start_char": ent.start_char,
                    "end_char": ent.end_char,
                    "type": "spacy_ent",
                }
            )

    # Add matches from matchers
    seen = set()
    if patterns:
        if phrase_matcher:
            try:
                for match_id, start, end in phrase_matcher(doc):
                    label = nlp.vocab.strings[match_id]
                    span = doc[start:end]
                    key = (span.start_char, span.end_char, label)
                    if key in seen:
                        continue
                    seen.add(key)
                    entities.append(
                        {
                            "text": span.text,
                            "label": label,
                            "start_char": span.start_char,
                            "end_char": span.end_char,
                            "type": "phrase_match",
                        }
                    )
            except Exception:
                pass
        if token_matcher:
            try:
                for match_id, start, end in token_matcher(doc):
                    label = nlp.vocab.strings[match_id]
                    span = doc[start:end]
                    key = (span.start_char, span.end_char, label)
                    if key in seen:
                        continue
                    seen.add(key)
                    entities.append(
                        {
                            "text": span.text,
                            "label": label,
                            "start_char": span.start_char,
                            "end_char": span.end_char,
                            "type": "token_match",
                        }
                    )
            except Exception:
                pass

    # Optional verbose/meta entry (includes effective device)
    if params.get("verbose"):
        entities.append(
            {
                "text": json.dumps(
                    {
                        "model": model_name,
                        "nlp_pipe": nlp.pipe_names,
                        "effective_device": effective_device,
                    }
                ),
                "label": "META",
                "start_char": 0,
                "end_char": 0,
                "type": "meta",
            }
        )

    outputs = {"output_0": noun_phrases, "output_1": verbs, "output_2": entities}
    return (outputs, state)


def register_spacy_nlp_processor() -> None:
    register_unit(
        UnitSpec(
            type_name="spacy_nlp_processor",
            input_ports=SPACY_INPUT_PORTS,
            output_ports=SPACY_OUTPUT_PORTS,
            step_fn=_spacy_step,
            role=None,
            description=(
                "Processes input text with spaCy. Inputs: text and optional ISO 639-1 language code. "
                "Params: patterns_to_find (list) or pattern_file (json), model/model_map, device/use_gpu, "
                "disable_components, ensure_parser_for_noun_chunks, use_lemma_for_verbs, include_spacy_ents, "
                "max_length, verbose. Outputs: noun phrases (output_0), verbs (output_1), and structured "
                "entities/phrase/concept matches (output_2)."
            ),
        )
    )


__all__ = ["register_spacy_nlp_processor", "SPACY_INPUT_PORTS", "SPACY_OUTPUT_PORTS"]
