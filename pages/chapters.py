"""
Chapter configuration for ARENA 3.0 curriculum.
Each chapter has a color, description, and list of sections.
"""

import re


def _extract_section_number(path: str) -> str:
    """Extract section number from path like '01_[0.1]_Ray_Tracing.md' -> '0.1'."""
    match = re.search(r'\[([^\]]+)\]', path)
    if match:
        return match.group(1)
    return ""


CHAPTERS = {
    "chapter0_fundamentals": {
        "title": "Chapter 0: Fundamentals",
        "short_title": "Fundamentals",
        "description": "Build your foundation in deep learning, from prerequisites through CNNs, optimization, backpropagation, and generative models.",
        "color": "#4F46E5",  # Indigo
        "icon": "foundation",
        "sections": [
            {
                "id": "00_prereqs",
                "title": "Prerequisites",
                "path": "chapter0_fundamentals/instructions/pages/00_[0.0]_Prerequisites.md",
                "python_path": "chapter0_fundamentals/exercises/part0_prereqs/solutions.py",
            },
            {
                "id": "01_ray_tracing",
                "title": "Ray Tracing",
                "path": "chapter0_fundamentals/instructions/pages/01_[0.1]_Ray_Tracing.md",
                "python_path": "chapter0_fundamentals/exercises/part1_ray_tracing/solutions.py",
            },
            {
                "id": "02_cnns",
                "title": "CNNs & ResNets",
                "path": "chapter0_fundamentals/instructions/pages/02_[0.2]_CNNs_&_ResNets.md",
                "python_path": "chapter0_fundamentals/exercises/part2_cnns/solutions.py",
            },
            {
                "id": "03_optimization",
                "title": "Optimization",
                "path": "chapter0_fundamentals/instructions/pages/03_[0.3]_Optimization.md",
                "python_path": "chapter0_fundamentals/exercises/part3_optimization/solutions.py",
            },
            {
                "id": "04_backprop",
                "title": "Backpropagation",
                "path": "chapter0_fundamentals/instructions/pages/04_[0.4]_Backprop.md",
                "python_path": "chapter0_fundamentals/exercises/part4_backprop/solutions.py",
            },
            {
                "id": "05_vaes_gans",
                "title": "VAEs & GANs",
                "path": "chapter0_fundamentals/instructions/pages/05_[0.5]_VAEs_&_GANs.md",
                "python_path": "chapter0_fundamentals/exercises/part5_vaes_and_gans/solutions.py",
            },
        ],
    },
    "chapter1_transformer_interp": {
        "title": "Chapter 1: Transformer Interpretability",
        "short_title": "Interpretability",
        "description": "Dive deep into language model interpretability, from linear probes and SAEs to alignment faking and thought anchors.",
        "color": "#059669",  # Emerald
        "icon": "microscope",
        "sections": [
            # Core sections (1.1, 1.2)
            {
                "id": "01_transformers",
                "title": "Transformers from Scratch",
                "path": "chapter1_transformer_interp/instructions/pages/01_[1.1]_Transformer_from_Scratch.md",
                "python_path": "chapter1_transformer_interp/exercises/part1_transformer_from_scratch/solutions.py",
            },
            {
                "id": "02_intro_mech_interp",
                "title": "Intro to Mech Interp",
                "path": "chapter1_transformer_interp/instructions/pages/02_[1.2]_Intro_to_Mech_Interp.md",
                "python_path": "chapter1_transformer_interp/exercises/part2_intro_to_mech_interp/solutions.py",
            },
            # Group 1.3: Probing and Representations
            {
                "id": "1_3_overview",
                "title": "Probing and Representations",
                "local_path": "1_3_probing_and_representations.md",
                "number": "1.3",
                "is_group": True,
                "children": ["11_probing", "12_function_vectors", "13_saes"],
            },
            {
                "id": "11_probing",
                "title": "Probing for Deception",
                "path": "chapter1_transformer_interp/instructions/pages/11_[1.3.1]_Probing_for_Deception.md",
                "python_path": "chapter1_transformer_interp/exercises/part31_probing_for_deception/solutions.py",
                "parent": "1_3_overview",
            },
            {
                "id": "12_function_vectors",
                "title": "Function Vectors & Model Steering",
                "path": "chapter1_transformer_interp/instructions/pages/12_[1.3.2]_Function_Vectors_&_Model_Steering.md",
                "python_path": "chapter1_transformer_interp/exercises/part32_function_vectors_and_model_steering/solutions.py",
                "parent": "1_3_overview",
            },
            {
                "id": "13_saes",
                "title": "Interpretability with SAEs",
                "path": "chapter1_transformer_interp/instructions/pages/13_[1.3.3]_Interpretability_with_SAEs.md",
                "python_path": "chapter1_transformer_interp/exercises/part33_interp_with_saes/solutions.py",
                "parent": "1_3_overview",
            },
            # Group 1.4: Circuits in LLMs
            {
                "id": "1_4_overview",
                "title": "Circuits in LLMs",
                "local_path": "1_4_circuits_in_llms.md",
                "number": "1.4",
                "is_group": True,
                "children": ["21_ioi", "22_sae_circuits"],
            },
            {
                "id": "21_ioi",
                "title": "Indirect Object Identification",
                "path": "chapter1_transformer_interp/instructions/pages/21_[1.4.1]_Indirect_Object_Identification.md",
                "python_path": "chapter1_transformer_interp/exercises/part41_indirect_object_identification/solutions.py",
                "parent": "1_4_overview",
            },
            {
                "id": "22_sae_circuits",
                "title": "SAE Circuits",
                "path": "chapter1_transformer_interp/instructions/pages/22_[1.4.2]_SAE_Circuits.md",
                "python_path": "chapter1_transformer_interp/exercises/part42_sae_circuits/solutions.py",
                "parent": "1_4_overview",
            },
            # Group 1.5: Toy Models
            {
                "id": "1_5_overview",
                "title": "Toy Models",
                "local_path": "1_5_toy_models.md",
                "number": "1.5",
                "is_group": True,
                "children": ["31_brackets", "32_grokking", "33_othellogpt", "34_superposition"],
            },
            {
                "id": "31_brackets",
                "title": "Balanced Bracket Classifier",
                "path": "chapter1_transformer_interp/instructions/pages/31_[1.5.1]_Balanced_Bracket_Classifier.md",
                "python_path": "chapter1_transformer_interp/exercises/part51_balanced_bracket_classifier/solutions.py",
                "parent": "1_5_overview",
            },
            {
                "id": "32_grokking",
                "title": "Grokking & Modular Arithmetic",
                "path": "chapter1_transformer_interp/instructions/pages/32_[1.5.2]_Grokking_&_Modular_Arithmetic.md",
                "python_path": "chapter1_transformer_interp/exercises/part52_grokking_and_modular_arithmetic/solutions.py",
                "parent": "1_5_overview",
            },
            {
                "id": "33_othellogpt",
                "title": "OthelloGPT",
                "path": "chapter1_transformer_interp/instructions/pages/33_[1.5.3]_OthelloGPT.md",
                "python_path": "chapter1_transformer_interp/exercises/part53_othellogpt/solutions.py",
                "parent": "1_5_overview",
            },
            {
                "id": "34_superposition",
                "title": "Superposition & SAEs",
                "path": "chapter1_transformer_interp/instructions/pages/34_[1.5.4]_Toy_Models_of_Superposition_&_SAEs.md",
                "python_path": "chapter1_transformer_interp/exercises/part54_toy_models_of_superposition_and_saes/solutions.py",
                "parent": "1_5_overview",
            },
            # Group 1.6: Case Studies in Larger Models
            {
                "id": "1_6_overview",
                "title": "Case Studies in Larger Models",
                "local_path": "1_6_case_studies.md",
                "number": "1.6",
                "is_group": True,
                "children": ["41_emergent_misalignment", "42_science_misalignment", "43_eliciting_knowledge", "44_reasoning_models"],
            },
            {
                "id": "41_emergent_misalignment",
                "title": "Emergent Misalignment",
                "path": "chapter1_transformer_interp/instructions/pages/41_[1.6.1]_Emergent_Misalignment.md",
                "python_path": "chapter1_transformer_interp/exercises/part61_emergent_misalignment/solutions.py",
                "parent": "1_6_overview",
            },
            {
                "id": "42_science_misalignment",
                "title": "Science of Misalignment",
                "path": "chapter1_transformer_interp/instructions/pages/42_[1.6.2]_Science_of_Misalignment.md",
                "python_path": "chapter1_transformer_interp/exercises/part62_science_of_misalignment/solutions.py",
                "parent": "1_6_overview",
            },
            {
                "id": "43_eliciting_knowledge",
                "title": "Eliciting Secret Knowledge",
                "path": "chapter1_transformer_interp/instructions/pages/43_[1.6.3]_Eliciting_Secret_Knowledge.md",
                "python_path": "chapter1_transformer_interp/exercises/part63_eliciting_secret_knowledge/solutions.py",
                "parent": "1_6_overview",
            },
            {
                "id": "44_reasoning_models",
                "title": "Interpreting Reasoning Models",
                "path": "chapter1_transformer_interp/instructions/pages/44_[1.6.4]_Interpreting_Reasoning_Models.md",
                "python_path": "chapter1_transformer_interp/exercises/part64_interpreting_reasoning_models/solutions.py",
                "parent": "1_6_overview",
            },
        ],
    },
    "chapter2_rl": {
        "title": "Chapter 2: Reinforcement Learning",
        "short_title": "RL",
        "description": "Take a whirlwind tour through RL, starting from tabular learning and Atari, and ending with some of the cutting-edge techniques used in current LLM post-training.",
        "color": "#D97706",  # Amber
        "icon": "gamepad",
        "sections": [
            {
                "id": "01_intro_rl",
                "title": "Intro to RL",
                "path": "chapter2_rl/instructions/pages/01_[2.1]_Intro_to_RL.md",
                "python_path": "chapter2_rl/exercises/part1_intro_to_rl/solutions.py",
            },
            {
                "id": "21_dqn",
                "title": "Deep Q-Networks",
                "path": "chapter2_rl/instructions/pages/21_[2.2.1]_DQN.md",
                "python_path": "chapter2_rl/exercises/part21_dqn/solutions.py",
            },
            {
                "id": "22_vpg",
                "title": "Vanilla Policy Gradient",
                "path": "chapter2_rl/instructions/pages/22_[2.2.2]_VPG.md",
                "python_path": "chapter2_rl/exercises/part22_vpg/solutions.py",
            },
            {
                "id": "03_ppo",
                "title": "PPO",
                "path": "chapter2_rl/instructions/pages/03_[2.3]_PPO.md",
                "python_path": "chapter2_rl/exercises/part3_ppo/solutions.py",
            },
            {
                "id": "04_rlhf",
                "title": "RLHF",
                "path": "chapter2_rl/instructions/pages/04_[2.4]_RLHF.md",
                "python_path": "chapter2_rl/exercises/part4_rlhf/solutions.py",
            },
        ],
    },
    "chapter3_llm_evals": {
        "title": "Chapter 3: LLM Evaluations",
        "short_title": "Evals",
        "description": "Learn to build and run evaluations for large language models, including dataset generation and LLM agents.",
        "color": "#DC2626",  # Red
        "icon": "clipboard-check",
        "sections": [
            {
                "id": "01_intro_evals",
                "title": "Intro to Evals",
                "path": "chapter3_llm_evals/instructions/pages/01_[3.1]_Intro_to_Evals.md",
                "python_path": "chapter3_llm_evals/exercises/part1_intro_to_evals/solutions.py",
            },
            {
                "id": "02_dataset_gen",
                "title": "Dataset Generation",
                "path": "chapter3_llm_evals/instructions/pages/02_[3.2]_Dataset_Generation.md",
                "python_path": "chapter3_llm_evals/exercises/part2_dataset_generation/solutions.py",
            },
            {
                "id": "03_running_evals",
                "title": "Running Evals with Inspect",
                "path": "chapter3_llm_evals/instructions/pages/03_[3.3]_Running_Evals_with_Inspect.md",
                "python_path": "chapter3_llm_evals/exercises/part3_running_evals_with_inspect/solutions.py",
            },
            {
                "id": "04_llm_agents",
                "title": "LLM Agents",
                "path": "chapter3_llm_evals/instructions/pages/04_[3.4]_LLM_Agents.md",
                "python_path": "chapter3_llm_evals/exercises/part4_llm_agents/solutions.py",
            },
        ],
    },
}


def get_chapter(chapter_id: str) -> dict | None:
    """Get a chapter by its ID, with section numbers included."""
    chapter = CHAPTERS.get(chapter_id)
    if not chapter:
        return None
    # Add section numbers extracted from paths (for non-group sections)
    result = dict(chapter)
    result["sections"] = []
    for section in chapter["sections"]:
        section_copy = dict(section)
        # Group sections already have their number set
        if not section_copy.get("is_group") and not section_copy.get("number"):
            section_copy["number"] = _extract_section_number(section.get("path", ""))
        result["sections"].append(section_copy)
    return result


def get_section(chapter_id: str, section_id: str) -> dict | None:
    """Get a section by chapter and section ID."""
    chapter = get_chapter(chapter_id)
    if not chapter:
        return None
    for section in chapter["sections"]:
        if section["id"] == section_id:
            return section
    return None


def get_all_chapters() -> list[dict]:
    """Get all chapters as a list with their IDs included."""
    result = []
    for chapter_id in CHAPTERS:
        chapter = get_chapter(chapter_id)
        if chapter:
            # Count only actual content sections (excluding group headers)
            section_count = sum(1 for s in chapter["sections"] if not s.get("is_group"))
            result.append({"id": chapter_id, "section_count": section_count, **chapter})
    return result


def count_sections(chapter_id: str) -> int:
    """Count the number of actual sections (excluding group headers)."""
    chapter = get_chapter(chapter_id)
    if not chapter:
        return 0
    return sum(1 for s in chapter["sections"] if not s.get("is_group"))
