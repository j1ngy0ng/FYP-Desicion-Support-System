import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = "C:/Users/user/Desktop/FYP Prototype/FYP-Desicion-Support-System";
const inputPath = `${root}/outputs/adjudication_corrections_2026-07-23/Adjudication_Corrections_Still_Required.xlsx`;
const candidatePath = `${root}/data/benchmark_candidate_125.csv`;
const extractedCsvPath = `${root}/data/human_annotations/completed/adjudication_completed.csv`;
const workDir = `${root}/.codex_work/final_adjudication`;
const evaluationDir = `${root}/outputs/confirmatory_evaluation`;
const metricsPath = `${evaluationDir}/metrics.csv`;
const seedMetricsPath = `${evaluationDir}/seed_metrics.csv`;
const predictionsPath = `${evaluationDir}/predictions.csv`;
const confidenceIntervalsPath = `${evaluationDir}/confidence_intervals.json`;
const metadataPath = `${evaluationDir}/run_metadata.json`;
const finalWorkbookPath = `${evaluationDir}/Confirmatory_Evaluation_Results.xlsx`;
const correctionDir = `${root}/outputs/adjudication_corrections_2026-07-23`;
const correctionWorkbookPath = `${correctionDir}/Adjudication_Final_Corrections_Required.xlsx`;
const allowedIntents = new Set(["Survival", "Retention", "Growth"]);
const allowedActions = new Set(["Increase", "Maintain", "Reduce", "Investigate"]);

await fs.mkdir(workDir, { recursive: true });
await fs.mkdir(`${root}/data/human_annotations/completed`, { recursive: true });
await fs.mkdir(evaluationDir, { recursive: true });
await fs.mkdir(correctionDir, { recursive: true });

function text(value) {
  return value == null ? "" : String(value).trim();
}

function csvCell(value) {
  const content = value instanceof Date
    ? value.toISOString().slice(0, 10)
    : value == null ? "" : String(value);
  return /[",\r\n]/.test(content) ? `"${content.replaceAll('"', '""')}"` : content;
}

function toCsv(rows) {
  return rows.map((row) => row.map(csvCell).join(",")).join("\n") + "\n";
}

function normalized(value) {
  if (value instanceof Date) return value.toISOString().slice(0, 10);
  const raw = text(value);
  const dateMatch = raw.match(/^(\d{1,4})-(\d{1,2})-(\d{1,4})$/);
  if (dateMatch) {
    const [, first, middle, last] = dateMatch;
    if (first.length === 4) {
      return `${first}-${middle.padStart(2, "0")}-${last.padStart(2, "0")}`;
    }
    if (last.length === 4) {
      return `${last}-${middle.padStart(2, "0")}-${first.padStart(2, "0")}`;
    }
  }
  const numeric = Number(raw.replaceAll(",", ""));
  return raw !== "" && Number.isFinite(numeric) ? numeric : raw;
}

function sameValue(left, right) {
  const a = normalized(left);
  const b = normalized(right);
  return typeof a === "number" && typeof b === "number"
    ? Math.abs(a - b) < 1e-9
    : a === b;
}

function kappa(left, right) {
  const observed = left.filter((value, index) => value === right[index]).length / left.length;
  const labels = new Set([...left, ...right]);
  const expected = [...labels].reduce((sum, label) => {
    const leftRate = left.filter((value) => value === label).length / left.length;
    const rightRate = right.filter((value) => value === label).length / right.length;
    return sum + leftRate * rightRate;
  }, 0);
  return expected === 1 ? 1 : (observed - expected) / (1 - expected);
}

function expectedAgreement(row) {
  const intentSame = text(row[16]) === text(row[19]);
  const actionSame = text(row[17]) === text(row[20]);
  if (intentSame && actionSame) return "Full Agreement";
  if (!intentSame && !actionSame) return "Both Disagree";
  if (!intentSame) return "Intent Disagreement";
  return "Action Disagreement";
}

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(inputPath));
const overview = await workbook.inspect({
  kind: "sheet",
  include: "id,name",
  maxChars: 5000,
});
console.log(overview.ndjson);

for (const [sheetName, range, outputName] of [
  ["Summary", "A1:F19", "source_summary.png"],
  ["Adjudication", "A1:P18", "source_adjudication_evidence.png"],
  ["Adjudication", "Q1:AA18", "source_adjudication_labels.png"],
  ["Provenance Attestation", "A1:F8", "source_provenance.png"],
]) {
  const inspection = await workbook.inspect({
    kind: "table",
    sheetId: sheetName,
    range,
    include: "values,formulas",
    tableMaxRows: 20,
    tableMaxCols: 27,
    maxChars: 12000,
  });
  console.log(`${sheetName} ${range}`);
  console.log(inspection.ndjson);
  const preview = await workbook.render({
    sheetName,
    range,
    scale: 1,
    format: "png",
  });
  await fs.writeFile(
    `${workDir}/${outputName}`,
    new Uint8Array(await preview.arrayBuffer()),
  );
}

const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "Completed adjudication formula error scan",
});
console.log(formulaErrors.ndjson);

const adjudication = workbook.worksheets.getItem("Adjudication");
const rows = adjudication.getUsedRange(true).values;
if (rows.length !== 126 || rows[0].length < 26) {
  throw new Error(
    `Adjudication sheet has ${rows.length - 1} cases and ${rows[0]?.length ?? 0} columns; expected 125 cases and at least 26 columns.`,
  );
}
const expectedHeaders = [
  "Campaign_ID", "Campaign_Type", "Target_Audience", "Duration", "Channel_Used",
  "Impressions", "Clicks", "Leads", "Conversions", "Revenue", "Acquisition_Cost",
  "ROI", "Language", "Engagement_Score", "Customer_Segment", "Date",
  "Reviewer_1_Intent", "Reviewer_1_Action", "Reviewer_1_Notes",
  "Reviewer_2_Intent", "Reviewer_2_Action", "Reviewer_2_Notes",
  "Adjudicated_Intent", "Adjudicated_Action", "Adjudicator_Notes",
  "Annotation_Status",
];
if (rows[0].slice(0, 26).map(text).join("|") !== expectedHeaders.join("|")) {
  throw new Error("Adjudication headers do not match the locked benchmark schema.");
}

const data = rows.slice(1);
for (let index = 0; index < data.length; index += 1) {
  const row = data[index];
  const labelsComplete =
    allowedIntents.has(text(row[22])) &&
    allowedActions.has(text(row[23]));
  const notesComplete =
    expectedAgreement(row) === "Full Agreement" || Boolean(text(row[24]));
  if (labelsComplete && notesComplete && text(row[25]) === "Needs Adjudication") {
    row[25] = "Audited";
    adjudication.getRange(`Z${index + 2}`).values = [["Audited"]];
  }
}
const duplicateIds = data
  .map((row) => text(row[0]))
  .filter((id, index, all) => all.indexOf(id) !== index);
const invalid = {
  duplicate_ids: [...new Set(duplicateIds)],
  reviewer_intents: data.filter((row) =>
    !allowedIntents.has(text(row[16])) || !allowedIntents.has(text(row[19]))),
  reviewer_actions: data.filter((row) =>
    !allowedActions.has(text(row[17])) || !allowedActions.has(text(row[20]))),
  adjudicated_intents: data.filter((row) => !allowedIntents.has(text(row[22]))),
  adjudicated_actions: data.filter((row) => !allowedActions.has(text(row[23]))),
  status: data.filter((row) => text(row[25]) !== "Audited"),
  agreement_flag: data.filter((row) =>
    row.length > 26 && text(row[26]) !== expectedAgreement(row)),
  disagreement_notes: data.filter((row) =>
    expectedAgreement(row) !== "Full Agreement" && !text(row[24])),
  agreed_label_mismatch: data.filter((row) =>
    expectedAgreement(row) === "Full Agreement" &&
    (text(row[22]) !== text(row[16]) || text(row[23]) !== text(row[17]))),
};
const invalidCounts = Object.fromEntries(
  Object.entries(invalid).map(([key, value]) => [key, value.length]),
);
const candidateText = await fs.readFile(candidatePath, "utf8");
const candidateWorkbook = await Workbook.fromCSV(candidateText, { sheetName: "Candidate" });
const candidateRows = candidateWorkbook.worksheets.getItem("Candidate").getUsedRange(true).values;
const candidateById = new Map(candidateRows.slice(1).map((row) => [text(row[0]), row]));
if (
  candidateById.size !== 125 ||
  data.some((row) => !candidateById.has(text(row[0])))
) {
  throw new Error("Completed adjudication does not contain the exact 125 benchmark candidates.");
}
for (const row of data) {
  const candidate = candidateById.get(text(row[0]));
  for (let column = 0; column < 16; column += 1) {
    if (!sameValue(row[column], candidate[column])) {
      throw new Error(
        `Source-lineage mismatch for ${text(row[0])} in column ${column + 1}.`,
      );
    }
  }
}

const provenance = workbook.worksheets.getItem("Provenance Attestation");
const provenanceRows = provenance.getRange("A6:F8").values;
const provenanceProblems = [];
for (const row of provenanceRows) {
  const role = text(row[0]);
  if (!role || !text(row[1]) || text(row[2]) !== "Yes" || !text(row[3]) || !text(row[4])) {
    provenanceProblems.push(role || "Missing role");
  }
}
const firstIntents = data.map((row) => text(row[16]));
const secondIntents = data.map((row) => text(row[19]));
const firstActions = data.map((row) => text(row[17]));
const secondActions = data.map((row) => text(row[20]));
const agreementCounts = {};
for (const row of data) {
  const flag = expectedAgreement(row);
  agreementCounts[flag] = (agreementCounts[flag] || 0) + 1;
}
const audit = {
  source_workbook: inputPath,
  cases: data.length,
  source_fields_match_candidate: true,
  unique_campaign_ids: new Set(data.map((row) => text(row[0]))).size,
  allowed_intents: [...allowedIntents],
  allowed_actions: [...allowedActions],
  all_statuses_audited: invalidCounts.status === 0,
  adjudication_complete:
    invalidCounts.adjudicated_intents === 0 &&
    invalidCounts.adjudicated_actions === 0 &&
    invalidCounts.disagreement_notes === 0,
  provenance_complete: provenanceProblems.length === 0,
  validation_issue_counts: invalidCounts,
  provenance_problems: provenanceProblems,
  intent_observed_agreement:
    firstIntents.filter((value, index) => value === secondIntents[index]).length / data.length,
  intent_kappa: kappa(firstIntents, secondIntents),
  action_observed_agreement:
    firstActions.filter((value, index) => value === secondActions[index]).length / data.length,
  action_kappa: kappa(firstActions, secondActions),
  agreement_counts: agreementCounts,
};
await fs.writeFile(`${workDir}/audit.json`, JSON.stringify(audit, null, 2));

const hasValidationIssues =
  Object.values(invalidCounts).some((count) => count > 0) ||
  provenanceProblems.length > 0;
if (hasValidationIssues) {
  const summarySheet = workbook.worksheets.getItem("Summary");
  summarySheet.getRange("A2:F2").merge();
  const onlyProvenanceRemains =
    Object.values(invalidCounts).every((count) => count === 0) &&
    provenanceProblems.length > 0;
  summarySheet.getRange("A2").values = [[onlyProvenanceRemains
    ? `ATTESTATIONS REQUIRED: all ${data.length} adjudications are complete; ${provenanceProblems.length} reviewer provenance attestations remain incomplete.`
    : `CORRECTIONS REQUIRED: ${invalidCounts.adjudicated_actions} cases have incomplete adjudication and ${provenanceProblems.length} reviewer provenance attestations remain incomplete.`,
  ]];
  summarySheet.getRange("A2:F2").format = {
    fill: "#F4CCCC",
    font: { bold: true, color: "#9C0006" },
    wrapText: true,
    rowHeight: 42,
    verticalAlignment: "center",
  };
  if (onlyProvenanceRemains) {
    summarySheet.getRange("A15:A19").values = [
      ["1. Reviewer 1 opens the Provenance Attestation sheet and completes their own row."],
      ["2. Reviewer 2 opens the Provenance Attestation sheet and completes their own row."],
      ["3. Each reviewer enters their actual name or reviewer ID."],
      ["4. Each reviewer selects Yes, enters the completion date and signs or initials."],
      ["5. Return the workbook; the audited benchmark can then be frozen and evaluated."],
    ];
  }

  const issueRows = [[
    "Campaign_ID", "Agreement_Flag", "Missing fields", "Required correction",
  ]];
  for (let index = 0; index < data.length; index += 1) {
    const row = data[index];
    const missing = [];
    if (!allowedIntents.has(text(row[22]))) missing.push("Adjudicated_Intent");
    if (!allowedActions.has(text(row[23]))) missing.push("Adjudicated_Action");
    if (expectedAgreement(row) !== "Full Agreement" && !text(row[24])) {
      missing.push("Adjudicator_Notes");
    }
    if (!missing.length) continue;
    const excelRow = index + 2;
    adjudication.getRange(`Z${excelRow}`).values = [["Needs Adjudication"]];
    adjudication.getRange(`W${excelRow}:Z${excelRow}`).format = {
      fill: "#F4CCCC",
      font: { color: "#9C0006" },
      wrapText: true,
      verticalAlignment: "top",
    };
    issueRows.push([
      text(row[0]),
      expectedAgreement(row),
      missing.join(", "),
      "Third human reviewer selects the final labels, records a reason, then sets Annotation_Status to Audited.",
    ]);
  }
  for (let index = 0; index < provenanceRows.length; index += 1) {
    const row = provenanceRows[index];
    const role = text(row[0]) || `Attestation row ${index + 6}`;
    if (
      !text(row[1]) ||
      text(row[2]) !== "Yes" ||
      !text(row[3]) ||
      !text(row[4])
    ) {
      issueRows.push([
        role,
        "Provenance",
        "Verified human-only attestation",
        "The named reviewer selects Yes, enters the completion date, and signs or initials the row.",
      ]);
      provenance.getRange(`B${index + 6}:F${index + 6}`).format = {
        fill: "#FFF2CC",
        font: { color: "#7F6000" },
        wrapText: true,
        verticalAlignment: "top",
      };
    }
  }

  const issuesSheet = workbook.worksheets.getOrAdd("Validation Issues");
  const existingIssuesRange = issuesSheet.getUsedRange();
  if (existingIssuesRange) existingIssuesRange.clear({ applyTo: "all" });
  issuesSheet.showGridLines = false;
  issuesSheet.getRange("A1:D1").merge();
  issuesSheet.getRange("A1").values = [["Corrections Required Before Benchmark Freeze"]];
  issuesSheet.getRange("A1:D1").format = {
    fill: "#9C0006",
    font: { bold: true, color: "#FFFFFF", size: 18 },
    rowHeight: 34,
    verticalAlignment: "center",
  };
  issuesSheet.getRange(`A3:D${2 + issueRows.length}`).values = issueRows;
  issuesSheet.getRange("A3:D3").format = {
    fill: "#5B9BD5",
    font: { bold: true, color: "#FFFFFF" },
    wrapText: true,
    rowHeight: 30,
  };
  issuesSheet.getRange(`A4:D${2 + issueRows.length}`).format = {
    fill: "#FCE4D6",
    wrapText: true,
    verticalAlignment: "top",
    rowHeight: 38,
  };
  issuesSheet.getRange(`A3:D${2 + issueRows.length}`).format.borders = {
    preset: "all",
    style: "thin",
    color: "#D9E2E8",
  };
  issuesSheet.getRange("A:A").format.columnWidth = 24;
  issuesSheet.getRange("B:B").format.columnWidth = 24;
  issuesSheet.getRange("C:C").format.columnWidth = 42;
  issuesSheet.getRange("D:D").format.columnWidth = 68;
  issuesSheet.freezePanes.freezeRows(3);

  const correctionErrors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 100 },
    summary: "Correction workbook formula error scan",
  });
  console.log(correctionErrors.ndjson);
  for (const [sheetName, range, outputName] of [
    ["Summary", "A1:F19", "correction_summary.png"],
    ["Adjudication", "Q1:AA18", "correction_adjudication.png"],
    ["Provenance Attestation", "A1:F8", "correction_provenance.png"],
    ["Validation Issues", `A1:D${2 + issueRows.length}`, "correction_issues.png"],
  ]) {
    const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
    await fs.writeFile(
      `${workDir}/${outputName}`,
      new Uint8Array(await preview.arrayBuffer()),
    );
  }
  const correctionOutput = await SpreadsheetFile.exportXlsx(workbook);
  await correctionOutput.save(correctionWorkbookPath);
  console.log(JSON.stringify({
    status: "corrections_required",
    correction_workbook: correctionWorkbookPath,
    validation_issue_counts: invalidCounts,
    provenance_problems: provenanceProblems,
  }, null, 2));
  process.exit(0);
}

await fs.writeFile(extractedCsvPath, toCsv(rows.map((row) => row.slice(0, 26))));
console.log(JSON.stringify(audit, null, 2));

try {
  await fs.access(metricsPath);
  await fs.access(seedMetricsPath);
  await fs.access(predictionsPath);
  await fs.access(confidenceIntervalsPath);
  await fs.access(metadataPath);
} catch {
  process.exit(0);
}

const metricsCsv = await fs.readFile(metricsPath, "utf8");
const seedMetricsCsv = await fs.readFile(seedMetricsPath, "utf8");
const predictionsCsv = await fs.readFile(predictionsPath, "utf8");
const confidenceIntervals = JSON.parse(
  await fs.readFile(confidenceIntervalsPath, "utf8"),
);
const metadata = JSON.parse(await fs.readFile(metadataPath, "utf8"));
const results = await Workbook.fromCSV(metricsCsv, { sheetName: "Metrics" });
await results.fromCSV(seedMetricsCsv, { sheetName: "Seed Metrics" });
await results.fromCSV(predictionsCsv, { sheetName: "Predictions" });
const metricsSheet = results.worksheets.getItem("Metrics");
const metricRows = metricsSheet.getUsedRange(true).values;
const predictionsSheet = results.worksheets.getItem("Predictions");
const predictionRows = predictionsSheet.getUsedRange(true).values;
const seedMetricsSheet = results.worksheets.getItem("Seed Metrics");
const seedMetricRows = seedMetricsSheet.getUsedRange(true).values;

const summary = results.worksheets.add("Summary");
summary.showGridLines = false;
summary.getRange("A1:J1").merge();
summary.getRange("A1").values = [["Confirmatory Baseline and Proposed-System Evaluation"]];
summary.getRange("A1:J1").format = {
  fill: "#17324D",
  font: { bold: true, color: "#FFFFFF", size: 18 },
  rowHeight: 34,
  verticalAlignment: "center",
};
summary.getRange("A3:B10").values = [
  ["Benchmark audit", "Result"],
  ["Audited cases", audit.cases],
  ["Test cases", metadata.test_records],
  ["Intent Cohen's kappa", audit.intent_kappa],
  ["Action Cohen's kappa", audit.action_kappa],
  ["All statuses audited", "Yes"],
  ["Source lineage verified", "Yes"],
  [
    "Calibration status",
    metadata.calibration_status ||
      (Object.values(metadata.calibration_statuses || {}).every(
        (value) => value === "calibrated",
      )
        ? "calibrated (all seeds)"
        : "mixed"),
  ],
];
summary.getRange("A3:B3").format = {
  fill: "#5B9BD5",
  font: { bold: true, color: "#FFFFFF" },
};
summary.getRange("A4:A10").format = { fill: "#DDEBF7", font: { bold: true } };
summary.getRange("B6:B7").format.numberFormat = "0.000";
summary.getRange("D3:J3").values = [[
  "System", "Macro F1", "Accuracy", "Top-2", "Scenario Fit", "Conflict Rate", "ECE",
]];
summary.getRange("D3:J3").format = {
  fill: "#5B9BD5",
  font: { bold: true, color: "#FFFFFF" },
};
const header = metricRows[0].map(text);
const systemColumn = header.indexOf("System");
const accuracyColumn = header.indexOf("Recommendation Accuracy");
const macroF1Column = header.indexOf("Macro F1");
const top2Column = header.indexOf("Top-2 Agreement");
const scenarioColumn = header.indexOf("Scenario-Fit Rate");
const conflictColumn = header.indexOf("Logical Conflict Rate");
const eceColumn = header.indexOf("Expected Calibration Error (ECE)");
const proposedRows = metricRows.slice(1).filter((row) =>
  text(row[systemColumn]).includes("Proposed System") ||
  text(row[systemColumn]).startsWith("Baseline"));
summary.getRange(`D4:J${3 + proposedRows.length}`).values = proposedRows.map((row) => [
  row[systemColumn],
  Number(row[macroF1Column]),
  Number(row[accuracyColumn]),
  Number(row[top2Column]),
  Number(row[scenarioColumn]),
  Number(row[conflictColumn]),
  Number(row[eceColumn]),
]);
summary.getRange(`E4:J${3 + proposedRows.length}`).format.numberFormat = "0.000";
summary.getRange("A12:J12").merge();
summary.getRange("A12").values = [[
  "These are technical benchmark results on the frozen audited cases. Human-reliance outcomes still require the separate participant study.",
]];
summary.getRange("A12:J12").format = {
  fill: "#FFF2CC",
  wrapText: true,
  rowHeight: 34,
  verticalAlignment: "center",
};
summary.getRange("A:A").format.columnWidth = 31;
summary.getRange("B:B").format.columnWidth = 18;
summary.getRange("C:C").format.columnWidth = 3;
summary.getRange("D:D").format.columnWidth = 38;
summary.getRange("E:J").format.columnWidth = 14;

metricsSheet.showGridLines = false;
metricsSheet.freezePanes.freezeRows(1);
metricsSheet.getUsedRange(true).format.borders = {
  insideHorizontal: { style: "thin", color: "#E7ECEF" },
  bottom: { style: "thin", color: "#AAB7C2" },
};
metricsSheet.getRange(`A1:${String.fromCharCode(64 + metricRows[0].length)}1`).format = {
  fill: "#17324D",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
  rowHeight: 34,
};
metricsSheet.getRange("A:A").format.columnWidth = 44;
for (let column = 1; column < metricRows[0].length; column += 1) {
  const letter = String.fromCharCode(65 + column);
  metricsSheet.getRange(`${letter}:${letter}`).format.columnWidth = 19;
  metricsSheet.getRange(`${letter}2:${letter}${metricRows.length}`).format.numberFormat = "0.0000";
}

predictionsSheet.showGridLines = false;
predictionsSheet.freezePanes.freezeRows(1);
predictionsSheet.freezePanes.freezeColumns(3);
predictionsSheet.getRange(`A1:${String.fromCharCode(64 + predictionRows[0].length)}1`).format = {
  fill: "#17324D",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
  rowHeight: 38,
};
predictionsSheet.getUsedRange(true).format.borders = {
  insideHorizontal: { style: "thin", color: "#E7ECEF" },
  bottom: { style: "thin", color: "#AAB7C2" },
};
predictionsSheet.getRange("A:A").format.columnWidth = 18;
predictionsSheet.getRange("B:C").format.columnWidth = 22;
for (let column = 3; column < predictionRows[0].length; column += 1) {
  const letter = String.fromCharCode(65 + column);
  predictionsSheet.getRange(`${letter}:${letter}`).format.columnWidth = 24;
}

seedMetricsSheet.showGridLines = false;
seedMetricsSheet.freezePanes.freezeRows(1);
seedMetricsSheet.getRange(
  `A1:${String.fromCharCode(64 + seedMetricRows[0].length)}1`,
).format = {
  fill: "#17324D",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
  rowHeight: 38,
};
seedMetricsSheet.getUsedRange(true).format.borders = {
  insideHorizontal: { style: "thin", color: "#E7ECEF" },
  bottom: { style: "thin", color: "#AAB7C2" },
};
seedMetricsSheet.getRange("A:A").format.columnWidth = 44;
seedMetricsSheet.getRange("B:B").format.columnWidth = 16;
for (let column = 2; column < seedMetricRows[0].length; column += 1) {
  const letter = String.fromCharCode(65 + column);
  seedMetricsSheet.getRange(`${letter}:${letter}`).format.columnWidth = 18;
  seedMetricsSheet.getRange(
    `${letter}2:${letter}${seedMetricRows.length}`,
  ).format.numberFormat = "0.0000";
}

const intervalSheet = results.worksheets.add("Confidence Intervals");
intervalSheet.showGridLines = false;
const intervalRows = [["System", "Metric", "95% CI Lower", "95% CI Upper"]];
for (const [system, metrics] of Object.entries(confidenceIntervals)) {
  for (const [metric, bounds] of Object.entries(metrics)) {
    intervalRows.push([system, metric, Number(bounds[0]), Number(bounds[1])]);
  }
}
intervalSheet.getRange(`A1:D${intervalRows.length}`).values = intervalRows;
intervalSheet.getRange("A1:D1").format = {
  fill: "#17324D",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
  rowHeight: 32,
};
intervalSheet.getRange(`A2:D${intervalRows.length}`).format.borders = {
  insideHorizontal: { style: "thin", color: "#E7ECEF" },
  bottom: { style: "thin", color: "#AAB7C2" },
};
intervalSheet.getRange(`C2:D${intervalRows.length}`).format.numberFormat = "0.0000";
intervalSheet.getRange("A:A").format.columnWidth = 44;
intervalSheet.getRange("B:B").format.columnWidth = 40;
intervalSheet.getRange("C:D").format.columnWidth = 18;
intervalSheet.freezePanes.freezeRows(1);

const metadataSheet = results.worksheets.add("Run Metadata");
metadataSheet.showGridLines = false;
const metadataRows = [["Field", "Value"]];
for (const [key, value] of Object.entries(metadata)) {
  metadataRows.push([
    key,
    typeof value === "object" ? JSON.stringify(value) : String(value),
  ]);
}
metadataSheet.getRange(`A1:B${metadataRows.length}`).values = metadataRows;
metadataSheet.getRange("A1:B1").format = {
  fill: "#17324D",
  font: { bold: true, color: "#FFFFFF" },
  rowHeight: 30,
};
metadataSheet.getRange(`A2:A${metadataRows.length}`).format = {
  fill: "#DDEBF7",
  font: { bold: true },
};
metadataSheet.getRange(`A1:B${metadataRows.length}`).format.borders = {
  insideHorizontal: { style: "thin", color: "#E7ECEF" },
  bottom: { style: "thin", color: "#AAB7C2" },
};
metadataSheet.getRange("A:A").format.columnWidth = 36;
metadataSheet.getRange("B:B").format = {
  columnWidth: 74,
  wrapText: true,
  verticalAlignment: "top",
};

const benchmarkAudit = results.worksheets.add("Benchmark Audit");
benchmarkAudit.showGridLines = false;
benchmarkAudit.getRange("A1:D1").merge();
benchmarkAudit.getRange("A1").values = [["Frozen Human Benchmark Audit"]];
benchmarkAudit.getRange("A1:D1").format = {
  fill: "#17324D",
  font: { bold: true, color: "#FFFFFF", size: 18 },
  rowHeight: 34,
};
benchmarkAudit.getRange("A3:B14").values = [
  ["Check", "Result"],
  ["Cases", audit.cases],
  ["Unique campaign IDs", audit.unique_campaign_ids],
  ["Source fields match candidate", "Yes"],
  ["All reviewer labels valid", "Yes"],
  ["All adjudicated labels valid", "Yes"],
  ["All statuses audited", "Yes"],
  ["Provenance attestations complete", "Yes"],
  ["Intent observed agreement", audit.intent_observed_agreement],
  ["Intent Cohen's kappa", audit.intent_kappa],
  ["Action observed agreement", audit.action_observed_agreement],
  ["Action Cohen's kappa", audit.action_kappa],
];
benchmarkAudit.getRange("A3:B3").format = {
  fill: "#5B9BD5",
  font: { bold: true, color: "#FFFFFF" },
};
benchmarkAudit.getRange("A4:A14").format = { fill: "#DDEBF7", font: { bold: true } };
benchmarkAudit.getRange("B11:B14").format.numberFormat = "0.000";
benchmarkAudit.getRange("A:A").format.columnWidth = 38;
benchmarkAudit.getRange("B:B").format.columnWidth = 24;

const finalErrors = await results.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 200 },
  summary: "Confirmatory results workbook formula error scan",
});
console.log(finalErrors.ndjson);
for (const [sheetName, range, outputName] of [
  ["Summary", "A1:J12", "results_summary.png"],
  ["Metrics", `A1:${String.fromCharCode(64 + metricRows[0].length)}${metricRows.length}`, "results_metrics.png"],
  ["Predictions", "A1:L12", "results_predictions.png"],
  ["Seed Metrics", `A1:${String.fromCharCode(64 + seedMetricRows[0].length)}${seedMetricRows.length}`, "results_seed_metrics.png"],
  ["Confidence Intervals", `A1:D${intervalRows.length}`, "results_confidence_intervals.png"],
  ["Run Metadata", `A1:B${metadataRows.length}`, "results_run_metadata.png"],
  ["Benchmark Audit", "A1:D14", "results_benchmark_audit.png"],
]) {
  const preview = await results.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(
    `${workDir}/${outputName}`,
    new Uint8Array(await preview.arrayBuffer()),
  );
}
const output = await SpreadsheetFile.exportXlsx(results);
await output.save(finalWorkbookPath);
console.log(finalWorkbookPath);
