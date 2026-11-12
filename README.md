# Keyboards Text-to-Graph

[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?style=flat&logo=FastAPI&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?style=flat&logo=Python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Containerized-2496ED.svg?style=flat&logo=Docker&logoColor=white)](https://www.docker.com/)

A web service that turns English or Danish text about musical keyboards
(specification sheets, advertisements) into a **JSON-LD knowledge graph**
expressed in the vocabulary of the **Keyboards Wikibase** and linked to its
existing items. Developed for the **DTU Natural Language Processing & Large
Language Models** course (assignment 08). The service never modifies the
Wikibase: it links against a read-only local snapshot.

```text
browser ─► frontend :8080 ──HTTP──► text2graph :8000 ──► CampusAI LLM
               │                          │
               └─ RDF scoring (rdflib)    └─ data/catalogue.json (Wikibase snapshot)
```

---

## Pipeline

```text
text ──LLM (prompt + JSON Schema)──► Extraction     surface strings, numbers in mm / kg / W / DKK
     ──entity linking (catalogue)──► kb:Q… | None   manufacturers, colours, sellers, models
     ──graph builder──────────────► JSON-LD        @base = fresh UUID, local ids model/1, offer/1
```

The LLM never writes identifiers or JSON-LD: it fills a flat, typed schema
(`schema.py`, enforced with **structured outputs**), and application code
links the names and builds the graph. It therefore cannot invent a Wikibase
id, forget the `@base`, or produce invalid JSON-LD.

## Project structure

```text
08-text-to-graph/
├── data/
│   ├── catalogue.json           # Wikibase entities to link to (scripts/fetch_catalogue.py)
│   └── keyboards.txt            # Test dataset: text / reference JSON-LD pairs
├── scripts/fetch_catalogue.py   # Refresh the catalogue snapshot (read-only SPARQL)
├── src/
│   ├── text2graph/              # The web service (:8000)
│   │   ├── config.py            # pydantic-settings (CampusAI, catalogue path)
│   │   ├── vocabulary.py        # Namespaces, classes, field -> property mapping, @base
│   │   ├── schema.py            # Extraction schema filled by the LLM (+ strict JSON Schema)
│   │   ├── catalogue.py         # Catalogue snapshot loader + prompt listing
│   │   ├── llm.py               # Async CampusAI chat client (from project 07)
│   │   ├── prompts.py           # Extraction prompt: rules + few-shot examples
│   │   ├── extraction.py        # LLM call + tolerant parsing of the answer
│   │   ├── linking.py           # Entity linking: name -> kb:Q… or None
│   │   ├── graph.py             # Extraction + links -> JSON-LD
│   │   ├── pipeline.py          # TextToGraph: extract -> link -> build
│   │   └── server.py            # FastAPI app, lifespan, error mapping
│   └── app/                     # Evaluation frontend (:8080), ported from text-to-graph-ui.py
│       ├── routes/              # /api/{health,config,dataset,compare,extract} + HTML page
│       ├── services/            # call the service, score its answer
│       └── utils/               # scoring.py (RDF triple F1), dataset.py (teacher's logic)
├── frontend/                    # Jinja2 template + static CSS/JS
├── tests/                       # pytest suite (no network: FakeLLM + catalogue snapshot)
├── Dockerfile                   # Multi-stage: frontend / text2graph (default)
├── compose.yaml                 # text2graph + frontend
└── main.py, frontend_main.py    # Dev entry points
```

---

## API

### `POST /v1/extract`

```json
{"text": "Der er kun 32 tangenter på et Roland SH-101."}
```

Response (`application/ld+json`):

```json
{
  "@context": {
    "@base": "https://example.org/keyboards/extraction/923d9fa7-a76f-4fff-ba1f-32a8801c7064/",
    "kb": "https://keyboards.wikibase.cloud/entity/",
    "kbt": "https://keyboards.wikibase.cloud/prop/direct/",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#"
  },
  "@graph": [
    {"@id": "kb:Q18", "kbt:P11": {"@id": "kb:Q14"}, "kbt:P1": 32, "kbt:P6": {"@id": "kb:Q16"}}
  ]
}
```

| Status | Meaning |
| --- | --- |
| 422 | Invalid request body |
| 501 | A pipeline step is not implemented yet |
| 502 | LLM answer unusable, or LLM unavailable |
| 503 | LLM not configured (missing `CAMPUSAI_API_KEY`) |
| 504 | LLM timed out |

### `GET /health`

`{"status": "ok"}` — liveness probe used by Docker / Compose.

---

## Run

```bash
uv sync                                               # dev environment (.venv)
uv run uvicorn src.text2graph.server:app --reload --port 8000
uv run uvicorn src.app.main:app --reload --port 8080  # evaluation UI
# ... or both in Docker
docker compose up --build
```

Open <http://localhost:8080>, then *Run all cases* to score the service on
`data/keyboards.txt` (triple precision / recall / F1 after JSON-LD expansion).

## Configure

Create a `.env` at the project root (never committed), see `.env.example`:

```bash
CAMPUSAI_API_KEY=...
CAMPUSAI_API_URL=https://api.campusai.compute.dtu.dk/v1
CAMPUSAI_MODEL=...
CAMPUSAI_EMBED_MODEL=...           # optional (embedding-based linking)
LLM_MAX_TOKENS=4096
CATALOGUE_PATH=data/catalogue.json
STUDENT_URL=http://localhost:8000/v1/extract   # frontend default
LOG_LEVEL=INFO
```

Refresh the catalogue when the Wikibase changes (read-only SPARQL queries):

```bash
uv run python -m scripts.fetch_catalogue
```

## Test

```bash
uv run pytest                     # whole suite (+ doctests in src/)
uv run pytest --no-live           # without calls to the real LLM
uv run pytest -m "not bonus"      # skip the harder tests
```

---

## Design choices

### Division of labour: LLM for language, code for identifiers

The LLM does what only it can do: read paraphrases, Danish, units and
distractors. It fills a flat Pydantic schema (`schema.py`) with **surface
strings** and **numbers in the target units**, enforced by strict structured
outputs (JSON Schema, `temperature = 0`). Everything that must be *exact*
belongs to deterministic, unit-tested code: entity linking (`linking.py`),
local ids, the UUID `@base`, typed literals and IRIs (`graph.py`). So the LLM
cannot invent a `kb:Q…` id ("Do not invent Wikibase identifiers") or emit
malformed JSON-LD. Each step can also be tested on its own (fake LLM, fake
linker), and the logs show where an error comes from (extraction or linking).

### Prompt strategy (`prompts.py`)

* **System prompt**: the assignment's rules made operational:
  * `null` ≠ `0`: 0 only when an absence is stated;
  * cm → mm and g → kg; `kr.` = DKK; Danish number format (`26.500` = 26500,
    `7,5` = 7.5);
  * the update date wins over the creation date;
  * physical sockets, not channels (a stereo AUX is 1 socket);
  * distractors: packaging dimensions, amplifier watts, number of voices,
    purchase price vs asking price;
  * colours in English base form (the linker knows `rød`/`red`, not the
    inflected `røde`);
  * off-topic texts (the Yamaha motorcycle) → empty lists;
  * a number inside a model name is not a stated fact.
* **Schema-aware prompting**: the catalogue (`catalogue.prompt_listing()`,
  names and aliases, **no ids**) is appended to the system prompt. Rule: if
  the text refers to a catalogue model, copy its canonical name and pick the
  variant implied by the text ("Nord Stage 4 med 88 tangenter" →
  `Nord Stage 4 88`). Otherwise keep the name as written. The LLM copies
  names, which it is good at, and the code turns them into ids
  deterministically.
* **Three invented few-shot pairs**, none taken from the test data (a test
  checks it):
  * an English spec sheet of an unknown model (unit conversions, carton and
    amplifier distractors, an explicit `0` for DIN MIDI);
  * a Danish classified ad of a catalogue model (variant naming
    `Korg Kross 2-61`, thousands separator, update date, inflected colour,
    purchase price as a distractor);
  * an off-topic text that shares a brand with keyboards → `Extraction()`.

### Linking rule (`linking.py`)

Conservative, by **levels of evidence**: the first level that finds a match
decides, and lower levels are never consulted.

1. normalized key (NFKC, `casefold`, only letters and digits) equal to the
   English label;
2. equal to an alias;
3. *(relaxed)* same comparison after dropping a trailing legal form
   (`A/S`, `GmbH`…), e.g. "Digitalpiano.com" → Q38;
4. *(models only)* same comparison without the manufacturer prefix, with a
   compatibility check: "Casio FP-10" never reaches "Roland FP-10".

Candidates are always of the requested kind. If several *distinct* entities
match at the deciding level, the name is ambiguous and the result is `None`
(e.g. "Nord Stage 4" has three variants). There is no fuzzy matching:
`jupiter08` vs `jupiter6` has a similarity of 0.82, which would be a
false link.

Why so conservative: with $F_1 = \frac{2TP}{2TP + FP + FN}$, a wrong link
costs 1 FP + 1 FN, while no link costs 1 FN only.

### Graph modelling (`graph.py`)

* **Linked model** → node `kb:Q…`, typed `kbt:P11 kb:Q14`, **no**
  `rdfs:label` (the catalogue already names it). If the text states no fact
  about it, the node is not emitted at all (assignment example 1).
* **Unmatched model** → local node `model/<n>` with an English `rdfs:label`.
* **Offer** → `offer/<n>`, typed `kb:Q42`, linked to its model with `kbt:P24`.
  If the model is neither extracted nor in the catalogue, the offer gets a
  labelled local node. The seller is linked or omitted, the URL is an
  **IRI** (`{"@id": …}`), and the date is a typed literal (`xsd:date`).
* Values: `is not None` filters unknown values but keeps a stated `0`.
  Unlinked manufacturers and colours are omitted. `992.0` is written `992`.
* **One node per entity**: two mentions of the same model (same `kb:Q…` or
  same local name) are merged into one node, since nodes are indexed by
  `@id`. Counters are separate for `model/n` and `offer/n`, and the UUID
  `@base` keeps local ids unique across extractions.

## Evaluation

`data/keyboards.txt` (10 cases), CampusAI model `cai`, `temperature = 0`,
scored with the teacher's RDF triple comparison (`src/app/utils/scoring.py`,
the same as *Run all cases*). Run on 2026-11-03.

| # | Case | P | R | F1 | TP / FP / FN | Latency |
| -: | --- | -: | -: | -: | :-: | -: |
| 1 | Yamaha GS1 weighs 90 kg | 1.00 | 1.00 | **1.00** | 3 / 0 / 0 | 6.4 s |
| 2 | Roland Jupiter-08 has just 25 keys | 1.00 | 1.00 | **1.00** | 4 / 0 / 0 | 6.8 s |
| 3 | Yamaha XSR900 (motorcycle) | 1.00 | 1.00 | **1.00** | 0 / 0 / 0 | 2.2 s |
| 4 | Der er kun 32 tangenter på et Roland SH-101 | 1.00 | 1.00 | **1.00** | 3 / 0 / 0 | 7.2 s |
| 5 | Morsø Musikhus sells a Yamaha PSR-E-583 | 0.71 | 1.00 | 0.83 | 5 / 2 / 0 | 8.8 s |
| 6 | Yamaha PSR-E373 (spec text) | 0.00 | 0.00 | 0.00 | 0 / 15 / 15 | 15.1 s |
| 7 | Yamaha PSR-E483 and PSR-E583 | 0.97 | 0.93 | 0.95 | 28 / 1 / 2 | 23.9 s |
| 8 | Nord Stage 4 88 (Danish ad) | 1.00 | 1.00 | **1.00** | 8 / 0 / 0 | 9.7 s |
| 9 | Roland SH-101 (DTU ad) | 0.67 | 1.00 | 0.80 | 4 / 2 / 0 | 11.2 s |
| 10 | The three Nord Stage 4 models lack speakers | 1.00 | 1.00 | **1.00** | 9 / 0 / 0 | 10.3 s |

**Micro F1 = 0.776, macro F1 = 0.858**, mean latency 10.1 s per text (one LLM
call each). Recall is 1.00 on 8 of the 10 cases. Before the rule "a number
inside a model name is not a stated fact", case 10 scored 0.90: the LLM added
`keys = 88` / `73` taken from the variant names.

Error analysis: the remaining losses come from the extraction choices behind
the reference, not from misread facts.

* **Case 6 (F1 = 0)**: our linker correctly links "Yamaha PSR-E373" to
  `kb:Q103`, which exists in the catalogue, but the reference uses a local
  node `"1"`. All 15 extracted facts are right, yet each triple has a
  different subject, so we get 15 FP + 15 FN. Creating a local node here
  would break the linking rule of the assignment.
* **Case 7**: the reference both links PSR-E583 to `kb:Q106` *and* gives it
  an `rdfs:label`, while the assignment reserves labels for local nodes (1 FN).
  Our PSR-E483 label is "Yamaha PSR-E483" (as written at its first mention),
  whereas the reference uses "PSR-E483", even though the Jupiter-08 reference
  keeps the manufacturer ("Roland Jupiter-08"): 1 FP + 1 FN for a correct
  label.
* **Cases 5 and 9 (2 FP each)**: in these short ads we also emit the linked
  model's type and manufacturer (`kb:Q106 kbt:P6 kb:Q2`). The reference omits
  them for these two ads ("additional specifications are optional"), but
  includes them in the Nord Stage 4 ad (case 8). No single rule fits all three
  references, so we keep the stated fact.

## Discussion

**LLM vs rules for extraction.** A regex extractor would do well on case 1
("weighs 90 kg") but not on the rest of the dataset: Danish inflection
(`røde`), the Danish thousands separator, units to convert, and above all
*distractors* that look exactly like the target (packaging dimensions next
to the instrument dimensions, 6 W amplifier channels next to the 13 W
consumption, 860 voices next to 64-note polyphony, a purchase price next to
the asking price). Telling them apart needs reading comprehension. The price
is that the LLM is not deterministic across model versions and sometimes
"knows too much" (the keys taken from a model name), so the prompt has to
state negative rules explicitly and the tests check them (`live`).

**Reliability of linking.** We favour precision over recall: an exact match
on a normalized key, by levels of evidence, and abstention when the match is
ambiguous. A wrong link is worse than no link, both in the F1 (FP + FN vs FN)
and in the graph, where a false `kb:Q…` silently merges facts about two
different products. Fuzzy matching was rejected because model names differ
by one character (Jupiter-6 vs Jupiter-08, GO:KEYS 3 vs 5). Choosing among
variants (Nord Stage 4 88 / 73 / Compact) is left to the LLM, which sees the
catalogue names and the stated key count.

**Limits of triple-level scoring.** The metric is strict and syntactic: a
correct but differently written label ("Yamaha PSR-E483" vs "PSR-E483"), or
a correct link to an item the reference did not use (case 6), costs as much
as a wrong fact. One subject mismatch spreads to every triple of the node,
which is why case 6 drops from all-correct facts to F1 = 0. Micro F1 is
dominated by the long spec texts, macro F1 by the many short cases; both are
needed. With 10 cases, one disputed reference moves micro F1 by several
points.

**Scaling up.** The catalogue (76 entities, ~80 prompt lines) fits in the
prompt, but Wikidata would not. We would need candidate retrieval before the
LLM call (`wbsearchentities`, BM25 or embeddings over labels and aliases),
pass the top-k candidates only, and keep the exact-key linker as the final
check, possibly with LLM disambiguation when several candidates remain.
Latency (≈10 s per text, dominated by the LLM) could be reduced with
smaller models for short texts or by batching requests.

## TODO (not implemented)

* **Optional extension: storage and SPARQL querying.** Add `POST /v1/graphs`
  (store a JSON-LD document in a local, in-memory `rdflib.Dataset`, so the
  public Wikibase stays unchanged) and `POST /v1/sparql` (query it). Demo:
  store the PSR-E483/E583 spec text, then the Morsø PSR-E-583 offer, and ask
  "Which keyboard models weigh less than 8 kg and have an offer below DKK
  3,000?". The join works only because both documents link the model to the
  same `kb:Q106`: two local `model/1` nodes would never meet.
* **Embedding-based linking** (`CAMPUSAI_EMBED_MODEL`): cosine similarity
  above a threshold *and* a margin over the second candidate; measure whether
  the extra recall is worth the false links.
* **LLM disambiguation** (ReAct-style): when the linker finds several
  candidates ("Nord Stage 4" → 88 / 73 / Compact), send them back to the LLM
  with the extracted facts and let it choose, with a second call only in that
  case.
* **Self-consistency**: several extractions at temperature > 0, keep the
  majority facts, and measure the precision gained against cost and latency.
