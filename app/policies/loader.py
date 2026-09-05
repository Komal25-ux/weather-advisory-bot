import os
import glob
import logging
from typing import List
import yaml
from pydantic import ValidationError

from app.policies.models import SOPRule

logger = logging.getLogger("weather-advisory-bot.policies.loader")


class SOPPolicyLoadError(Exception):
    """Raised when an SOP file is malformed, invalid, or duplicate."""
    pass


def load_sops_from_directory(directory_path: str) -> List[SOPRule]:
    """
    Scans a directory for YAML files (*.yaml, *.yml), parses them,
    and strictly validates them against the SOPRule Pydantic schema.

    Fails fast on any malformed file or duplicate SOP ID.
    """
    if not os.path.exists(directory_path):
        raise SOPPolicyLoadError(f"SOP directory does not exist: {directory_path}")

    yaml_pattern = os.path.join(directory_path, "*.y*ml")
    yaml_files = sorted(glob.glob(yaml_pattern))

    if not yaml_files:
        logger.warning(f"No YAML SOP files found in {directory_path}")
        return []

    loaded_sops: List[SOPRule] = []
    seen_ids = set()

    for file_path in yaml_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = yaml.safe_load(f)

            if not content:
                continue

            # Support list of SOPs or single SOP object per file
            items = content if isinstance(content, list) else [content]

            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    raise SOPPolicyLoadError(
                        f"Invalid SOP item #{idx} in {file_path}: Expected a YAML dictionary, got {type(item)}"
                    )

                try:
                    sop_rule = SOPRule.model_validate(item)
                except ValidationError as ve:
                    sop_id = item.get("id", f"unknown_item_{idx}")
                    raise SOPPolicyLoadError(
                        f"Validation error in SOP '{sop_id}' ({file_path}):\n{ve}"
                    ) from ve

                if sop_rule.id in seen_ids:
                    raise SOPPolicyLoadError(
                        f"Duplicate SOP ID detected: '{sop_rule.id}' found in {file_path}"
                    )

                seen_ids.add(sop_rule.id)
                loaded_sops.append(sop_rule)

        except yaml.YAMLError as ye:
            raise SOPPolicyLoadError(f"YAML parsing error in {file_path}: {ye}") from ye

    logger.info(f"Successfully loaded and validated {len(loaded_sops)} SOPs from {directory_path}")
    return loaded_sops
