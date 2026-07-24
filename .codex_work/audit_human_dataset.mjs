import fs from "node:fs/promises";
import { Workbook } from "@oai/artifact-tool";

const inputPath =
  "C:/Users/user/Downloads/Dataset_development_human_annotated_v2.csv";
const csvText = await fs.readFile(inputPath, "utf8");
const workbook = await Workbook.fromCSV(csvText, { sheetName: "Human Annotations" });
const overview = await workbook.inspect({
  kind: "workbook,sheet,table",
  maxChars: 5000,
  tableMaxRows: 8,
  tableMaxCols: 24,
  tableMaxCellChars: 120,
});
const keyRange = await workbook.inspect({
  kind: "region",
  sheetId: "Human Annotations",
  range: "A1:X12",
  maxChars: 9000,
});
console.log(overview.ndjson);
console.log(keyRange.ndjson);
