import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const root =
  "C:/Users/user/Desktop/FYP Prototype/FYP-Desicion-Support-System/data/annotation_packets";
for (const reviewer of [1, 2]) {
  const workbook = await SpreadsheetFile.importXlsx(
    await FileBlob.load(`${root}/Reviewer_${reviewer}_Annotation_Packet.xlsx`),
  );
  const readme = await workbook.inspect({
    kind: "table",
    sheetId: "Read Me",
    range: "A1:B8",
    include: "values,formulas",
    tableMaxRows: 8,
    tableMaxCols: 2,
    maxChars: 5000,
  });
  console.log(`Reviewer ${reviewer} - Read Me`);
  console.log(readme.ndjson);
  for (const sheetName of ["Pilot 25 Cases", "Full 125 Cases"]) {
    const inspection = await workbook.inspect({
      kind: "table",
      sheetId: sheetName,
      range: "A1:S4",
      include: "values,formulas",
      tableMaxRows: 4,
      tableMaxCols: 19,
      maxChars: 9000,
    });
    console.log(`Reviewer ${reviewer} - ${sheetName}`);
    console.log(inspection.ndjson);
  }
  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 100 },
  });
  console.log(errors.ndjson);
}
