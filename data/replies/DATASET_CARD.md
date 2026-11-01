# Dataset card: synthetic B2B sales replies

`reply_examples.csv` holds 617 synthetic replies to one fictional first-touch sales email, each labelled with one of 11 intents. It trains and evaluates the reply-routing decision model in this repository. It is not real correspondence, and no person reviewed it.

## Provenance

- **Generator:** Claude Opus 5.5 (`claude-opus-5-5`) in a Claude Code session on 2026-11-01, one intent per batch, following `generation_brief.md`.
- **Seeds:** the tutorial's 11 seed replies (`reply-001` to `reply-011`).
- **Generated rows:** `generated_0001` to `generated_0624`.
- **Fixed context:** every reply answers "A first-touch introduction to a fictional B2B procurement service." Only the reply varies; the offer, channel and market do not.
- **Human review:** none. The Owner chose automated checks in place of review.

## Automated checks

`tools/check_replies.py` gates the file. `checks_report.json` records the run.

1. Schema: the six required columns, no blank or null values, unique `reply_id`.
2. Taxonomy: only the 11 intents below.
3. Duplicates: no two replies are equal after casefolding and removing punctuation.
4. Scenario groups: every group holds one intent, and every intent has at least 10 groups and 45 rows. The dataset has at least 500 rows.
5. Blind relabel: a separate agent on a different Claude model (Sonnet) labelled every reply from its text and the intent definitions alone, under random IDs and in random order. Rows where its label differed from the intended label were dropped.

The first relabel pass agreed on every row, but its input kept IDs that ran in intent order, so the labels could be inferred from the IDs. That pass was discarded, and the published pass used random IDs.

## Result

635 candidate rows, 617 kept: an agreement rate of 97.2%. Of the 18 dropped rows, 17 were declines that give a reason ("We went with a competitor", "We don't have this problem"), which the annotator labelled `objection`, and one was an ambiguous reply labelled `wrong_person`. A decline with a reason fits both definitions; the dataset keeps only the declines both labellers agree on. Two groups of plain declines were then added so that `not_interested` stays above its floor.

| Intent | Rows | Scenario groups |
|---|---:|---:|
| interested | 61 | 11 |
| meeting_requested | 51 | 11 |
| more_information | 53 | 11 |
| referral | 61 | 11 |
| not_now | 51 | 11 |
| objection | 61 | 11 |
| wrong_person | 61 | 11 |
| out_of_office | 51 | 11 |
| not_interested | 56 | 13 |
| opt_out | 51 | 11 |
| ambiguous | 60 | 11 |

SHA-256 of `reply_examples.csv`: `c57a26d99d05b29b3ce63c5e627d2a79dd03ed78d3bd35ce1afb1f07fca72439`.

## Intents

| Intent | Meaning |
|---|---|
| interested | The recipient expresses interest without requesting a meeting. |
| meeting_requested | The recipient asks to schedule or discuss a meeting. |
| more_information | The recipient requests details, pricing or documentation. |
| referral | The recipient points to another relevant person. |
| not_now | The recipient asks to revisit the topic later. |
| objection | The recipient raises a concern or reason not to proceed. |
| wrong_person | The recipient says they are not responsible for this topic. |
| out_of_office | The recipient indicates an absence or return date. |
| not_interested | The recipient declines further engagement. |
| opt_out | The recipient asks to stop marketing or unsubscribe. |
| ambiguous | The reply does not support a reliable intent classification. |

## Limitations

- One generator wrote every reply, so the data carries its wording habits. A model can learn those habits as shortcuts, and they will not match how real prospects write.
- The classes are balanced on purpose. Their proportions say nothing about how often each intent occurs in real inboxes.
- The relabel agent is also a Claude model. It catches labels that contradict the text, but it can share the generator's blind spots.
- Real replies mix intents, quote earlier mail, carry signatures and arrive in many languages. These replies are short, clean and English.
- Results on this data show that the pipeline works. They do not show performance on real sales replies; test on permissioned, anonymized real replies before any deployment.

## License

MIT, like the rest of this repository.
