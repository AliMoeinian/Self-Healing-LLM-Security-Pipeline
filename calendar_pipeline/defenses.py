"""Conservative channel minimization for the fixed structured-calendar task.

No oracle or private-calendar lookup is used by either runtime defense. These
are deliberately broad policies, not semantic injection/leak classifiers.
"""

import copy

POLICY_VERSION = "calendar-channel-minimization-v1"
INPUT_PLACEHOLDER = "Participant prose omitted by input policy; use the validated scheduling attachments."
OUTPUT_TEMPLATES = {
    "publish": "Availability published.",
    "propose": "Scheduling proposal published.",
    "acknowledge": "I acknowledge this exact locally valid proposal.",
}
VARIANTS = (
    {"id": "none", "input": False, "output": False, "version": POLICY_VERSION},
    {"id": "input_only", "input": True, "output": False, "version": POLICY_VERSION},
    {"id": "output_only", "input": False, "output": True, "version": POLICY_VERSION},
    {"id": "both", "input": True, "output": True, "version": POLICY_VERSION},
)


def validate_policy(policy):
    if not isinstance(policy, dict) or policy not in VARIANTS:
        raise ValueError("Unknown or inconsistent versioned defense policy")
    # bool equality with integers is not a valid configuration.
    if type(policy["input"]) is not bool or type(policy["output"]) is not bool:
        raise ValueError("Defense switches must be booleans")


def input_patch(control):
    """Remove peer prose only; preserve routing, structured facts and actions."""
    result = copy.deepcopy(control)
    changes = []
    for message in result["incoming_messages"]:
        if set(message) != {"from", "phase", "content", "attachment"} or not isinstance(message["content"], str):
            raise ValueError("Input defense received an invalid routed message")
        original = message["content"]
        message["content"] = INPUT_PLACEHOLDER
        changes.append({"sender": message["from"], "phase": message["phase"], "original": original,
                        "delivered": INPUT_PLACEHOLDER})
    return result, changes


def output_patch(message):
    """Publish only a fixed phase phrase; action validity was checked earlier."""
    result = copy.deepcopy(message)
    if result["phase"] not in OUTPUT_TEMPLATES:
        raise ValueError("Unknown output-defense phase")
    original = result["content"]
    result["content"] = OUTPUT_TEMPLATES[result["phase"]]
    return result, {"original": original, "delivered": result["content"],
                    "changed": original != result["content"]}
