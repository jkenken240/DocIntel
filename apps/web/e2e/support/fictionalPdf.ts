import { writeFile } from "node:fs/promises";

function escapePdfText(value: string): string {
  return value.replaceAll("\\", "\\\\").replaceAll("(", "\\(").replaceAll(")", "\\)");
}

export async function writeFictionalPdf(
  filePath: string,
  pages: readonly string[],
): Promise<void> {
  if (pages.length === 0) throw new Error("A fictional PDF needs at least one page.");

  const fontObject = 3 + pages.length * 2;
  const objects = new Map<number, string>();
  const pageObjects = pages.map((_, index) => 3 + index * 2);
  objects.set(1, "<< /Type /Catalog /Pages 2 0 R >>");
  objects.set(
    2,
    `<< /Type /Pages /Kids [${pageObjects.map((number) => `${number} 0 R`).join(" ")}] /Count ${pages.length} >>`,
  );

  pages.forEach((pageText, index) => {
    const pageObject = pageObjects[index];
    const contentObject = pageObject + 1;
    const stream = `BT\n/F1 14 Tf\n72 720 Td\n(${escapePdfText(pageText)}) Tj\nET\n`;
    objects.set(
      pageObject,
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 ${fontObject} 0 R >> >> /Contents ${contentObject} 0 R >>`,
    );
    objects.set(
      contentObject,
      `<< /Length ${Buffer.byteLength(stream, "latin1")} >>\nstream\n${stream}endstream`,
    );
  });
  objects.set(fontObject, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");

  let pdf = "%PDF-1.4\n% DocIntel fictional test fixture\n";
  const offsets = new Array<number>(fontObject + 1).fill(0);
  for (let objectNumber = 1; objectNumber <= fontObject; objectNumber += 1) {
    offsets[objectNumber] = Buffer.byteLength(pdf, "latin1");
    pdf += `${objectNumber} 0 obj\n${objects.get(objectNumber)}\nendobj\n`;
  }

  const xrefOffset = Buffer.byteLength(pdf, "latin1");
  pdf += `xref\n0 ${fontObject + 1}\n`;
  pdf += "0000000000 65535 f \n";
  for (let objectNumber = 1; objectNumber <= fontObject; objectNumber += 1) {
    pdf += `${String(offsets[objectNumber]).padStart(10, "0")} 00000 n \n`;
  }
  pdf += `trailer\n<< /Size ${fontObject + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF\n`;

  await writeFile(filePath, Buffer.from(pdf, "latin1"));
}
