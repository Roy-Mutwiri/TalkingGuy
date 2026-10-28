# Trade Fix streamer training starter

Prepared for Roy Mutwiri. Version 1.0. Date: 2026-10-26 (America/New_York).

## What this is

An original, synthetic teaching set for an English AI trading-stream host: 48 demonstrations, split into 32 training, 8 validation and 8 held-out test examples; plus 8 training and 4 validation preference pairs. It demonstrates data structure and desired behavior. It is not a corpus of top streamers, is not human-validated, contains no audio, and has no measured watch-time or retention results. All market values and viewer situations are fictional fixtures.

Use the examples first for prompt experiments, retrieval of relevant demonstrations, schema checks, and a small fine-tuning pipeline smoke test. This small starter set is insufficient to establish broad ability or justify production deployment. Public research datasets are linked, not redistributed. Do not feed validation/test targets into training or retrieval.

## Files

- `sft_train.jsonl`, `sft_validation.jsonl`, `sft_test.jsonl`: chat-format messages. The assistant target is serialized JSON with action, reply_to, speech, delivery and follow_up. Only `speech` is sent to TTS.
- `annotated_examples.jsonl`: the same 48 demonstrations with skill, split, scenario group, input, target, provenance and review status. This is a catalog, not extra training data.
- `preference_train.jsonl`, `preference_validation.jsonl`: prompt/chosen/rejected format suitable for adaptation to TRL DPO. The preference labels are author-generated, not ratings from real viewers.
- `preference_annotations.jsonl`: the defect illustrated by each rejected answer. Rejected answers must never be used as SFT targets.
- `evaluation_rubric.md`: practical assessment and retention experiment design.
- `sources.md`: primary-source links and data-use qualifications.
- `manifest.json`: counts, hashes and validation results.

## The behavior to develop

1. Orient someone who arrives in the middle of a stream within a few clear sentences.
2. Explain one useful observation, why it matters, and the next thing to examine.
3. Select relevant, novel comments instead of reading the chat chronologically.
4. Ask one answerable question, allow a response, and use the answers.
5. Keep a session memory of questions and promises; return to them with a real payoff.
6. Use warmth and occasional light humor. Let energy rise when an actual event warrants it.
7. Know when to stop talking. Speech already playing, a pending question, or no new information can justify waiting.
8. Admit missing data, preserve numbers and names, and recover gracefully from mistakes.

These are design objectives to test, not claims that every popular streamer shares one formula. A coherent persona is more useful than switching between incompatible creator styles.

## Build your actual corpus

Use your own streams, hired voice performers, or source recordings licensed for the intended training use. Select 8–12 creators or hosts as technique references, covering explaining, improvising, audience interaction and recovery. Study ordinary stretches and quiet periods as well as highlights. Create original Trade Fix demonstrations of the techniques; do not depend on copied catchphrases or another person's voice identity.

As an initial collection target, prepare 2,000–5,000 reviewed examples, then expand according to observed errors. This is a planning target, not an empirically proven minimum. Every example should preserve the preceding context and the timing of the relevant chat message. Include unsuccessful moments and deliberate silence, not only exciting speeches.

Record: source/session id, timestamps, source rights, recent transcript, selected and competing chat messages, event facts with timestamps, existing memory, speech-busy state, action, reply, delivery label, next promised beat, reviewer scores and any platform outcome measurements. Never let the training input include future chat, future prices, or future results. Put all overlapping windows from one source session in the same split. For stronger evaluation, also hold out some source creators and entire days.

Use a target distribution adapted to your stream's actual workload. Ensure explicit coverage of: arrivals, useful explanations, genuine questions, humor, disagreement, quiet periods, technical failures, name corrections, misleading comments, unavailable data, and follow-through on promises. Do not infer causality merely because a popular creator's clip has many views.

## Training sequence

**First establish a baseline.** Use the current instruction model with a clear persona, structured state, and a few retrieved examples. Review complete session replays and listen to rendered audio. Prompting and runtime changes may fix errors without model training.

**Then supervised fine-tuning (SFT).** Train a small adapter on compatible base-model weights using the reviewed demonstrations and the model's correct chat template. Model architecture and hardware determine whether LoRA/QLoRA is suitable. An Ollama model name or Modelfile is not evidence of fine-tuning. Keep all other runtime settings fixed when comparing an adapter against the baseline.

**Then preferences, if needed.** For the same input, have two reviewers compare alternatives for relevance, naturalness, clarity, timing, and accuracy. Use agreed preferred/rejected pairs with DPO or a similar method. Do not train a model merely to sound more excited or to produce longer answers. Do not optimize directly for raw chat-message volume or watch time without quality constraints.

**Train or tune voice separately.** Text SFT does not teach pitch, breath, laughter, pauses, or vocal identity. Record consented target-voice audio paired with exact transcripts and delivery labels. Start with natural calm speech and small variations. Verify the exact TTS checkpoint's training support before collecting a large audio corpus. Treat `delivery` as metadata; a speech adapter must map it only to controls that the installed TTS actually supports. If an effect is unsupported, omit it rather than speaking the label.

## Runtime that turns the trained model into a live host

- Chat selector: score topical relevance, novelty, urgency, and whether the question was already answered. Queue or expire stale comments. Research on response-worthy chat supports using multiple criteria, but the weights must be validated for your audience.
- Segment controller: alternate useful explanation, viewer response, short recap, and observation. Have an explicit pending-question state and a store of promised follow-ups. Do not introduce a new promised segment if the runtime cannot deliver it.
- Grounding: provide fresh facts from actual tools or feeds. Training cannot supply current market prices. Make data age and unavailable state explicit.
- Memory: maintain a bounded session ledger of viewer preferences, pronunciation corrections and unfinished questions. Do not invent familiarity. Any persistence across sessions needs an actual stored record.
- Speech: normalize names, numbers, abbreviations and emoji before TTS. Keep accurate caption text separate from pronunciation respellings. Skip empty outputs and prevent overlapping audio.
- Timing: measure comment age and decision-to-first-audio latency. Cancel obsolete queued speech after a major state change. Fixed frequent monologues are not a substitute for relevance.

The starter schema's `follow_up` is only a planning field. A real scheduler must store, trigger, and mark it completed. `wait` is one decision; subsequent events can cause a new decision. An ignored comment should not be announced to the audience.

## A small engagement experiment

Test a recurring educational segment: identify a concrete detail, invite one observation, leave time for answers, explain the answer, and refer back to a real comment. During slow market periods, use a self-contained chart-reading exercise rather than pretending a major event is imminent.

Try changes in matched session blocks, keeping market session, content, acquisition source and technical quality as comparable as possible. Start with one variable: shorter answers, better callbacks, or a different recap cadence. Measure average watch duration and returning-viewer/retention metrics where the platform exposes them; your own logs can measure repeated phrases, stale replies, factual errors and speech latency. Report uncertainty and avoid attributing a single unusually active day to training.

## Adoption gate

This pack has been checked for valid JSON, unique scenario ids, split separation, valid reply references, and consistent empty wait outputs. It has not been used to train a model or tested with real viewers. Review and revise the synthetic labels before substantial training. Compare complete audio sessions against the baseline before making production claims.
