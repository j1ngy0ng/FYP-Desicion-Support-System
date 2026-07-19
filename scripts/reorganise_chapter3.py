from copy import deepcopy
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "Ng Jing Yong FYP Report.docx"
OUTPUT = ROOT / "docs" / "Ng Jing Yong FYP Report - Chapter 3 Reorganised.docx"


doc = Document(SOURCE)
body = doc.element.body
blocks = list(body.iterchildren())


def block_text(element):
    if element.tag != qn("w:p"):
        return ""
    return Paragraph(element, doc).text.strip()


def locate(text, start=0):
    for i in range(start, len(blocks)):
        if block_text(blocks[i]) == text:
            return i
    raise ValueError(f"Could not find paragraph: {text}")


def locate_starts(text, start=0):
    for i in range(start, len(blocks)):
        if block_text(blocks[i]).startswith(text):
            return i
    raise ValueError(f"Could not find paragraph beginning: {text}")


chapter3 = locate("Chapter 3")
chapter4 = locate("Chapter 4", chapter3 + 1)


def segment(start_text, end_text):
    start = locate(start_text, chapter3)
    end = locate(end_text, start + 1)
    return blocks[start:end]


def content_after_heading(start_text, end_text):
    items = segment(start_text, end_text)
    return items[1:]


def clone_paragraph(template_element, text, style_name=None):
    element = deepcopy(template_element)
    paragraph = Paragraph(element, doc)
    paragraph.text = text
    if style_name:
        paragraph.style = style_name
    return element


heading2_template = blocks[locate("Research Methodology Overview", chapter3)]
normal_template = blocks[locate_starts("This research adopts a design science research approach", chapter3)]


def h2(text):
    return clone_paragraph(heading2_template, text, "Heading 2")


def h3(text):
    return clone_paragraph(heading2_template, text, "Heading 3")


def para(text):
    return clone_paragraph(normal_template, text, "Normal Indent")


def keep_nonempty(items):
    kept = []
    for element in items:
        if element.tag == qn("w:tbl") or block_text(element):
            kept.append(element)
    return kept


intro_existing = blocks[locate_starts("This chapter presents the methodology for the proposed Intent-Aware", chapter3):locate("Research Methodology Overview", chapter3)]
research_approach = content_after_heading("Research Approach", "Mapping of Research Objectives, Questions and Evaluation")
mapping = content_after_heading("Mapping of Research Objectives, Questions and Evaluation", "Experimental Design Framework")
experimental_framework = content_after_heading("Experimental Design Framework", "System Development Methodology")
development = content_after_heading("Development Strategy", "System Pipeline Overview")
pipeline = content_after_heading("System Pipeline Overview", "Data Requirements and Preparation")
dataset_requirements = content_after_heading("Dataset Requirements", "Data Sources and Feature Scope")
data_sources = content_after_heading("Data Sources and Feature Scope", "Decision Case Construction")
decision_cases = content_after_heading("Decision Case Construction", "Preprocessing, Splitting and Leakage Control")
preprocessing = content_after_heading("Preprocessing, Splitting and Leakage Control", "AI Pipeline Components")
ai_pipeline = content_after_heading("AI Pipeline Components", "Evaluation Methodology")
baselines = content_after_heading("Baseline Systems", "Ablation Study Design")
ablations = content_after_heading("Ablation Study Design", "Evaluation Metrics and Acceptance Criteria")
metrics = content_after_heading("Evaluation Metrics and Acceptance Criteria", "Human Evaluation Procedure")
human_eval = content_after_heading("Human Evaluation Procedure", "Statistical Analysis")
statistics = content_after_heading("Statistical Analysis", "Ethical Considerations, Reliability and Study Limitations")
ethics = content_after_heading("Ethical Considerations", "Privacy and Data Governance")
privacy = content_after_heading("Privacy and Data Governance", "Experimental Reliability and Reproducibility")
reliability = content_after_heading("Experimental Reliability and Reproducibility", "Study Limitations")
limitations = content_after_heading("Study Limitations", "Tools, Software, Hardware and Reproducibility")
tools = content_after_heading("Tools, Software, Hardware and Reproducibility", "Requirement Gathering Techniques")
requirements = content_after_heading("Requirement Gathering Techniques", "Chapter Summary and Evaluation")
summary = content_after_heading("Chapter Summary and Evaluation", "Chapter 4")


# Remove obsolete section-navigation paragraph and retain the opening framework figure/caption.
intro_existing = [e for e in intro_existing if not block_text(e).startswith("The chapter is organised to preserve")]

new_blocks = []
new_blocks.extend(blocks[chapter3:locate_starts("This chapter presents the methodology for the proposed Intent-Aware", chapter3)])

new_blocks.append(h2("Chapter Introduction"))
new_blocks.extend(keep_nonempty(intro_existing))
new_blocks.append(para(
    "Accordingly, this chapter defines the research design and workflow, research question and objective mapping, "
    "dataset and ground-truth preparation, preprocessing and leakage prevention, baseline selection, proposed AI "
    "method, experimental protocol, evaluation metrics, validation procedures, tools and reproducibility controls, "
    "and ethical, privacy, security and validity considerations."
))

new_blocks.append(h2("Research Design or Framework"))
new_blocks.extend(keep_nonempty(research_approach))
new_blocks.extend(keep_nonempty(requirements))
new_blocks.append(h3("Development Strategy and Research Workflow"))
new_blocks.extend(keep_nonempty(development))
new_blocks.extend(keep_nonempty(experimental_framework[-2:]))  # methodology framework caption and table

new_blocks.append(h2("Research Question and Objective Mapping"))
new_blocks.extend(keep_nonempty(mapping))

new_blocks.append(h2("Dataset, Corpus or Data Source"))
new_blocks.extend(keep_nonempty(dataset_requirements))
new_blocks.extend(keep_nonempty(data_sources))
new_blocks.append(para(
    "The target benchmark contains at least 500 campaign-period records covering at least three marketing channels "
    "and six months of observations. Its unit of analysis is the campaign-period record. Input fields cover campaign "
    "context, channel exposure, engagement, cost and outcome variables; derived fields include click-through rate, "
    "conversion rate, cost per acquisition, revenue per conversion, ROI band, engagement band and channel saturation. "
    "The controlled labels are the business-intent classes Survival, Retention and Growth and the recommendation "
    "classes Increase, Maintain, Decrease and Investigate. The final record count, class distribution and excluded "
    "records are reported after the reproducible data audit."
))

new_blocks.append(h2("Data Collection, Sampling and Ground Truth"))
new_blocks.extend(keep_nonempty(decision_cases))
new_blocks.append(para(
    "Records are included when the fields needed to compute the selected performance, cost and outcome indicators are "
    "available or can be handled by a predefined missing-value rule. Duplicated records, unusable records and cases "
    "whose labels remain unresolved after review are excluded. Sampling preserves representation across channel and "
    "intent classes; where usable dates exist, chronological ordering is retained for splitting. The Kaggle dataset is "
    "accessed only under the access conditions published with the source and is stored in the controlled project "
    "workspace. Because the benchmark uses secondary campaign-level data and excludes personally identifiable customer "
    "information, individual customer consent is not collected; any separate human evaluation follows participant "
    "information and voluntary-consent procedures."
))
new_blocks.append(para(
    "Ground-truth recommendation and intent labels are prepared using documented definitions for the three intents and "
    "four actions. Label quality is checked through independent review where more than one annotator is available. "
    "Cohen's Kappa measures nominal agreement beyond chance, disagreements are discussed against the written labelling "
    "rules, and cases that cannot be resolved are removed before the benchmark is frozen."
))

new_blocks.append(h2("Data Preprocessing and Leakage Prevention"))
new_blocks.extend(keep_nonempty(preprocessing))

new_blocks.append(h2("Baseline Selection and Justification"))
new_blocks.extend(keep_nonempty(baselines))
new_blocks.append(para(
    "For a fair comparison, every baseline receives the same prepared decision cases, uses the same four-action output "
    "space and is evaluated on the identical frozen test subset. Thresholds, model parameters and calibration choices "
    "are selected using training or validation data only. No baseline is allowed access to test labels, additional "
    "features or a different sampling procedure."
))

new_blocks.append(h2("Proposed Method or Approach"))
new_blocks.extend(keep_nonempty(pipeline))
new_blocks.extend(keep_nonempty(ai_pipeline))

new_blocks.append(h2("Experimental Design"))
new_blocks.extend(keep_nonempty(experimental_framework[:-2]))
new_blocks.extend(keep_nonempty(ablations))
new_blocks.append(para(
    "Training, validation and test partitions remain identical across the full framework, baselines and ablations. "
    "Training fits predictive parameters; validation supports hyperparameter selection, rule-weight selection where "
    "applicable and temperature scaling; testing is performed once for final comparison. Fixed random seeds and logged "
    "configurations control stochastic variation. If repeated stochastic runs are required, the same predefined seed "
    "set is applied to every configuration and aggregate results are reported. Fairness controls include identical "
    "features, action labels, test cases, compute setting and metric implementations across comparison groups."
))

new_blocks.append(h2("Evaluation Metrics and Acceptance Criteria"))
new_blocks.extend(keep_nonempty(metrics))
new_blocks.append(para(
    "Recommendation Accuracy is the number of test cases whose recommended action matches the benchmark action divided "
    "by the total number of test cases; higher values are better. Scenario-Fit Rate is the proportion of recommendations "
    "judged compatible with the assigned intent; higher values are better. Logical Conflict Rate is the proportion of "
    "recommendations that violate at least one predefined important constraint; lower values are better. Expected "
    "Calibration Error is the confidence-weighted average absolute difference between mean confidence and empirical "
    "accuracy across confidence bins; lower values indicate better calibration."
))
new_blocks.append(para(
    "Actionability and Explanation Usefulness are mean five-point participant ratings, where higher scores indicate more "
    "practical and reviewable outputs. Overtrust Rate is the proportion of incorrect or low-confidence recommendations "
    "that participants indicate they would accept without further checking; lower values are better. Recommendation "
    "Latency is elapsed time from a submitted decision case to the complete recommendation package; lower values are "
    "better provided that decision quality is preserved. Acceptance is determined by the directional criteria in Table "
    "3.6 and by whether the full framework improves the objective-linked metric over the corresponding baseline or ablation."
))
new_blocks.extend(keep_nonempty(statistics))

new_blocks.append(h2("Testing and Validation Procedures"))
new_blocks.extend(keep_nonempty(human_eval))
new_blocks.append(para(
    "Model validation compares predictions, recommendations, confidence and rule activations with frozen benchmark "
    "labels and constraint definitions. Functional validation verifies that campaign input, preprocessing, prediction, "
    "candidate generation, rule scoring, intent selection, calibration, explanation and recommendation logging produce "
    "the expected outputs. Reliability validation reruns controlled configurations from recorded seeds and parameters. "
    "Usability validation uses the participant procedure above, while security and privacy checks verify access control, "
    "data minimisation, exclusion of personally identifiable information and aggregate reporting. Failed cases and "
    "unexpected outputs are logged for correction and regression testing."
))

new_blocks.append(h2("Tools, Software, Hardware and Reproducibility"))
new_blocks.extend(keep_nonempty(tools))

new_blocks.append(h2("Ethical, Privacy, Security and Validity Considerations"))
new_blocks.append(h3("Ethical Considerations"))
new_blocks.extend(keep_nonempty(ethics))
new_blocks.append(h3("Privacy and Data Governance"))
new_blocks.extend(keep_nonempty(privacy))
new_blocks.append(h3("Experimental Reliability and Reproducibility"))
new_blocks.extend(keep_nonempty(reliability))
new_blocks.append(h3("Study Limitations and Validity"))
new_blocks.extend(keep_nonempty(limitations))
new_blocks.append(para(
    "Internal validity is protected through a frozen test set, identical comparison cases and component-removal "
    "experiments, although benchmark labelling and rule definitions may still introduce judgement bias. Construct "
    "validity is supported by mapping each objective to explicit technical and human-centred metrics, while recognising "
    "that bounded actionability and scenario-fit measures cannot represent every managerial judgement. External validity "
    "is limited by the use of one secondary benchmark and three simplified SME intents. Conclusion validity is supported "
    "by confidence intervals, multiple-comparison correction and practical-significance interpretation, but findings "
    "remain subject to benchmark size and participant coverage."
))

new_blocks.append(h2("Chapter Summary"))
new_blocks.extend(keep_nonempty(summary))
new_blocks.append(para(
    "Chapter 4 translates this approved methodology into the system architecture, module design, database design, "
    "algorithms, security controls and user-interface implementation of the prototype."
))

# Replace only the Chapter 3 body; preserve all other chapters and document parts.
for element in blocks[chapter3:chapter4]:
    body.remove(element)

chapter4_element = next(e for e in body.iterchildren() if block_text(e) == "Chapter 4")
insert_at = list(body.iterchildren()).index(chapter4_element)
for offset, element in enumerate(new_blocks):
    body.insert(insert_at + offset, element)

# Renumber Chapter 3 figures and tables in their new reading order. Temporary
# tokens prevent cascading replacements (for example, old Table 3.1 -> 3.2).
renumber = {
    "Figure 3.1": "Figure 3.1",
    "Figure 3.7": "Figure 3.2",
    "Figure 3.3": "Figure 3.3",
    "Figure 3.2": "Figure 3.4",
    "Figure 3.4": "Figure 3.5",
    "Figure 3.5": "Figure 3.6",
    "Figure 3.6": "Figure 3.7",
    "Table 3.2": "Table 3.1",
    "Table 3.1": "Table 3.2",
    "Table 3.4": "Table 3.3",
    "Table 3.3": "Table 3.4",
    "Table 3.5": "Table 3.5",
    "Table 3.6": "Table 3.6",
    "Table 3.7": "Table 3.7",
    "Table 3.8": "Table 3.8",
    "Table 3.9": "Table 3.9",
}

for paragraph in doc.paragraphs:
    if not paragraph.text:
        continue
    revised = paragraph.text
    for number, old in enumerate(renumber):
        revised = revised.replace(old, f"[[CH3REF{number}]]")
    for number, new in enumerate(renumber.values()):
        revised = revised.replace(f"[[CH3REF{number}]]", new)
    if revised != paragraph.text:
        paragraph.text = revised

doc.save(OUTPUT)
print(OUTPUT)
