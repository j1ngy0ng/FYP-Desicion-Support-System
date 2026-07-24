import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = "C:/Users/user/Desktop/FYP Prototype/FYP-Desicion-Support-System";
const sourceFiles = [
  "C:/Users/user/Downloads/Reviewer_1_Completed.xlsx",
  "C:/Users/user/Downloads/Reviewer_2_Completed.xlsx",
];
const workDir = `${root}/.codex_work/completed_reviews`;
const dataDir = `${root}/data/human_annotations/completed`;
const outputDir = `${root}/outputs/reviewer_adjudication_2026-07-23`;
const mergedCsvPath = `${dataDir}/human_adjudication_working.csv`;
const finalWorkbookPath = `${outputDir}/Human_Annotation_Adjudication_Pending_Attestation.xlsx`;
const allowedIntents = new Set(["Survival", "Retention", "Growth"]);
const allowedActions = new Set(["Increase", "Maintain", "Reduce", "Investigate"]);

await fs.mkdir(workDir, { recursive: true });
await fs.mkdir(dataDir, { recursive: true });
await fs.mkdir(outputDir, { recursive: true });

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

function classifyAgreement(first, second) {
  const intentSame = text(first[16]) === text(second[16]);
  const actionSame = text(first[17]) === text(second[17]);
  if (intentSame && actionSame) return "Full Agreement";
  if (!intentSame && !actionSame) return "Both Disagree";
  if (!intentSame) return "Intent Disagreement";
  return "Action Disagreement";
}

async function loadReviewer(path, reviewerNumber) {
  const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(path));
  const sheetOverview = await workbook.inspect({
    kind: "sheet",
    include: "id,name",
    maxChars: 3000,
  });
  console.log(`Reviewer ${reviewerNumber} sheets`);
  console.log(sheetOverview.ndjson);

  const result = { workbook, sheets: {} };
  for (const [sheetName, expectedRows, renderRange, required] of [
    ["Read Me", 10, "A1:F10", false],
    ["Pilot 25 Cases", 26, "A1:S15", true],
    ["Full 125 Cases", 126, "A1:S15", true],
  ]) {
    let sheet;
    try {
      sheet = workbook.worksheets.getItem(sheetName);
    } catch (error) {
      if (required) throw error;
      continue;
    }
    const used = sheet.getUsedRange(true);
    const values = used.values;
    result.sheets[sheetName] = values;
    if (values.length !== expectedRows) {
      throw new Error(
        `Reviewer ${reviewerNumber} ${sheetName} has ${values.length} used rows; expected ${expectedRows}.`,
      );
    }
    const inspection = await workbook.inspect({
      kind: "table",
      sheetId: sheetName,
      range: sheetName === "Full 125 Cases" ? "A120:S126" : renderRange,
      include: "values,formulas",
      tableMaxRows: 15,
      tableMaxCols: 19,
      maxChars: 8000,
    });
    console.log(`Reviewer ${reviewerNumber} ${sheetName}`);
    console.log(inspection.ndjson);
    const preview = await workbook.render({
      sheetName,
      range: renderRange,
      scale: 1,
      format: "png",
    });
    await fs.writeFile(
      `${workDir}/reviewer_${reviewerNumber}_${sheetName.replaceAll(" ", "_")}.png`,
      new Uint8Array(await preview.arrayBuffer()),
    );
  }
  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 100 },
    summary: `Reviewer ${reviewerNumber} formula error scan`,
  });
  console.log(errors.ndjson);
  return result;
}

const reviewers = [];
for (let index = 0; index < sourceFiles.length; index += 1) {
  reviewers.push(await loadReviewer(sourceFiles[index], index + 1));
}

function validateSheet(rows, reviewerNumber, label) {
  const header = rows[0].map(text);
  const expectedTail = ["Reviewer_Intent", "Reviewer_Action", "Reviewer_Notes"];
  if (header.slice(16, 19).join("|") !== expectedTail.join("|")) {
    throw new Error(`Reviewer ${reviewerNumber} ${label} has unexpected annotation headers.`);
  }
  const data = rows.slice(1);
  const ids = data.map((row) => text(row[0]));
  const invalidIntents = data.filter((row) => !allowedIntents.has(text(row[16])));
  const invalidActions = data.filter((row) => !allowedActions.has(text(row[17])));
  const blankNotes = data.filter((row) => !text(row[18]));
  const duplicates = ids.filter((id, index) => ids.indexOf(id) !== index);
  if (invalidIntents.length || invalidActions.length || duplicates.length) {
    throw new Error(JSON.stringify({
      reviewer: reviewerNumber,
      sheet: label,
      invalid_intents: invalidIntents.map((row) => text(row[0])),
      invalid_actions: invalidActions.map((row) => text(row[0])),
      duplicate_ids: [...new Set(duplicates)],
    }, null, 2));
  }
  return { data, ids, blankNotes: blankNotes.map((row) => text(row[0])) };
}

const full = reviewers.map((reviewer, index) =>
  validateSheet(reviewer.sheets["Full 125 Cases"], index + 1, "Full 125 Cases"));
const pilot = reviewers.map((reviewer, index) =>
  validateSheet(reviewer.sheets["Pilot 25 Cases"], index + 1, "Pilot 25 Cases"));

function align(first, second, label) {
  const secondById = new Map(second.data.map((row) => [text(row[0]), row]));
  if (
    first.ids.length !== second.ids.length ||
    first.ids.some((id) => !secondById.has(id))
  ) {
    throw new Error(`${label} reviewer files do not contain the same campaign IDs.`);
  }
  for (const row of first.data) {
    const other = secondById.get(text(row[0]));
    for (let column = 0; column < 16; column += 1) {
      if (text(row[column]) !== text(other[column])) {
        throw new Error(
          `${label} source mismatch for ${text(row[0])} at column ${column + 1}.`,
        );
      }
    }
  }
  return first.data.map((row) => [row, secondById.get(text(row[0]))]);
}

const fullPairs = align(full[0], full[1], "Full review");
const pilotPairs = align(pilot[0], pilot[1], "Pilot");

function agreementSummary(pairs) {
  const firstIntents = pairs.map(([first]) => text(first[16]));
  const secondIntents = pairs.map(([, second]) => text(second[16]));
  const firstActions = pairs.map(([first]) => text(first[17]));
  const secondActions = pairs.map(([, second]) => text(second[17]));
  const agreementCounts = {};
  for (const pair of pairs) {
    const classification = classifyAgreement(...pair);
    agreementCounts[classification] = (agreementCounts[classification] || 0) + 1;
  }
  return {
    cases: pairs.length,
    intent_observed_agreement:
      firstIntents.filter((value, index) => value === secondIntents[index]).length / pairs.length,
    intent_kappa: kappa(firstIntents, secondIntents),
    action_observed_agreement:
      firstActions.filter((value, index) => value === secondActions[index]).length / pairs.length,
    action_kappa: kappa(firstActions, secondActions),
    agreement_counts: agreementCounts,
  };
}

const audit = {
  reviewer_1_file: sourceFiles[0],
  reviewer_2_file: sourceFiles[1],
  allowed_intents: [...allowedIntents],
  allowed_actions: [...allowedActions],
  reviewer_1_blank_full_notes: full[0].blankNotes,
  reviewer_2_blank_full_notes: full[1].blankNotes,
  reviewer_1_declares_ai_assistance: (reviewers[0].sheets["Read Me"] || [])
    .flat()
    .some((value) => text(value).toLowerCase().includes("ai-assisted")),
  user_confirmed_human_completion: true,
  confirmatory_eligible: "pending_reviewer_attestation_and_adjudication",
  provenance_note:
    "The user confirms both current files were completed by humans. Reviewer attestation remains required as a reproducible audit record before the benchmark is frozen.",
  pilot: agreementSummary(pilotPairs),
  full: agreementSummary(fullPairs),
};

await fs.writeFile(`${workDir}/audit.json`, JSON.stringify(audit, null, 2));
await fs.writeFile(`${dataDir}/reviewer_1_completed.csv`, toCsv(reviewers[0].sheets["Full 125 Cases"]));
await fs.writeFile(`${dataDir}/reviewer_2_completed.csv`, toCsv(reviewers[1].sheets["Full 125 Cases"]));
console.log(JSON.stringify(audit, null, 2));

try {
  await fs.access(mergedCsvPath);
} catch {
  process.exit(0);
}

const mergedCsv = await fs.readFile(mergedCsvPath, "utf8");
const adjudicationWorkbook = await Workbook.fromCSV(mergedCsv, { sheetName: "Adjudication" });
const adjudication = adjudicationWorkbook.worksheets.getItem("Adjudication");
const mergedRows = adjudication.getUsedRange(true).values;
if (mergedRows.length !== 126) {
  throw new Error(`Merged adjudication file contains ${mergedRows.length - 1} cases; expected 125.`);
}

mergedRows[0].push("Agreement_Flag");
for (let rowIndex = 1; rowIndex < mergedRows.length; rowIndex += 1) {
  const row = mergedRows[rowIndex];
  if (text(row[16]) === text(row[19])) row[22] = text(row[16]);
  if (text(row[17]) === text(row[20])) row[23] = text(row[17]);
  row[25] = "Pending Audit";
  row.push(classifyAgreement(
    [...row.slice(0, 16), row[16], row[17], row[18]],
    [...row.slice(0, 16), row[19], row[20], row[21]],
  ));
}
adjudication.getRange("A1:AA126").values = mergedRows;
adjudication.showGridLines = false;
adjudication.freezePanes.freezeRows(1);
adjudication.freezePanes.freezeColumns(1);
adjudication.getRange("A1:AA1").format = {
  fill: "#17324D",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
  rowHeight: 36,
  verticalAlignment: "center",
};
adjudication.getRange("Q2:V126").format = {
  fill: "#DDEBF7",
  wrapText: true,
  verticalAlignment: "top",
};
adjudication.getRange("W2:Z126").format = {
  fill: "#FFF2CC",
  wrapText: true,
  verticalAlignment: "top",
};
adjudication.getRange("AA2:AA126").format = {
  fill: "#E2F0D9",
  font: { bold: true, color: "#244062" },
  wrapText: true,
};
adjudication.getRange("W2:W126").dataValidation = {
  rule: { type: "list", values: [...allowedIntents] },
};
adjudication.getRange("X2:X126").dataValidation = {
  rule: { type: "list", values: [...allowedActions] },
};
adjudication.getRange("Z2:Z126").dataValidation = {
  rule: { type: "list", values: ["Pending Audit", "Audited", "Remove"] },
};
adjudication.getRange("AA2:AA126").conditionalFormats.add("containsText", {
  text: "Disagreement",
  format: { fill: "#FCE4D6", font: { color: "#9C0006", bold: true } },
});
adjudication.getRange("A1:AA126").format.borders = {
  insideHorizontal: { style: "thin", color: "#E7ECEF" },
  bottom: { style: "thin", color: "#AAB7C2" },
};
const widths = {
  A: 18, B: 18, C: 22, D: 10, E: 26, F: 13, G: 11, H: 11, I: 13,
  J: 15, K: 17, L: 10, M: 12, N: 15, O: 22, P: 13,
  Q: 18, R: 18, S: 38, T: 18, U: 18, V: 38,
  W: 20, X: 20, Y: 38, Z: 18, AA: 22,
};
for (const [column, width] of Object.entries(widths)) {
  adjudication.getRange(`${column}:${column}`).format.columnWidth = width;
}
const table = adjudication.tables.add("A1:AA126", true, "AdjudicationTable");
table.style = "TableStyleMedium2";
table.showBandedRows = true;
table.showFilterButton = true;

const summary = adjudicationWorkbook.worksheets.add("Summary");
summary.showGridLines = false;
summary.getRange("A1:F1").merge();
summary.getRange("A1").values = [["Independent Human Review Agreement and Adjudication"]];
summary.getRange("A1:F1").format = {
  fill: "#17324D",
  font: { bold: true, color: "#FFFFFF", size: 18 },
  rowHeight: 34,
  verticalAlignment: "center",
};
summary.getRange("A2:F2").merge();
summary.getRange("A2").values = [[
  "PROVENANCE CHECK: The user confirms both reviews were human-completed. Both reviewers should complete the Provenance Attestation sheet before the benchmark is frozen.",
]];
summary.getRange("A2:F2").format = {
  fill: "#FFF2CC",
  font: { bold: true, color: "#7F6000" },
  wrapText: true,
  rowHeight: 42,
  verticalAlignment: "center",
};
summary.getRange("A4:B12").values = [
  ["Metric", "Result"],
  ["Benchmark cases", audit.full.cases],
  ["Intent observed agreement", audit.full.intent_observed_agreement],
  ["Intent Cohen's kappa", audit.full.intent_kappa],
  ["Action observed agreement", audit.full.action_observed_agreement],
  ["Action Cohen's kappa", audit.full.action_kappa],
  ["Full agreements", audit.full.agreement_counts["Full Agreement"] || 0],
  ["Cases needing intent adjudication",
    (audit.full.agreement_counts["Intent Disagreement"] || 0) +
    (audit.full.agreement_counts["Both Disagree"] || 0)],
  ["Cases needing action adjudication",
    (audit.full.agreement_counts["Action Disagreement"] || 0) +
    (audit.full.agreement_counts["Both Disagree"] || 0)],
];
summary.getRange("A4:B4").format = {
  fill: "#5B9BD5",
  font: { bold: true, color: "#FFFFFF" },
};
summary.getRange("A5:A12").format = { fill: "#DDEBF7", font: { bold: true } };
summary.getRange("B6:B9").format.numberFormat = "0.000";
summary.getRange("A14:F14").merge();
summary.getRange("A14").values = [["Required next step"]];
summary.getRange("A14:F14").format = {
  fill: "#5B9BD5",
  font: { bold: true, color: "#FFFFFF" },
};
summary.getRange("A15:F19").merge(true);
summary.getRange("A15:A19").values = [
  ["1. Reviewer 1 and Reviewer 2 complete the Provenance Attestation sheet."],
  ["2. Filter Agreement_Flag for disagreements; a third human reviewer selects the final labels."],
  ["3. Record concise reasons in Adjudicator_Notes and complete the adjudicator attestation."],
  ["4. Verify agreed rows and set every accepted row's Annotation_Status to Audited."],
  ["5. Export the completed Adjudication sheet to CSV, finalize it and run the evaluation."],
];
summary.getRange("A15:F19").format = {
  fill: "#FFF2CC",
  wrapText: true,
  rowHeight: 28,
  verticalAlignment: "center",
};
summary.getRange("A:A").format.columnWidth = 34;
summary.getRange("B:B").format.columnWidth = 18;
summary.getRange("C:F").format.columnWidth = 16;

const provenance = adjudicationWorkbook.worksheets.add("Provenance Attestation");
provenance.showGridLines = false;
provenance.getRange("A1:F1").merge();
provenance.getRange("A1").values = [["Human Annotation Provenance Attestation"]];
provenance.getRange("A1:F1").format = {
  fill: "#17324D",
  font: { bold: true, color: "#FFFFFF", size: 18 },
  rowHeight: 34,
  verticalAlignment: "center",
};
provenance.getRange("A3:F3").merge();
provenance.getRange("A3").values = [[
  "Each person confirms that their labels or adjudication decisions were made independently from the campaign evidence and frozen rubric, without AI-generated or system-suggested labels.",
]];
provenance.getRange("A3:F3").format = {
  fill: "#DDEBF7",
  wrapText: true,
  rowHeight: 42,
  verticalAlignment: "center",
};
provenance.getRange("A5:F8").values = [
  ["Role", "Name or Reviewer ID", "Human-only completion?", "Completion date", "Signature / initials", "Notes"],
  ["Reviewer 1", "", "", "", "", ""],
  ["Reviewer 2", "", "", "", "", ""],
  ["Adjudicator", "", "", "", "", ""],
];
provenance.getRange("A5:F5").format = {
  fill: "#5B9BD5",
  font: { bold: true, color: "#FFFFFF" },
  wrapText: true,
  rowHeight: 30,
};
provenance.getRange("A6:F8").format = {
  fill: "#FFF2CC",
  wrapText: true,
  verticalAlignment: "top",
  rowHeight: 42,
};
provenance.getRange("C6:C8").dataValidation = {
  rule: { type: "list", values: ["Yes", "No"] },
};
provenance.getRange("D6:D8").format.numberFormat = "yyyy-mm-dd";
provenance.getRange("A5:F8").format.borders = {
  preset: "all",
  style: "thin",
  color: "#D9E2E8",
};
const provenanceWidths = { A: 18, B: 24, C: 22, D: 18, E: 22, F: 58 };
for (const [column, width] of Object.entries(provenanceWidths)) {
  provenance.getRange(`${column}:${column}`).format.columnWidth = width;
}

const finalErrors = await adjudicationWorkbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "Final adjudication workbook formula error scan",
});
console.log(finalErrors.ndjson);
for (const [sheetName, range, outputName] of [
  ["Summary", "A1:F19", "final_summary.png"],
  ["Adjudication", "Q1:AA18", "final_adjudication.png"],
  ["Provenance Attestation", "A1:F8", "final_provenance.png"],
]) {
  const preview = await adjudicationWorkbook.render({
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
const finalInspection = await adjudicationWorkbook.inspect({
  kind: "table",
  sheetId: "Adjudication",
  range: "Q1:AA8",
  include: "values,formulas",
  tableMaxRows: 8,
  tableMaxCols: 11,
  maxChars: 10000,
});
console.log(finalInspection.ndjson);
const output = await SpreadsheetFile.exportXlsx(adjudicationWorkbook);
await output.save(finalWorkbookPath);
console.log(finalWorkbookPath);
