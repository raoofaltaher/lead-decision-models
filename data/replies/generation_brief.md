# Reply generation brief

This is the brief the tutorial gives for generating synthetic B2B sales replies, followed by how this dataset was produced with it.

## The brief

```text
Create synthetic B2B sales-reply examples for a machine-learning classification tutorial.

Return CSV rows with:
reply_id, scenario_group, outreach_context, reply_text, reply_intent, is_synthetic

Set is_synthetic to true for every generated row. Use unique reply_id values
such as generated_0001, generated_0002, and so on. Do not reuse seed IDs.

Use only these reply_intent values:
interested, meeting_requested, more_information, referral, not_now,
objection, wrong_person, out_of_office, not_interested, opt_out, ambiguous.

Generate 45-89 additional examples per class, in addition to the one seed
example per class. This produces 506-990 combined examples.
Create at least 10 distinct scenario_group values per class, with roughly 4-9
examples per group across the seed and generated rows. A group represents one underlying recipient situation;
keep its paraphrases together so they cannot leak across evaluation splits.

Vary reply length, directness, wording and punctuation. Include short replies,
indirect replies and replies with more than one sentence. Keep the intent
unambiguous unless the label is ambiguous. Keep the fictional product,
industry, geography, company size, sender offer and outreach channel fixed
across this experiment. Vary the recipient's reply, not the outreach strategy.

Do not use real people, real companies, real email addresses, real phone numbers,
or private correspondence. Do not optimize the outreach message itself.
Do not invent a reply that contradicts its label. Use valid CSV quoting for
commas, quotes and line breaks. Generate one class or a small group of classes
per batch if output limits make the full dataset too large; append the batches
under one header while preserving unique IDs and scenario groups. Return only
CSV data with a header row.
```

## How this dataset was produced

- **Generator:** Claude Opus 5.5 (`claude-opus-5-5`), in a Claude Code session on 2026-11-01, one intent per batch.
- **Seeds:** the tutorial's 11 seed replies (`reply-001` to `reply-011`), one per intent, each in its own scenario group.
- **Generated rows:** `generated_0001` to `generated_0612`, 10 scenario groups per intent with 5 or 6 paraphrases each.
- **Fixed context:** every row answers "A first-touch introduction to a fictional B2B procurement service."
- **Checks and relabel:** see `checks_report.json` and `DATASET_CARD.md`. No person reviewed the rows.
