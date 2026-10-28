# Evaluation rubric

Use unseen complete scenarios and listen to the actual rendered voice. A strong text answer can still sound poor or arrive too late.

## Review each decision

Rate each dimension 1–5 with written reasons:

| Dimension | 1 | 5 |
|---|---|---|
| Relevance | Ignores the actual moment | Directly addresses what matters now |
| Usefulness | Empty hype or filler | Adds a clear observation, explanation or answer |
| Conversational tone | Stiff, patronizing or forced | Clear, warm and appropriate to the moment |
| Participation | Stacks questions or reads everything | Selects a good comment and allows response time |
| Continuity | Repeats or drops promised topics | Uses supplied memory and completes the beat |
| Delivery | Monotone, overacted or mistimed | Intelligible, varied and paced appropriately |

Hard failures: invented current prices; incorrect signs/decimals; fabricated personal memories or trading results; speaking while audio is already playing; reading emoji/control labels; claiming a scheduled follow-up happened when it did not; using a future event unavailable at decision time.

## Pairwise judgments

For identical input, compare A and B in randomized order. Reviewers select A, B, tie, or neither, then state why. A more entertaining reply cannot win if it introduces a hard factual failure. Resolve disagreements before making training labels. Do not present author-generated preferences as human audience ratings.

## Tests beyond this starter set

Use whole unseen sessions; bursts of 20 or more comments; no-chat intervals; duplicate questions; connection losses; unexpected topic switches; corrected names; conflicting stale/fresh facts; and a supplied event that arrives while speech is queued. Validate numeric fidelity after TTS, not only in text. Evaluate timing at the actual runtime's audio boundaries.

## Audience experiment log

Record model/version, prompt/version, voice/version, tested change, segment type, start/end, market session, stream quality, arrival source if available, aggregate watch duration/retention if exposed, returning viewers if exposed, relevant comments, and factual/repetition failures. Do not invent per-viewer retention if the platform does not supply it.

Compare repeated, matched blocks and report uncertainty. Chat volume, likes and follows are secondary measures; they can rise without improving watch quality. Keep a short review of confusing or annoying moments. Update the dataset from verified recurring errors, then rerun the unchanged held-out evaluation.
