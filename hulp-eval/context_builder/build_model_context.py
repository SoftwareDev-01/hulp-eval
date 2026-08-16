"""
PII Context Builder — field-level classification and minimization of
available_context data before it enters the model prompt.

Each field is classified as: keep, generalise, tokenise, or exclude.
This ensures data minimisation while preserving task-relevant information.
"""

import re
from datetime import datetime, date


# ─── Field-level policy ───────────────────────────────────────────────────────
FIELD_POLICY = {
    # Names — tokenise for stable aliases, keep when needed for personalization
    "client_full_name": {
        "action": "tokenise",
        "purpose": "stable reference in reasoning",
    },
    "traveller_full_name": {
        "action": "tokenise",
        "purpose": "stable alias for constraint tracking",
    },
    "child_full_name": {
        "action": "tokenise",
        "purpose": "stable alias for constraint tracking",
    },
    "recipient_full_name": {
        "action": "keep",
        "purpose": "may affect personalization (e.g. hamper)",
    },

    # Phone numbers — always exclude (execution-only data)
    "client_phone": {
        "action": "exclude",
        "purpose": "execution-only — attach at booking/dispatch time",
    },
    "traveller_phone": {
        "action": "exclude",
        "purpose": "execution-only — attach at booking/dispatch time",
    },
    "recipient_phone": {
        "action": "exclude",
        "purpose": "execution-only — attach at booking/dispatch time",
    },

    # Addresses — generalise to area/city level
    "home_address": {
        "action": "generalise",
        "generalise_to": "area",
        "purpose": "area-level sufficient for vendor matching",
    },
    "delivery_address": {
        "action": "generalise",
        "generalise_to": "city",
        "purpose": "city-level sufficient for vendor scoping",
    },

    # Security / access — always exclude
    "gate_code": {
        "action": "exclude",
        "purpose": "never needed for reasoning, high sensitivity",
    },
    "building_access_note": {
        "action": "exclude",
        "purpose": "security-sensitive, execution-only",
    },

    # Vendor / loyalty — exclude
    "vendor_loyalty_id": {
        "action": "exclude",
        "purpose": "never needed for reasoning",
    },

    # Government / identity documents — always exclude
    "aadhaar_number": {
        "action": "exclude",
        "purpose": "never needed for reasoning",
    },
    "insurance_policy_number": {
        "action": "exclude",
        "purpose": "never needed for reasoning",
    },
    "passport_number": {
        "action": "exclude",
        "purpose": "not needed for slot shortlisting",
    },
    "passport_scan_ocr": {
        "action": "exclude",
        "purpose": "raw document data, never needed",
    },

    # Date of birth — generalise to precise age (years + months) when relevant
    "date_of_birth": {
        "action": "generalise",
        "generalise_to": "precise_age",
        "purpose": "only when age is task-relevant (e.g. paediatric)",
    },

    # Medical — generalise to minimum task-relevant restriction
    "medical_history": {
        "action": "generalise",
        "purpose": "reduce to single task-relevant restriction",
    },

    # Payment — HARD EXCLUDE, must never enter model context or logs
    "payment_token_reference": {
        "action": "exclude",
        "purpose": "must NEVER enter model context or logs",
    },

    # Task-relevant fields — keep as-is
    "mobility_requirement": {
        "action": "keep",
        "purpose": "affects vehicle selection",
    },
    "preferred_area": {
        "action": "keep",
        "purpose": "location preference for search",
    },
    "saved_preferences": {
        "action": "keep",
        "purpose": "improves recommendation quality",
    },
    "preferred_passport_office": {
        "action": "keep",
        "purpose": "scheduling preference",
    },
    "relationship": {
        "action": "keep",
        "purpose": "low sensitivity, gives useful tone/context",
    },
    "usual_pickup_area": {
        "action": "keep",
        "purpose": "generalised location already",
    },
}


# ─── Generalisation helpers ───────────────────────────────────────────────────

def _generalise_address_to_area(address: str) -> str:
    """Extract area-level location from a full address."""
    # Simple heuristic: take the last 2-3 meaningful parts
    parts = [p.strip() for p in address.split(",")]
    if len(parts) >= 3:
        return ", ".join(parts[-2:])
    elif len(parts) == 2:
        return parts[-1]
    return address


def _generalise_address_to_city(address: str) -> str:
    """Extract city-level location from a full address."""
    parts = [p.strip() for p in address.split(",")]
    if parts:
        return parts[-1]
    return address


def _generalise_dob_to_precise_age(dob_str: str) -> str:
    """Convert date of birth to a precise synthetic age (years + months).
    
    This removes the actual DOB (PII) but preserves the exact numerical
    precision needed for clinical contexts like paediatrics.
    
    Examples:
        '2018-04-12' → 'Age: 8 years, 4 months'  (depending on today)
        '1987-09-14' → 'Age: 38 years, 11 months'
    """
    try:
        # Try common formats
        for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
            try:
                dob = datetime.strptime(dob_str, fmt).date()
                break
            except ValueError:
                continue
        else:
            return "age unknown"

        today = date.today()
        years = today.year - dob.year
        months = today.month - dob.month
        if today.day < dob.day:
            months -= 1
        if months < 0:
            years -= 1
            months += 12

        if years < 1:
            return f"Age: {months} month{'s' if months != 1 else ''}"
        else:
            year_str = f"{years} year{'s' if years != 1 else ''}"
            month_str = f"{months} month{'s' if months != 1 else ''}"
            return f"Age: {year_str}, {month_str}"
    except Exception:
        return "age unknown"


def _generalise_medical_history(history: str) -> str:
    """Reduce full medical history to task-relevant restriction."""
    # Extract allergy information and key conditions
    parts = []

    # Look for allergy info
    allergy_match = re.search(r"allerg\w+\s+to\s+(\w+)", history, re.IGNORECASE)
    if allergy_match:
        parts.append(f"allergic to {allergy_match.group(1)}")

    # Look for key conditions (seizure, asthma, diabetes, etc.)
    conditions = re.findall(
        r"(seizure|epilep|asthma|diabet|heart|hypertension|allerg)",
        history, re.IGNORECASE,
    )
    if conditions:
        # Deduplicate
        unique = list(dict.fromkeys(c.lower() for c in conditions))
        condition_str = "; ".join(unique)
        if parts:
            parts.insert(0, f"history: {condition_str}")
        else:
            parts.append(f"conditions: {condition_str}")

    if not parts:
        return "medical history present — share only with treating physician"

    return "; ".join(parts) + " — share only with treating physician"


def generalise_value(field: str, value: str, generalise_to: str | None = None) -> str:
    """Generalise a field value based on its type."""
    if generalise_to == "area":
        return _generalise_address_to_area(value)
    elif generalise_to == "city":
        return _generalise_address_to_city(value)
    elif generalise_to == "precise_age":
        return _generalise_dob_to_precise_age(value)
    elif field == "medical_history":
        return _generalise_medical_history(value)
    else:
        return value


# ─── Main builder ─────────────────────────────────────────────────────────────

def build_model_context(available_context: dict) -> dict:
    """
    Build a minimised model context from available_context.
    
    Applies field-level policies: keep, generalise, tokenise, or exclude.
    
    Returns:
        dict with:
        - model_payload: the data safe to send to the model
        - field_manifest: audit trail of decisions per field
        - token_map: mapping from tokens back to real values (for execution step)
    """
    model_payload = {}
    field_manifest = []
    token_map = {}
    token_counter = {}

    for field, value in available_context.items():
        policy = FIELD_POLICY.get(field, {
            "action": "exclude",
            "purpose": "unclassified — default to exclude",
        })
        action = policy["action"]

        if action == "keep":
            model_payload[field] = value

        elif action == "generalise":
            generalised = generalise_value(
                field, value, policy.get("generalise_to")
            )
            model_payload[field] = generalised

        elif action == "tokenise":
            # Generate a stable, unique token
            base = field.upper()
            count = token_counter.get(base, 0) + 1
            token_counter[base] = count
            token = f"{base}_{count}"
            token_map[token] = value
            model_payload[field] = token

        # action == "exclude": intentionally add nothing to model_payload

        field_manifest.append({
            "field": field,
            "action": action,
            "purpose": policy["purpose"],
            "downstream_attachment": (
                "resolved via token_map at execution step"
                if action == "tokenise"
                else None
            ),
        })

    return {
        "model_payload": model_payload,
        "field_manifest": field_manifest,
        "token_map": token_map,
    }
