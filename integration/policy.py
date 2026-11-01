import numpy as np
import pandas as pd

MODEL_FEATURES = [
    "industry",
    "region",
    "employee_band",
    "estimated_revenue_band",
    "process_maturity_band",
    "role_function",
    "seniority",
    "buyer_role",
    "touch_count",
    "inbound_touch_count",
    "outbound_touch_count",
    "session_count",
    "pricing_page_views",
    "demo_page_views",
    "total_session_duration_seconds",
    "touches_week_1",
    "touches_last_7_days",
    "days_since_first_touch",
    "activity_count",
    "days_since_last_touch",
    "opportunity_created",
    "has_open_opportunity",
    "opportunity_estimated_acv",
    "expected_acv",
]


LEAD_QUESTIONS = {
    "icp_fit": {
        "type": "choice",
        "instructions": (
            "Apply the stated fictional ICP using only industry, region and employee_band. "
            "Ignore contact role, seniority, lead source, engagement and opportunity fields "
            "when deciding account fit. Return not_fit if any known required value is "
            "outside the target. Otherwise use insufficient_evidence when a required "
            "value is missing. Do not infer facts that are not present."
        ),
        "criteria": {
            "fit": "Target industry, US or UK region, and an employee band from 200 to 1999.",
            "not_fit": "At least one known firmographic value falls outside the target ICP.",
            "insufficient_evidence": "At least one required field is missing, and no known value rules out ICP fit.",
        },
    },
    "conversion_outcome_90d": {
        "type": "noul",
        "instructions": (
            "Classify whether the simulator records a closed_won event within 90 days "
            "of lead creation. Features cover only the first 30 days, so the label "
            "may include outcomes that occurred before the feature cutoff. "
            "Do not interpret this as a day-30-to-day-90 forecast."
        ),
    },
}


def to_python_value(value):
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


TARGET_BUYER_ROLES = {
    "economic_buyer",
    "champion",
    "technical_evaluator",
}


def evaluate_contact_persona_fit(buyer_role):
    if pd.isna(buyer_role):
        return None

    return str(buyer_role).strip().lower() in TARGET_BUYER_ROLES


def lead_action(
    prediction,
    suppressed,
    contact_persona_fit,
    contact_eligibility,
):
    if isinstance(suppressed, np.bool_):
        suppressed = bool(suppressed)
    if isinstance(contact_persona_fit, np.bool_):
        contact_persona_fit = bool(contact_persona_fit)

    if suppressed is True:
        return {
            "priority": "blocked",
            "action": "suppress",
            "send": False,
        }

    if suppressed is not False:
        return {
            "priority": "review",
            "action": "verify_suppression_status",
            "send": False,
        }

    fit = prediction.get("icp_fit")

    if fit not in {"fit", "not_fit", "insufficient_evidence"}:
        return {
            "priority": "review",
            "action": "human_icp_review",
            "send": False,
        }

    if fit == "insufficient_evidence":
        return {
            "priority": "review",
            "action": "research_missing_account_evidence",
            "send": False,
        }

    if fit == "not_fit":
        return {
            "priority": "low",
            "action": "do_not_recommend_outreach",
            "send": False,
        }

    if contact_persona_fit is False:
        return {
            "priority": "high",
            "icp_fit_probability": prediction.get("icp_fit_probability"),
            "action": "find_relevant_contact",
            "send": False,
        }

    if contact_persona_fit is not True:
        return {
            "priority": "high",
            "icp_fit_probability": prediction.get("icp_fit_probability"),
            "action": "human_persona_review",
            "send": False,
        }

    if contact_eligibility == "ineligible":
        return {
            "priority": "blocked",
            "action": "do_not_contact",
            "send": False,
        }

    if contact_eligibility != "approved":
        return {
            "priority": "high",
            "icp_fit_probability": prediction.get("icp_fit_probability"),
            "action": "human_eligibility_review",
            "send": False,
        }

    return {
        "priority": "high",
        "icp_fit_probability": prediction.get("icp_fit_probability"),
        "action": "recommend_outreach_for_approval",
        "send": False,
    }


REPLY_QUESTIONS = {
    "reply_intent": {
        "type": "choice",
        "instructions": (
            "Classify the recipient's reply using the defined intent taxonomy. "
            "Do not infer interest that the recipient did not express."
        ),
        "criteria": {
            "interested": "The recipient expresses interest without requesting a meeting.",
            "meeting_requested": "The recipient asks to schedule or discuss a meeting.",
            "more_information": "The recipient requests details, pricing or documentation.",
            "referral": "The recipient points to another relevant person.",
            "not_now": "The recipient asks to revisit the topic later.",
            "objection": "The recipient raises a concern or reason not to proceed.",
            "wrong_person": "The recipient says they are not responsible for this topic.",
            "out_of_office": "The recipient indicates an absence or return date.",
            "not_interested": "The recipient declines further engagement.",
            "opt_out": "The recipient asks to stop marketing or unsubscribe.",
            "ambiguous": "The reply does not support a reliable intent classification.",
        },
    },
    "follow_up_recommended": {
        "type": "noul",
        "instructions": (
            "Does this reply call for an appropriate next step? "
            "A next step may be a handoff, requested information, a pause "
            "or human review. It does not mean an automatic marketing email."
        ),
    },
}


NO_FOLLOW_UP_INTENTS = {
    "not_interested",
    "opt_out",
}


REPLY_ACTIONS = {
    "interested": "handoff_to_sales",
    "meeting_requested": "handoff_to_sales",
    "more_information": "prepare_requested_information",
    "referral": "review_referral",
    "not_now": "schedule_later_after_date_confirmation",
    "objection": "human_review",
    "wrong_person": "human_review",
    "out_of_office": "pause_until_return_date_confirmation",
    "not_interested": "stop_sequence",
    "opt_out": "suppress_marketing",
    "ambiguous": "human_review",
}


def route_reply(
    predicted_intent,
    model_follow_up_recommended,
    contact_is_suppressed,
    explicit_opt_out_event,
):
    if isinstance(contact_is_suppressed, np.bool_):
        contact_is_suppressed = bool(contact_is_suppressed)
    if isinstance(explicit_opt_out_event, np.bool_):
        explicit_opt_out_event = bool(explicit_opt_out_event)

    if (
        contact_is_suppressed is True
        or explicit_opt_out_event is True
        or predicted_intent == "opt_out"
    ):
        return {
            "action": "suppress_marketing",
            "model_follow_up_recommended": (
                model_follow_up_recommended
                if isinstance(model_follow_up_recommended, (bool, np.bool_))
                else None
            ),
            "policy_follow_up_recommended": False,
            "send": False,
        }

    if (
        contact_is_suppressed is not False
        or explicit_opt_out_event is not False
    ):
        return {
            "action": "verify_suppression_and_opt_out_status",
            "model_follow_up_recommended": None,
            "policy_follow_up_recommended": False,
            "send": False,
        }

    if not isinstance(model_follow_up_recommended, (bool, np.bool_)):
        return {
            "action": "human_review",
            "reason": "invalid_follow_up_model_output",
            "model_follow_up_recommended": None,
            "policy_follow_up_recommended": False,
            "send": False,
        }

    model_follow_up_recommended = bool(model_follow_up_recommended)

    if predicted_intent not in REPLY_ACTIONS:
        return {
            "action": "human_review",
            "reason": "unknown_reply_intent",
            "model_follow_up_recommended": model_follow_up_recommended,
            "policy_follow_up_recommended": False,
            "send": False,
        }

    policy_follow_up_recommended = (
        predicted_intent not in NO_FOLLOW_UP_INTENTS
    )

    if not policy_follow_up_recommended:
        return {
            "action": REPLY_ACTIONS[predicted_intent],
            "model_follow_up_recommended": model_follow_up_recommended,
            "policy_follow_up_recommended": False,
            "send": False,
        }

    if not model_follow_up_recommended:
        return {
            "action": "human_review",
            "reason": "intent_and_follow_up_decisions_disagree",
            "model_follow_up_recommended": False,
            "policy_follow_up_recommended": True,
            "send": False,
        }

    return {
        "action": REPLY_ACTIONS[predicted_intent],
        "model_follow_up_recommended": True,
        "policy_follow_up_recommended": True,
        "send": False,
    }
