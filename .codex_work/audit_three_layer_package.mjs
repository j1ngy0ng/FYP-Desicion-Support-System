import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const base =
  "C:/Users/user/Downloads/nykaa_three_layer_dataset(1)/nykaa_data_layers";
const out = ".codex_work/three_layer_audit";
await fs.mkdir(out, { recursive: true });

for (const [file, sheetName] of [
  ["01_raw_dataset_55555x16.csv", "Raw"],
  ["02_processed_model_data.csv", "Processed"],
  ["03_gold_benchmark_125.csv", "Gold Benchmark"],
]) {
  const csvText = await fs.readFile(path.join(base, file), "utf8");
  const workbook = await Workbook.fromCSV(csvText, { sheetName });
  const summary = await workbook.inspect({
    kind: "workbook,sheet,table",
    maxChars: 8000,
    tableMaxRows: 8,
    tableMaxCols: 40,
    tableMaxCellChars: 140,
  });
  console.log(`FILE ${file}`);
  console.log(summary.ndjson);
}

const reviewPath = path.join(base, "03_gold_benchmark_review.xlsx");
const review = await SpreadsheetFile.importXlsx(await FileBlob.load(reviewPath));
const reviewSummary = await review.inspect({
  kind: "workbook,sheet,table,drawing",
  maxChars: 16000,
  tableMaxRows: 12,
  tableMaxCols: 36,
  tableMaxCellChars: 140,
});
console.log("FILE 03_gold_benchmark_review.xlsx");
console.log(reviewSummary.ndjson);

const sheets = await review.inspect({ kind: "sheet", include: "id,name" });
console.log(sheets.ndjson);
for (const item of review.worksheets.items) {
  const safe = item.name.replace(/[^A-Za-z0-9_-]+/g, "_");
  const region = await review.inspect({
    kind: "region",
    sheetId: item.name,
    range: item.getUsedRange().address,
    maxChars: 12000,
  });
  console.log(`SHEET ${item.name}`);
  console.log(region.ndjson);
  const formulas = await review.inspect({
    kind: "formula",
    sheetId: item.name,
    maxChars: 6000,
    options: { maxResults: 100 },
  });
  console.log(formulas.ndjson);
  const preview = await review.render({
    sheetName: item.name,
    autoCrop: "all",
    scale: 1,
    format: "png",
  });
  await fs.writeFile(
    path.join(out, `${safe}.png`),
    new Uint8Array(await preview.arrayBuffer()),
  );
}

const errors = await review.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "formula error scan",
});
console.log(errors.ndjson);
