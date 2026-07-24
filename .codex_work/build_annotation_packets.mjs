import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = "C:/Users/user/Desktop/FYP Prototype/FYP-Desicion-Support-System";
const outputDir = `${root}/data/annotation_packets`;
const previewDir = `${root}/.codex_work/annotation_previews`;
await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

async function createPacket(reviewerNumber) {
  const pilotCsv = await fs.readFile(`${root}/data/pilot_reviewer_${reviewerNumber}.csv`, "utf8");
  const fullCsv = await fs.readFile(`${root}/data/benchmark_reviewer_${reviewerNumber}.csv`, "utf8");
  const workbook = await Workbook.fromCSV(pilotCsv, { sheetName: "Pilot 25 Cases" });
  await workbook.fromCSV(fullCsv, { sheetName: "Full 125 Cases" });
  const instructions = workbook.worksheets.add("Read Me");
  instructions.showGridLines = false;
  instructions.getRange("A1:F1").merge();
  instructions.getRange("A1").values = [[`Independent Human Annotation - Reviewer ${reviewerNumber}`]];
  instructions.getRange("A1:F1").format = {
    fill: "#17324D",
    font: { bold: true, color: "#FFFFFF", size: 18 },
    rowHeight: 34,
    verticalAlignment: "center",
  };
  const notes = [
    ["Purpose", "Assign one strategic intent and one bounded action using only the campaign evidence shown."],
    ["Independence", "Do not consult the other reviewer, system recommendations, AI tools, or generated labels."],
    ["Pilot", "Complete the 25-case Pilot sheet first. Discuss rubric ambiguity only after both reviewers finish."],
    ["Full review", "Complete all 125 cases only after the pilot rubric is frozen."],
    ["Allowed intents", "Survival; Retention; Growth"],
    ["Allowed actions", "Increase; Maintain; Reduce; Investigate"],
    ["Notes", "Record the evidence and assumptions supporting each choice."],
    ["Privacy", "Do not add names, email addresses, or personal customer information."],
  ];
  instructions.getRange("A3:B10").values = notes;
  instructions.getRange("A3:A10").format = {
    fill: "#DDEBF7",
    font: { bold: true, color: "#17324D" },
  };
  instructions.getRange("B3:B10").format = { wrapText: true };
  instructions.getRange("A3:B10").format.borders = {
    preset: "inside",
    style: "thin",
    color: "#D9E2E8",
  };
  instructions.getRange("A:A").format.columnWidth = 20;
  instructions.getRange("B:B").format.columnWidth = 72;

  for (const [sheetName, rows] of [["Pilot 25 Cases", 26], ["Full 125 Cases", 126]]) {
    const sheet = workbook.worksheets.getItem(sheetName);
    sheet.showGridLines = false;
    sheet.freezePanes.freezeRows(1);
    sheet.freezePanes.freezeColumns(1);
    sheet.getRange("A1:S1").format = {
      fill: "#17324D",
      font: { bold: true, color: "#FFFFFF" },
      wrapText: true,
      rowHeight: 34,
      verticalAlignment: "center",
    };
    sheet.getRange(`Q2:S${rows}`).format = {
      fill: "#FFF2CC",
      wrapText: true,
      verticalAlignment: "top",
    };
    sheet.getRange(`Q2:Q${rows}`).dataValidation = {
      rule: { type: "list", values: ["Survival", "Retention", "Growth"] },
    };
    sheet.getRange(`R2:R${rows}`).dataValidation = {
      rule: { type: "list", values: ["Increase", "Maintain", "Reduce", "Investigate"] },
    };
    sheet.getRange(`A1:S${rows}`).format.borders = {
      insideHorizontal: { style: "thin", color: "#E7ECEF" },
      bottom: { style: "thin", color: "#AAB7C2" },
    };
    sheet.getRange(`D2:D${rows}`).format.numberFormat = "0";
    sheet.getRange(`F2:J${rows}`).format.numberFormat = "#,##0";
    sheet.getRange(`K2:L${rows}`).format.numberFormat = "0.00";
    sheet.getRange(`N2:N${rows}`).format.numberFormat = "0.00";
    sheet.getRange(`P2:P${rows}`).format.numberFormat = "yyyy-mm-dd";
    const widths = {
      A: 18, B: 18, C: 23, D: 10, E: 28, F: 14, G: 12, H: 12, I: 14,
      J: 15, K: 17, L: 10, M: 12, N: 16, O: 22, P: 13, Q: 18, R: 18, S: 42,
    };
    for (const [column, width] of Object.entries(widths)) {
      sheet.getRange(`${column}:${column}`).format.columnWidth = width;
    }
  }

  for (const [sheetName, range, suffix] of [
    ["Read Me", "A1:F10", "readme"],
    ["Pilot 25 Cases", "A1:S15", "pilot"],
    ["Full 125 Cases", "A1:S15", "full"],
  ]) {
    const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
    await fs.writeFile(
      `${previewDir}/reviewer_${reviewerNumber}_${suffix}.png`,
      new Uint8Array(await preview.arrayBuffer()),
    );
  }

  const inspection = await workbook.inspect({
    kind: "region",
    sheetId: "Pilot 25 Cases",
    range: "Q1:S6",
    maxChars: 2000,
  });
  console.log(inspection.ndjson);
  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 50 },
    summary: `Reviewer ${reviewerNumber} formula-error scan`,
  });
  console.log(errors.ndjson);
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(`${outputDir}/Reviewer_${reviewerNumber}_Annotation_Packet.xlsx`);
}

await createPacket(1);
await createPacket(2);
